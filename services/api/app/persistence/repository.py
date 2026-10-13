"""Ownership and optimistic revisions enforced inside the same write transaction."""

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.domain.errors import DomainError, not_found, stale_revision
from app.domain.materials import (
    BodyMaterial,
    MaterialSetup,
    MaterialSnapshot,
    MaterialState,
    body_status,
)
from app.domain.models import (
    Analysis,
    AnalysisCreate,
    AnalysisPage,
    AnalysisPatch,
    GeometryMetadata,
    GeometryPage,
    GeometryRevision,
    Project,
    ProjectCreate,
    ProjectPage,
)
from app.domain.units import PresetID
from app.persistence.database import Database


def now() -> str:
    return datetime.now(UTC).isoformat()


class Repository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @contextmanager
    def write(self) -> Iterator[Connection]:
        with self.database.engine.connect().execution_options(sqlite_immediate=True) as connection:
            with connection.begin():
                yield connection

    def local_owner(self) -> UUID:
        with self.write() as connection:
            owner = connection.execute(
                text("SELECT id FROM users WHERE local_identity='single-user'")
            ).scalar_one_or_none()
            if owner is None:
                owner = str(uuid4())
                connection.execute(
                    text("INSERT INTO users VALUES (:id, 'single-user', :created)"),
                    {"id": owner, "created": now()},
                )
            return UUID(owner)

    def _project(self, connection: Connection, owner: UUID, project: UUID) -> Project:
        row = (
            connection.execute(
                text("""SELECT id, owner_id, name, revision, created_at, updated_at FROM projects
                    WHERE id=:id AND owner_id=:owner AND deleted_at IS NULL"""),
                {"id": str(project), "owner": str(owner)},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise not_found()
        return Project.model_validate(dict(row))

    def create_project(self, owner: UUID, payload: ProjectCreate) -> Project:
        identifier, timestamp = uuid4(), now()
        with self.write() as connection:
            connection.execute(
                text("""INSERT INTO projects
                        (id, owner_id, name, revision, created_at, updated_at)
                        VALUES (:id, :owner, :name, 1, :timestamp, :timestamp)"""),
                {
                    "id": str(identifier),
                    "owner": str(owner),
                    "name": payload.name,
                    "timestamp": timestamp,
                },
            )
            return self._project(connection, owner, identifier)

    def get_project(self, owner: UUID, project: UUID) -> Project:
        with self.database.engine.connect() as connection:
            return self._project(connection, owner, project)

    def list_projects(self, owner: UUID, offset: int, limit: int) -> ProjectPage:
        with self.database.engine.connect() as connection:
            parameters = {"owner": str(owner), "offset": offset, "limit": limit}
            total = connection.execute(
                text("SELECT count(*) FROM projects WHERE owner_id=:owner AND deleted_at IS NULL"),
                parameters,
            ).scalar_one()
            rows = connection.execute(
                text("""SELECT id, owner_id, name, revision, created_at, updated_at FROM projects
                        WHERE owner_id=:owner AND deleted_at IS NULL
                        ORDER BY created_at, id LIMIT :limit OFFSET :offset"""),
                parameters,
            ).mappings()
            return ProjectPage(
                items=[Project.model_validate(dict(row)) for row in rows],
                total=total,
                offset=offset,
                limit=limit,
            )

    def edit_project(
        self, owner: UUID, project: UUID, expected: int, payload: ProjectCreate | None
    ) -> Project | None:
        with self.write() as connection:
            current = self._project(connection, owner, project)
            if current.revision != expected:
                raise stale_revision()
            timestamp = now()
            connection.execute(
                text("""UPDATE projects SET name=:name, revision=revision+1,
                        updated_at=:timestamp, deleted_at=:deleted WHERE id=:id"""),
                {
                    "id": str(project),
                    "name": payload.name if payload else current.name,
                    "timestamp": timestamp,
                    "deleted": None if payload else timestamp,
                },
            )
            return self._project(connection, owner, project) if payload else None

    def register_geometry(
        self,
        owner: UUID,
        project: UUID,
        expected: int,
        metadata: GeometryMetadata,
        parent: UUID | None = None,
    ) -> GeometryRevision:
        """Internal CAD-adapter boundary, not a browser metadata-registration endpoint.

        T008 must verify artifact bytes/hashes and native validity before calling this.
        Metadata persistence alone makes no CAD validation claim.
        """
        identifier, timestamp = uuid4(), now()
        with self.write() as connection:
            current = self._project(connection, owner, project)
            if current.revision != expected:
                raise stale_revision()
            if parent is not None:
                self._geometry(connection, owner, parent, project)
            connection.execute(
                text("""INSERT INTO geometry_revisions VALUES
                        (:id, :project, :parent, :metadata, :timestamp)"""),
                {
                    "id": str(identifier),
                    "project": str(project),
                    "parent": str(parent) if parent else None,
                    "timestamp": timestamp,
                    "metadata": json.dumps(
                        metadata.model_dump(mode="json"),
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                },
            )
            connection.execute(
                text("UPDATE projects SET revision=revision+1, updated_at=:time WHERE id=:id"),
                {"id": str(project), "time": timestamp},
            )
            return self._geometry(connection, owner, identifier, project)

    @staticmethod
    def _geometry_model(row: Mapping[str, Any]) -> GeometryRevision:
        fields = dict(row)
        return GeometryRevision.model_validate(json.loads(fields.pop("metadata_json")) | fields)

    def _geometry(
        self, connection: Connection, owner: UUID, geometry: UUID, project: UUID | None = None
    ) -> GeometryRevision:
        row = (
            connection.execute(
                text("""SELECT g.* FROM geometry_revisions g JOIN projects p ON p.id=g.project_id
                    WHERE g.id=:id AND p.owner_id=:owner AND p.deleted_at IS NULL
                    AND (:project IS NULL OR p.id=:project)"""),
                {
                    "id": str(geometry),
                    "owner": str(owner),
                    "project": str(project) if project else None,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise not_found()
        return self._geometry_model(dict(row))

    def get_geometry(self, owner: UUID, geometry: UUID) -> GeometryRevision:
        with self.database.engine.connect() as connection:
            return self._geometry(connection, owner, geometry)

    def list_geometry(self, owner: UUID, project: UUID, offset: int, limit: int) -> GeometryPage:
        with self.database.engine.connect() as connection:
            self._project(connection, owner, project)
            params = {"project": str(project), "offset": offset, "limit": limit}
            total = connection.execute(
                text("SELECT count(*) FROM geometry_revisions WHERE project_id=:project"), params
            ).scalar_one()
            rows = connection.execute(
                text("""SELECT * FROM geometry_revisions WHERE project_id=:project
                        ORDER BY created_at, id LIMIT :limit OFFSET :offset"""),
                params,
            ).mappings()
            return GeometryPage(
                items=[self._geometry_model(dict(row)) for row in rows],
                total=total,
                offset=offset,
                limit=limit,
            )

    def _analysis(
        self, connection: Connection, owner: UUID, analysis: UUID, revision: int | None = None
    ) -> Analysis:
        row = (
            connection.execute(
                text("""SELECT a.id, a.project_id, a.created_at, r.created_at AS updated_at,
                           r.name, r.geometry_revision_id, r.revision
                    FROM analyses a JOIN projects p ON p.id=a.project_id
                    JOIN analysis_revisions r ON r.analysis_id=a.id
                    AND r.revision=coalesce(:revision, a.head_revision)
                    WHERE a.id=:id AND p.owner_id=:owner AND p.deleted_at IS NULL"""),
                {"id": str(analysis), "owner": str(owner), "revision": revision},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise not_found()
        return Analysis.model_validate(dict(row))

    def create_analysis(
        self, owner: UUID, project: UUID, expected: int, payload: AnalysisCreate
    ) -> Analysis:
        identifier, timestamp = uuid4(), now()
        with self.write() as connection:
            current = self._project(connection, owner, project)
            if current.revision != expected:
                raise stale_revision()
            if payload.geometry_revision_id is not None:
                self._geometry(connection, owner, payload.geometry_revision_id, project)
            connection.execute(
                text("INSERT INTO analyses VALUES (:id, :project, 1, :time, :time)"),
                {"id": str(identifier), "project": str(project), "time": timestamp},
            )
            self._insert_analysis_revision(connection, identifier, project, 1, payload, timestamp)
            return self._analysis(connection, owner, identifier)

    @staticmethod
    def _insert_analysis_revision(
        connection: Connection,
        analysis: UUID,
        project: UUID,
        revision: int,
        payload: AnalysisCreate,
        timestamp: str,
        setup: MaterialSetup | None = None,
    ) -> None:
        connection.execute(
            text("""INSERT INTO analysis_revisions VALUES
                    (:id, :project, :revision, :name, :geometry, :time)"""),
            {
                "id": str(analysis),
                "project": str(project),
                "revision": revision,
                "name": payload.name,
                "time": timestamp,
                "geometry": str(payload.geometry_revision_id)
                if payload.geometry_revision_id
                else None,
            },
        )
        if setup is None:
            setup = Repository._material_setup(connection, analysis, revision - 1)
        connection.execute(
            text("INSERT INTO analysis_material_setups VALUES (:id, :revision, :setup)"),
            {"id": str(analysis), "revision": revision, "setup": setup.model_dump_json()},
        )

    @staticmethod
    def _material_setup(connection: Connection, analysis: UUID, revision: int) -> MaterialSetup:
        raw = connection.execute(
            text(
                "SELECT setup_json FROM analysis_material_setups "
                "WHERE analysis_id=:id AND revision=:revision"
            ),
            {"id": str(analysis), "revision": revision},
        ).scalar_one_or_none()
        # T007/T008 revisions predate material editing; their empty setup is explicit.
        return MaterialSetup.model_validate_json(raw) if raw is not None else MaterialSetup()

    def _material_state(
        self, connection: Connection, owner: UUID, analysis: Analysis
    ) -> MaterialState:
        setup = self._material_setup(connection, analysis.id, analysis.revision)
        bodies = []
        if analysis.geometry_revision_id is not None:
            geometry = self._geometry(
                connection, owner, analysis.geometry_revision_id, analysis.project_id
            )
            assigned = {item.body_id: item.material for item in setup.assignments}
            bodies = [body_status(body.id, assigned.get(body.id)) for body in geometry.bodies]
        return MaterialState(
            analysis_id=analysis.id,
            analysis_revision=analysis.revision,
            geometry_revision_id=analysis.geometry_revision_id,
            setup=setup,
            bodies=bodies,
        )

    def get_material_state(
        self, owner: UUID, analysis: UUID, revision: int | None = None
    ) -> MaterialState:
        with self.database.engine.connect() as connection:
            return self._material_state(
                connection, owner, self._analysis(connection, owner, analysis, revision)
            )

    def edit_material_setup(
        self,
        owner: UUID,
        analysis: UUID,
        expected: int,
        *,
        display_units: PresetID | None = None,
        body: str | None = None,
        material: MaterialSnapshot | None = None,
    ) -> MaterialState:
        with self.write() as connection:
            current = self._analysis(connection, owner, analysis)
            if current.revision != expected:
                raise stale_revision()
            previous = self._material_setup(connection, analysis, expected)
            assignments = list(previous.assignments)
            if body is not None:
                if current.geometry_revision_id is None:
                    raise DomainError(
                        409,
                        "geometry_required",
                        "Create an analysis pinned to accepted geometry before assigning materials",
                    )
                geometry = self._geometry(
                    connection, owner, current.geometry_revision_id, current.project_id
                )
                if body not in {b.id for b in geometry.bodies}:
                    raise DomainError(
                        422,
                        "invalid_body",
                        "This body does not belong to the analysis geometry revision",
                    )
                assignments = [item for item in assignments if item.body_id != body]
                if material is not None:
                    assignments.append(BodyMaterial(body_id=body, material=material))
            # Unit-only updates copy every SI value and original source field verbatim.
            setup = MaterialSetup.model_validate(
                {
                    "display_units": display_units or previous.display_units,
                    "assignments": sorted(assignments, key=lambda item: item.body_id),
                }
            )
            timestamp = now()
            self._insert_analysis_revision(
                connection,
                analysis,
                current.project_id,
                expected + 1,
                AnalysisCreate(
                    name=current.name, geometry_revision_id=current.geometry_revision_id
                ),
                timestamp,
                setup,
            )
            connection.execute(
                text(
                    "UPDATE analyses SET head_revision=head_revision+1, "
                    "updated_at=:time WHERE id=:id"
                ),
                {"id": str(analysis), "time": timestamp},
            )
            return self._material_state(
                connection, owner, self._analysis(connection, owner, analysis)
            )

    def get_analysis(self, owner: UUID, analysis: UUID, revision: int | None = None) -> Analysis:
        with self.database.engine.connect() as connection:
            return self._analysis(connection, owner, analysis, revision)

    def list_analyses(self, owner: UUID, project: UUID, offset: int, limit: int) -> AnalysisPage:
        with self.database.engine.connect() as connection:
            self._project(connection, owner, project)
            params = {"project": str(project), "limit": limit, "offset": offset}
            total = connection.execute(
                text("SELECT count(*) FROM analyses WHERE project_id=:project"), params
            ).scalar_one()
            ids = connection.execute(
                text("""SELECT id FROM analyses WHERE project_id=:project
                        ORDER BY created_at, id LIMIT :limit OFFSET :offset"""),
                params,
            ).scalars()
            return AnalysisPage(
                items=[self._analysis(connection, owner, UUID(i)) for i in ids],
                total=total,
                offset=offset,
                limit=limit,
            )

    def edit_analysis(
        self, owner: UUID, analysis: UUID, expected: int, payload: AnalysisPatch
    ) -> Analysis:
        with self.write() as connection:
            current = self._analysis(connection, owner, analysis)
            if current.revision != expected:
                raise stale_revision()
            timestamp = now()
            self._insert_analysis_revision(
                connection,
                analysis,
                current.project_id,
                expected + 1,
                AnalysisCreate(
                    name=payload.name, geometry_revision_id=current.geometry_revision_id
                ),
                timestamp,
            )
            connection.execute(
                text("""UPDATE analyses SET head_revision=head_revision+1,
                        updated_at=:time WHERE id=:id"""),
                {"id": str(analysis), "time": timestamp},
            )
            return self._analysis(connection, owner, analysis)
