"""Metadata-only queue races, fencing, immutable inputs and owned API reads."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.domain.deck_service import canonical
from app.domain.errors import DomainError
from app.domain.jobs import JobInput
from app.domain.loads import DeckSnapshot
from app.domain.models import AnalysisPatch
from app.persistence.database import Database
from app.persistence.jobs import JobRepository
from app.persistence.repository import Repository
from tests.unit import test_materials as material_tests
from tests.unit.test_face_loads import fixture
from worker.local_solve import validate_outputs

application = material_tests.application
client = material_tests.client


def queued(client: TestClient, application: FastAPI) -> tuple[JobRepository, UUID, JobInput]:
    # No native job is launched in these pure state-machine/transaction tests.
    application.state.local_worker.close()
    path, _ = fixture(client, application)
    owner = application.state.owner
    analysis, geometry, materials, loads = application.state.repository.load_inputs(
        owner, UUID(path.split("/")[-1])
    )
    assert geometry is not None
    inputs = JobInput(
        kind="mesh",
        snapshot=DeckSnapshot(
            analysis=analysis, geometry=geometry, materials=materials, loads=loads
        ),
        display=application.state.import_service.display(owner, geometry.id, "coarse"),
        policy={"fixture": "metadata-only; not executable or numerical evidence"},
    )
    return application.state.job_service.repository, owner, inputs


def enqueue(
    store: JobRepository,
    owner: UUID,
    inputs: JobInput,
    key: UUID | None = None,
    request: str = "a" * 64,
) -> Any:
    return store.enqueue(
        owner,
        key or uuid4(),
        request,
        uuid4(),
        inputs,
        hashlib.sha256(canonical(inputs.model_dump(mode="json"))).hexdigest(),
    )


def test_idempotency_race_admits_one_job_and_payload_conflicts(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    key = uuid4()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: enqueue(store, owner, inputs, key), range(6)))
    assert len({job.id for job in results}) == 1
    assert len(store.list_jobs(owner, inputs.snapshot.analysis.id)) == 1
    with pytest.raises(DomainError) as error:
        enqueue(store, owner, inputs, key, "b" * 64)
    assert error.value.code == "idempotency_conflict"
    assert store.existing(owner, key, "a" * 64) is not None


def test_competing_claims_one_winner_fifo_and_stale_attempt_cannot_publish(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    first, second = enqueue(store, owner, inputs), enqueue(store, owner, inputs)
    with ThreadPoolExecutor(max_workers=6) as pool:
        winners = [r for r in pool.map(lambda _: store.claim(uuid4()), range(6)) if r is not None]
    assert len(winners) == 1 and winners[0][0].id == first.id
    _, token, _ = winners[0]
    with pytest.raises(DomainError, match="stale attempt"):
        store.finish(first.id, uuid4(), "failed", "wrong", "Wrong worker", {}, {})
    with pytest.raises(ValueError, match="complete frozen artifact"):
        store.finish(first.id, token, "succeeded", None, None, {}, {})
    assert store.get(owner, first.id).status == "running"
    store.finish(
        first.id, token, "failed", "synthetic_state_test", "Metadata-only state fixture", {}, {}
    )
    next_job = store.claim(uuid4())
    assert next_job is not None and next_job[0].id == second.id


def test_cancel_queued_and_running_is_idempotent_and_requires_death_ack(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    first = enqueue(store, owner, inputs)
    assert store.cancel(owner, first.id).status == "cancelled"
    assert store.cancel(owner, first.id).status == "cancelled"
    assert store.claim(uuid4()) is None
    second = enqueue(store, owner, inputs)
    claim = store.claim(uuid4())
    assert claim is not None
    token = claim[1]
    requested = store.cancel(owner, second.id)
    assert requested.status == "cancelling" and requested.finished_at is None
    assert store.control(second.id, token)
    # The process supervisor, not a browser timer, supplies terminal acknowledgment.
    store.finish(second.id, token, "failed", "synthetic_state_test", None, {}, {})
    final = store.get(owner, second.id)
    assert final.status == "cancelled" and final.finished_at is not None
    assert [e.sequence for e in final.events] == [1, 2, 3, 4]


def test_cancel_completion_race_has_one_terminal_state(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    job = enqueue(store, owner, inputs)
    claimed = store.claim(uuid4())
    assert claimed is not None

    def finish() -> str:
        store.finish(job.id, claimed[1], "failed", "synthetic_state_test", None, {}, {})
        return "finished"

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(store.cancel, owner, job.id)
        finish_future = pool.submit(finish)
        cancel_future.result()
        assert finish_future.result() == "finished"
    final = store.get(owner, job.id)
    assert final.status in ("cancelled", "failed") and final.finished_at


def test_frozen_input_and_terminal_rows_are_immutable_and_survive_edits(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    job = enqueue(store, owner, inputs)
    store.projects.edit_analysis(
        owner, inputs.snapshot.analysis.id, 1, AnalysisPatch(name="Edited later")
    )
    assert store.inputs(owner, job.id) == inputs
    assert store.get(owner, job.id).analysis_revision == 1
    with store.projects.write() as connection:
        for sql in (
            "UPDATE local_job_inputs SET input_json='{}'",
            "DELETE FROM local_job_inputs",
            "UPDATE local_job_events SET status='succeeded'",
            "DELETE FROM local_job_events",
            "UPDATE local_jobs SET input_sha256='bad'",
            "DELETE FROM local_jobs",
        ):
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql(sql)
    store.cancel(owner, job.id)
    with store.projects.write() as connection:
        with pytest.raises(IntegrityError, match="terminal job"):
            connection.exec_driver_sql("UPDATE local_jobs SET status='running'")


def test_owner_csrf_tombstone_reads_and_queued_delete_cancellation(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    job = enqueue(store, owner, inputs)
    with pytest.raises(DomainError) as inaccessible:
        store.get(uuid4(), job.id)
    assert inaccessible.value.status == 404
    response = client.post(
        f"/api/v1/jobs/{job.id}/cancel", headers={"X-CSRF-Token": "wrong"}, json={}
    )
    assert response.status_code == 403
    assert client.get(f"/api/v1/jobs/{job.id}").status_code == 200
    store.projects.edit_project(owner, job.project_id, 2, None)
    for suffix in ("", "/events", "/mesh-display", "/artifacts/snapshot.json"):
        assert client.get(f"/api/v1/jobs/{job.id}" + suffix).status_code == 404
    assert client.post(f"/api/v1/jobs/{job.id}/cancel", json={}).status_code == 404
    with store.projects.database.engine.connect() as connection:
        row = store.row(connection, job.id)
        assert row["status"] == "cancelled" and row["cancel_requested"]


def test_global_pending_queue_cap_and_stale_admission(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    for _ in range(20):
        enqueue(store, owner, inputs)
    with pytest.raises(DomainError) as full:
        enqueue(store, owner, inputs)
    assert full.value.code == "queue_full"
    store.projects.edit_analysis(
        owner, inputs.snapshot.analysis.id, 1, AnalysisPatch(name="New revision")
    )
    with pytest.raises(DomainError) as stale:
        enqueue(store, owner, inputs)
    assert stale.value.code == "stale_revision"


def test_public_admission_headers_and_unsupported_payloads_refuse_before_native(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    path = f"/api/v1/analyses/{inputs.snapshot.analysis.id}"
    headers = {"If-Match": '"1"', "Idempotency-Key": str(uuid4())}
    assert client.post(path + "/mesh-jobs", json={}, headers={"If-Match": '"1"'}).status_code == 428
    assert (
        client.post(
            path + "/mesh-jobs", json={}, headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == 428
    )
    assert (
        client.post(
            path + "/mesh-jobs", json={}, headers={"If-Match": '"1"', "Idempotency-Key": "bad"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            path + "/mesh-jobs", json={"native_command": "untrusted"}, headers=headers
        ).status_code
        == 422
    )
    assert client.post(path + "/runs", json={}, headers=headers).status_code == 422
    assert (
        client.post(
            path + "/runs",
            json={"mesh_job_id": str(uuid4()), "raw_deck": "untrusted"},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.post(
            path + "/mesh-jobs", json={}, headers=headers | {"X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    assert (
        client.post(path + "/mesh-jobs", json={}, headers=headers).json()["code"]
        == "setup_incomplete"
    )
    assert store.list_jobs(owner, inputs.snapshot.analysis.id) == []


def test_populated_queue_migration_reverses_without_mutating_analysis(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    enqueue(store, owner, inputs)
    database = store.projects.database
    original = store.projects.get_analysis(owner, inputs.snapshot.analysis.id)
    database.migrate("0004_loads_decks", downgrade=True)
    database.migrate()
    assert store.projects.get_analysis(owner, original.id) == original
    assert store.list_jobs(owner, original.id) == []


@pytest.mark.parametrize(
    ("returncode", "transcript"),
    [
        (7, "Job finished\nnumber of equations: 1\n"),
        (0, "number of equations: 1\n"),
        (0, "*ERROR invalid solve\nJob finished\nnumber of equations: 1\n"),
        (0, "singular matrix\nJob finished\nnumber of equations: 1\n"),
        (0, "Job finished\nnumber of equations: 0\n"),
        (0, "Job finished\nnumber of equations: 1\n"),
        pytest.param(
            0,
            "Job finished\nnumber of equations:" + " " * 250000 + "invalid\n",
            id="bounded-whitespace-log",
        ),
    ],
)
def test_solver_exit_zero_alone_cannot_credit_success(
    tmp_path: Path, returncode: int, transcript: str
) -> None:
    (tmp_path / "solver.log").write_text(transcript)
    from tests.unit.test_quadratic import POINTS

    mesh = {
        "nodes": POINTS,
        "elements": {1: tuple(range(1, 11))},
        "owners": {1: "body"},
        "revision": "synthetic-metadata-only",
    }
    with pytest.raises(ValueError):
        validate_outputs(
            tmp_path, mesh, {"body": "M1"}, {"returncode": returncode}, "a" * 64, "b" * 64, "c" * 64
        )


def test_populated_migration_round_trip_keeps_prior_analysis(tmp_path: Path) -> None:
    database = Database(tmp_path / "migration.sqlite3")
    try:
        database.migrate("0004_loads_decks")
        from app.domain.models import AnalysisCreate, ProjectCreate

        store = Repository(database)
        owner = store.local_owner()
        project = store.create_project(owner, ProjectCreate(name="Before jobs"))
        analysis = store.create_analysis(owner, project.id, 1, AnalysisCreate(name="Saved"))
        database.migrate()
        assert JobRepository(store).list_jobs(owner, analysis.id) == []
        database.migrate("0004_loads_decks", downgrade=True)
        database.migrate()
        assert store.get_analysis(owner, analysis.id) == analysis
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    finally:
        database.close()
