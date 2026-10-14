"""Atomic cleanup publication and guarded undo; old setups/runs remain immutable."""

from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.domain.edits import EditResult, GeometryEdit
from app.domain.errors import DomainError, not_found, stale_revision
from app.domain.loads import LoadAssignment, LoadSetup
from app.domain.materials import BodyMaterial, MaterialSetup
from app.domain.mesh import MeshSetup
from app.domain.models import AnalysisCreate, GeometryMetadata, GeometryRevision
from app.persistence.repository import Repository, now


def remap_loads(edit: GeometryEdit, geometry: GeometryRevision, setup: LoadSetup) -> LoadSetup:
    assert edit.preview is not None
    mappings = {m.source_face_id: m for m in edit.preview.mappings}
    assignments = []
    for item in setup.assignments:
        if item.kind == "gravity":
            assignments.append(
                item.model_copy(update={"review_bodies": item.review_bodies or item.body_ids})
            )
            continue  # Body mass/centroid changed; never silently transfer gravity.
        uncertain = [
            f for f in item.face_ids if f not in mappings or mappings[f].status != "unchanged"
        ]
        if item.review_faces or uncertain:
            assignments.append(
                item.model_copy(update={"review_faces": item.review_faces or uncertain})
            )
        else:
            targets: list[str] = []
            for face_id in item.face_ids:
                target = mappings[face_id].target_face_id
                assert target is not None
                targets.append(target)
            assignments.append(
                LoadAssignment.model_validate(
                    item.model_dump()
                    | {
                        "geometry_revision_id": geometry.id,
                        "face_ids": sorted(set(targets)),
                        "review_faces": [],
                    }
                )
            )
    return LoadSetup(assignments=assignments)


