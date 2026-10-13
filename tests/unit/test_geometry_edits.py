"""Conservative remapping, stale/owned publication and immutable undo transactions."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.domain.edits import EditCreate, EditPreview, FaceMapping, GeometryEdit
from app.domain.errors import DomainError
from app.domain.loads import LoadAssignment, load_state
from app.domain.materials import MaterialSetup
from app.domain.models import AnalysisCreate, GeometryMetadata, ProjectCreate
from app.persistence.database import Database
from app.persistence.edits import EditRepository, remap_loads
from app.persistence.repository import Repository


def metadata(digest: str) -> GeometryMetadata:
    return GeometryMetadata.model_validate(
        {
            "source_sha256": "a" * 64,
            "brep_sha256": digest * 64,
            "units": {"source_length_unit": "m", "confirmed": True},
            "bodies": [{"id": f"{digest}:b1"}],
            "faces": [
                {
                    "id": f"{digest}:f{i}",
                    "body_id": f"{digest}:b1",
                    "signature": {
                        "area_m2": 1,
                        "center_m": [0, 0, 0],
                        "surface_type": "GeomAbs_Plane",
                    },
                }
                for i in range(1, 4)
            ],
            "validation": {"synthetic_metadata_only": True},
        }
    )


@pytest.fixture
def fixture(tmp_path: Path) -> tuple[Repository, EditRepository, UUID, GeometryEdit]:
    database = Database(tmp_path / "metadata.sqlite3")
    database.migrate()
    store = Repository(database)
    owner = store.local_owner()
    project = store.create_project(owner, ProjectCreate(name="Synthetic mapping"))
    source = store.register_geometry(owner, project.id, 1, metadata("b"))
    analysis = store.create_analysis(
        owner, project.id, 2, AnalysisCreate(name="Original", geometry_revision_id=source.id)
    )
    assignment = LoadAssignment(
        id=uuid4(),
        name="Total force",
        kind="force",
        geometry_revision_id=source.id,
        face_ids=["b:f1", "b:f2"],
        force_n=(123, -456, 789),
        source_units="m-N-Pa",
        source_force=(123, -456, 789),
    )
    store.edit_loads(owner, analysis.id, 1, assignment)
    request = EditCreate(
        operation="remove_feature", face_id="b:f3", analysis_id=analysis.id, analysis_revision=2
    )
    edit = GeometryEdit(
        id=uuid4(),
        project_id=project.id,
        project_revision=2,
        source_geometry_id=source.id,
        request=request,
        status="ready",
        metadata=metadata("c"),
        preview=EditPreview(
            feature="hole",
            original_volume_m3=0.97,
            preview_volume_m3=1,
            volume_delta_m3=0.03,
            expected_delta_m3=0.03,
            mappings=[
                FaceMapping(
                    source_face_id=f"b:f{i}",
                    target_face_id=f"c:f{i}" if i == 1 else None,
                    status="unchanged" if i == 1 else "changed_or_ambiguous",
                )
                for i in range(1, 4)
            ],
        ),
    )
    EditRepository(store).save(owner, edit)
    return store, EditRepository(store), owner, edit


@pytest.mark.parametrize("status", ["removed", "changed_or_ambiguous"])
def test_partial_split_merged_removed_selection_keeps_entire_force_blocked(
    fixture: tuple[Repository, EditRepository, UUID, GeometryEdit],
    status: Literal["removed", "changed_or_ambiguous"],
) -> None:
    store, repo, owner, edit = fixture
    assert edit.preview and edit.request.analysis_id
    mappings = [
        FaceMapping(source_face_id="b:f1", target_face_id="c:f1", status="unchanged"),
        FaceMapping(source_face_id="b:f2", target_face_id=None, status=status),
    ]
    changed = edit.model_copy(
        update={"preview": edit.preview.model_copy(update={"mappings": mappings})}
    )
    geometry = store.get_geometry(owner, edit.source_geometry_id)
    inputs = store.load_inputs(owner, edit.request.analysis_id)
    remapped = remap_loads(changed, geometry, inputs[3])
    assert remapped.assignments[0].face_ids == ["b:f1", "b:f2"]
    assert remapped.assignments[0].force_n == (123, -456, 789)
    assert remapped.assignments[0].review_faces == ["b:f2"]
    state = load_state(inputs[0], geometry, MaterialSetup(), remapped, None)
    assert any("b:f2" in b for b in state.blockers)
    assert not state.markers and not state.previews and state.total_force_n == (0, 0, 0)


def test_undo_restores_setup_append_only_and_refuses_subsequent_analysis_edits(
    fixture: tuple[Repository, EditRepository, UUID, GeometryEdit],
) -> None:
    store, repo, owner, edit = fixture
    assert edit.request.analysis_id
    before = store.load_inputs(owner, edit.request.analysis_id)
    applied = repo.commit(owner, edit.id, edit.source_geometry_id, 2)
    assert applied.analysis and applied.analysis.revision == 3
    assert store.load_inputs(owner, edit.request.analysis_id)[3].assignments[0].review_faces == [
        "b:f2"
    ]
    undone = repo.undo(owner, edit.id, 3)
    assert undone.analysis and undone.analysis.revision == 4
    after = store.load_inputs(owner, edit.request.analysis_id)
    assert after[1] and after[1].brep_sha256 == before[1].brep_sha256  # type: ignore[union-attr]
    assert after[3].assignments[0].face_ids == before[3].assignments[0].face_ids
    assert store.load_inputs(owner, edit.request.analysis_id, 2) == before
    assert repo.undo(owner, edit.id, 3) == undone


@pytest.mark.parametrize("change", ["project", "analysis", "delete"])
def test_preview_commit_refuses_stale_or_deleted_sources(
    fixture: tuple[Repository, EditRepository, UUID, GeometryEdit], change: str
) -> None:
    store, repo, owner, edit = fixture
    if change in ("project", "delete"):
        store.edit_project(
            owner,
            edit.project_id,
            2,
            ProjectCreate(name="Changed") if change == "project" else None,
        )
    else:
        assert edit.request.analysis_id
        store.edit_material_setup(owner, edit.request.analysis_id, 2, display_units="m-N-Pa")
    with pytest.raises(DomainError) as failure:
        repo.commit(owner, edit.id, edit.source_geometry_id, 2)
    assert failure.value.status == (404 if change == "delete" else 409)


@pytest.mark.parametrize("mapping", ["duplicate_target", "missing_source", "unverified_target"])
def test_bad_split_merged_mapping_contract_refuses_publication(
    fixture: tuple[Repository, EditRepository, UUID, GeometryEdit], mapping: str
) -> None:
    store, repo, owner, edit = fixture
    assert edit.preview
    maps = list(edit.preview.mappings)
    if mapping == "duplicate_target":
        maps[1] = FaceMapping(source_face_id="b:f2", target_face_id="c:f1", status="unchanged")
    elif mapping == "missing_source":
        maps.pop()
    else:
        maps[1] = FaceMapping(
            source_face_id="b:f2", target_face_id="c:f2", status="changed_or_ambiguous"
        )
    changed = edit.model_copy(
        update={"preview": edit.preview.model_copy(update={"mappings": maps})}
    )
    with store.write() as connection:
        connection.execute(
            text("UPDATE geometry_edits SET record_json=:record WHERE id=:id"),
            {"record": changed.model_dump_json(), "id": str(edit.id)},
        )
    with pytest.raises(DomainError) as failure:
        repo.commit(owner, edit.id, edit.source_geometry_id, 2)
    assert failure.value.code == "invalid_edit_map"
    assert store.list_geometry(owner, edit.project_id, 0, 10).total == 1


def test_ownership_wrong_parent_and_concurrent_apply_are_guarded(
    fixture: tuple[Repository, EditRepository, UUID, GeometryEdit],
) -> None:
    store, repo, owner, edit = fixture
    for who, source in [(uuid4(), edit.source_geometry_id), (owner, uuid4())]:
        with pytest.raises(DomainError) as failure:
            repo.commit(who, edit.id, source, 2)
        assert failure.value.status == 404
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: repo.commit(owner, edit.id, edit.source_geometry_id, 2), range(2))
        )
    assert results[0] == results[1]
    assert store.list_geometry(owner, edit.project_id, 0, 10).total == 2
    assert edit.request.analysis_id
    store.edit_material_setup(owner, edit.request.analysis_id, 3, display_units="m-N-Pa")
    with pytest.raises(DomainError) as failure:
        repo.undo(owner, edit.id, 3)
    assert failure.value.status == 409


def test_populated_migration_downgrade_reupgrade_preserves_original_history(tmp_path: Path) -> None:
    database = Database(tmp_path / "legacy.sqlite3")
    database.migrate("0005_local_jobs")
    store = Repository(database)
    owner = store.local_owner()
    project = store.create_project(owner, ProjectCreate(name="Existing"))
    geometry = store.register_geometry(owner, project.id, 1, metadata("b"))
    database.migrate()
    assert store.get_geometry(owner, geometry.id) == geometry
    database.migrate("0005_local_jobs", downgrade=True)
    assert store.get_geometry(owner, geometry.id) == geometry
    database.migrate()
    assert store.get_geometry(owner, geometry.id) == geometry


@pytest.mark.parametrize(
    "fields",
    [
        {"analysis_id": str(uuid4())},
        {"analysis_revision": 1},
        {"operation": "repair"},
        {"face_id": "../bad", "command": "exec"},
    ],
)
def test_edit_contract_refuses_unpaired_or_executable_requests(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        EditCreate.model_validate({"operation": "remove_feature", "face_id": "body:face"} | fields)