class EditRepository:
    def __init__(self, projects: Repository) -> None:
        self.projects = projects

    def _get(self, connection: Connection, owner: UUID, identifier: UUID) -> GeometryEdit:
        row = (
            connection.execute(
                text("SELECT * FROM geometry_edits WHERE id=:id"), {"id": str(identifier)}
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise not_found()
        self.projects._project(connection, owner, UUID(row["project_id"]))
        return GeometryEdit.model_validate_json(row["record_json"])

    def get(self, owner: UUID, identifier: UUID) -> GeometryEdit:
        with self.projects.database.engine.connect() as connection:
            return self._get(connection, owner, identifier)

    def _check(
        self, connection: Connection, owner: UUID, edit: GeometryEdit, expected: int
    ) -> None:
        project = self.projects._project(connection, owner, edit.project_id)
        source = self.projects._geometry(connection, owner, edit.source_geometry_id, project.id)
        if project.revision != expected or edit.project_revision != expected:
            raise stale_revision()
        if edit.request.analysis_id:
            analysis = self.projects._analysis(connection, owner, edit.request.analysis_id)
            if analysis.project_id != project.id or analysis.geometry_revision_id != source.id:
                raise DomainError(
                    422, "invalid_analysis", "Select an analysis pinned to this geometry"
                )
            if analysis.revision != edit.request.analysis_revision:
                raise stale_revision()

    def save(self, owner: UUID, edit: GeometryEdit) -> GeometryEdit:
        with self.projects.write() as connection:
            self._check(connection, owner, edit, edit.project_revision)
            connection.execute(
                text("INSERT INTO geometry_edits VALUES (:id,:project,:record)"),
                {
                    "id": str(edit.id),
                    "project": str(edit.project_id),
                    "record": edit.model_dump_json(),
                },
            )
        return edit

    def result(self, connection: Connection, owner: UUID, edit: GeometryEdit) -> EditResult:
        assert edit.result_geometry_id is not None
        return EditResult(
            project=self.projects._project(connection, owner, edit.project_id),
            geometry=self.projects._geometry(connection, owner, edit.result_geometry_id),
            analysis=self.projects._analysis(
                connection, owner, edit.request.analysis_id, edit.result_analysis_revision
            )
            if edit.request.analysis_id
            else None,
        )

    def commit(self, owner: UUID, identifier: UUID, source: UUID, expected: int) -> EditResult:
        with self.projects.write() as connection:
            edit = self._get(connection, owner, identifier)
            if edit.source_geometry_id != source:
                raise not_found()
            if edit.status == "committed":
                return self.result(connection, owner, edit)
            if edit.status != "ready" or edit.metadata is None or edit.preview is None:
                raise DomainError(
                    409, "edit_not_ready", "Create and review a successful cleanup preview first"
                )
            self._check(connection, owner, edit, expected)
            original = self.projects._geometry(connection, owner, source)
            # Verify a complete one-to-one map contract before trusting any assignment.
            mappings = edit.preview.mappings
            targets = [m.target_face_id for m in mappings if m.status == "unchanged"]
            if (
                len(mappings) != len(original.faces)
                or {m.source_face_id for m in mappings} != {f.id for f in original.faces}
                or len(set(targets)) != len(targets)
                or None in targets
                or not set(targets) <= {f.id for f in edit.metadata.faces}
                or any(m.target_face_id is not None for m in mappings if m.status != "unchanged")
                or len(original.bodies) != 1
                or len(edit.metadata.bodies) != 1
            ):
                raise DomainError(503, "invalid_edit_map", "Cleanup mapping failed verification")
            geometry = self._geometry(connection, owner, edit, edit.metadata, source)
            result_analysis_revision = None
            if edit.request.analysis_id:
                analysis = self.projects._analysis(connection, owner, edit.request.analysis_id)
                materials = self.projects._material_setup(
                    connection, analysis.id, analysis.revision
                )
                setup = materials.model_copy(
                    update={
                        "assignments": [
                            BodyMaterial(body_id=geometry.bodies[0].id, material=a.material)
                            for a in materials.assignments
                            if a.body_id == original.bodies[0].id
                        ]
                    }
                )
                loads = remap_loads(
                    edit,
                    geometry,
                    self.projects._load_setup(connection, analysis.id, analysis.revision),
                )
                self._analysis(
                    connection,
                    analysis.id,
                    analysis.project_id,
                    analysis.name,
                    analysis.revision + 1,
                    geometry.id,
                    setup,
                    loads,
                )
                result_analysis_revision = analysis.revision + 1
            edit = edit.model_copy(
                update={
                    "status": "committed",
                    "result_geometry_id": geometry.id,
                    "result_project_revision": expected + 1,
                    "result_analysis_revision": result_analysis_revision,
                }
            )
            self._update(connection, edit)
            return self.result(connection, owner, edit)

    def _geometry(
        self,
        connection: Connection,
        owner: UUID,
        edit: GeometryEdit,
        metadata: GeometryMetadata,
        parent: UUID,
    ) -> GeometryRevision:
        identifier, timestamp = uuid4(), now()
        connection.execute(
            text("INSERT INTO geometry_revisions VALUES (:id,:project,:parent,:metadata,:time)"),
            {
                "id": str(identifier),
                "project": str(edit.project_id),
                "parent": str(parent),
                "metadata": metadata.model_dump_json(),
                "time": timestamp,
            },
        )
        connection.execute(
            text("UPDATE projects SET revision=revision+1,updated_at=:time WHERE id=:id"),
            {"time": timestamp, "id": str(edit.project_id)},
        )
        return self.projects._geometry(connection, owner, identifier)

    def _analysis(
        self,
        connection: Connection,
        identifier: UUID,
        project: UUID,
        name: str,
        revision: int,
        geometry: UUID,
        materials: MaterialSetup,
        loads: LoadSetup,
        mesh: MeshSetup | None = None,
    ) -> None:
        timestamp = now()
        self.projects._insert_analysis_revision(
            connection,
            identifier,
            project,
            revision,
            AnalysisCreate(name=name, geometry_revision_id=geometry),
            timestamp,
            materials,
            loads,
            mesh,
        )
        connection.execute(
            text("UPDATE analyses SET head_revision=:revision,updated_at=:time WHERE id=:id"),
            {"revision": revision, "time": timestamp, "id": str(identifier)},
        )

    @staticmethod
    def _update(connection: Connection, edit: GeometryEdit) -> None:
        connection.execute(
            text("UPDATE geometry_edits SET record_json=:record WHERE id=:id"),
            {"record": edit.model_dump_json(), "id": str(edit.id)},
        )

    def undo(self, owner: UUID, identifier: UUID, expected: int) -> EditResult:
        with self.projects.write() as connection:
            edit = self._get(connection, owner, identifier)
            if edit.status == "undone":
                return self.result(connection, owner, edit)
            if edit.status != "committed":
                raise DomainError(409, "undo_unavailable", "Only an applied cleanup can be undone")
            project = self.projects._project(connection, owner, edit.project_id)
            if project.revision != expected or expected != edit.result_project_revision:
                raise stale_revision()
            if edit.request.analysis_id:
                analysis = self.projects._analysis(connection, owner, edit.request.analysis_id)
                if (
                    analysis.revision != edit.result_analysis_revision
                    or analysis.geometry_revision_id != edit.result_geometry_id
                ):
                    raise stale_revision()
            source = self.projects._geometry(connection, owner, edit.source_geometry_id)
            fields = source.model_dump(include=set(GeometryMetadata.model_fields))
            fields["edit_recipe"] = {
                "operation": "undo_cleanup",
                "edit_id": str(edit.id),
                "restored_geometry_id": str(source.id),
            }
            assert edit.result_geometry_id is not None
            geometry = self._geometry(
                connection,
                owner,
                edit,
                GeometryMetadata.model_validate(fields),
                edit.result_geometry_id,
            )
            result_analysis_revision = None
            if edit.request.analysis_id:
                assert edit.request.analysis_revision is not None
                previous = self.projects._analysis(
                    connection, owner, edit.request.analysis_id, edit.request.analysis_revision
                )
                setup = self.projects._material_setup(connection, previous.id, previous.revision)
                loads = self.projects._load_setup(connection, previous.id, previous.revision)
                loads = loads.model_copy(
                    update={
                        "assignments": [
                            a.model_copy(update={"geometry_revision_id": geometry.id})
                            if not a.review_faces and not a.review_bodies
                            else a
                            for a in loads.assignments
                        ]
                    }
                )
                mesh = self.projects._mesh_setup(connection, previous.id, previous.revision)
                if mesh.geometry_revision_id == source.id:
                    mesh = mesh.model_copy(update={"geometry_revision_id": geometry.id})
                self._analysis(
                    connection,
                    previous.id,
                    previous.project_id,
                    previous.name,
                    analysis.revision + 1,
                    geometry.id,
                    setup,
                    loads,
                    mesh,
                )
                result_analysis_revision = analysis.revision + 1
            edit = edit.model_copy(
                update={
                    "status": "undone",
                    "result_geometry_id": geometry.id,
                    "result_project_revision": expected + 1,
                    "result_analysis_revision": result_analysis_revision,
                }
            )
            self._update(connection, edit)
            return self.result(connection, owner, edit)
