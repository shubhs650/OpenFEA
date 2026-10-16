"""Durable retry ceilings, stale publications, cancellation and migrated history."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain.errors import DomainError
from tests.unit import test_local_queue as queue_tests

application = queue_tests.application
client = queue_tests.client
enqueue, queued = queue_tests.enqueue, queue_tests.queued


def test_retry_has_one_deadline_and_fences_every_old_publication(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    job = enqueue(store, owner, inputs)
    first = store.claim(uuid4())
    assert first is not None
    deadline = first[0].deadline_at
    store.finish(
        job.id,
        first[1],
        "interrupted",
        "worker_interrupted",
        None,
        {"mesh_attempt": 2},
        {},
        retry=True,
    )
    between = store.get(owner, job.id)
    assert between.status == "queued" and between.summary["mesh_attempt"] == 2
    second = store.claim(uuid4())
    assert second is not None and second[0].id == job.id and second[1] != first[1]
    assert second[0].deadline_at == deadline and second[0].started_at == first[0].started_at
    actions: tuple[Callable[[], object], ...] = (
        lambda: store.pulse(job.id, first[1]),
        lambda: store.finish(job.id, first[1], "failed", "stale", None, {}, {}),
        lambda: store.checkpoint(job.id, first[1], {}, {}),
        lambda: store.reusable(job.id, first[1]),
    )
    for action in actions:
        with pytest.raises(DomainError) as failure:
            action()
        assert failure.value.code == "lease_lost"
    store.finish(job.id, second[1], "interrupted", "worker_interrupted", None, {}, {}, retry=True)
    final = store.get(owner, job.id)
    assert (
        final.status == "interrupted" and len(final.attempts) == 2 and store.claim(uuid4()) is None
    )
    assert final.attempts[0].finished_at is not None
    assert final.attempts[0].finished_at <= final.attempts[1].started_at
    with store.projects.write() as connection:
        with pytest.raises(IntegrityError, match="finished attempt"):
            connection.exec_driver_sql("UPDATE local_job_attempts SET status='succeeded'")


def test_expired_heartbeat_refuses_pulse_checkpoint_and_success(
    client: TestClient, application: FastAPI
) -> None:
    store, _, inputs = queued(client, application)
    job = enqueue(store, application.state.owner, inputs)
    claimed = store.claim(uuid4())
    assert claimed is not None
    with store.projects.write() as connection:
        connection.execute(
            text("UPDATE local_jobs SET heartbeat_at=:at WHERE id=:id"),
            {"id": str(job.id), "at": (datetime.now(UTC) - timedelta(seconds=11)).isoformat()},
        )
    actions: tuple[Callable[[], object], ...] = (
        lambda: store.pulse(job.id, claimed[1]),
        lambda: store.checkpoint(job.id, claimed[1], {}, {}),
        lambda: store.finish(job.id, claimed[1], "succeeded", None, None, {}, {}),
    )
    for action in actions:
        with pytest.raises(DomainError) as failure:
            action()
        assert failure.value.code == "lease_lost"


@pytest.mark.parametrize(
    "reason",
    ["invalid_output", "disk_full", "resource_exceeded", "parser_failed", "solver_singular"],
)
def test_model_resource_and_unknown_failures_do_not_retry(
    client: TestClient, application: FastAPI, reason: str
) -> None:
    store, owner, inputs = queued(client, application)
    job = enqueue(store, owner, inputs)
    claimed = store.claim(uuid4())
    assert claimed is not None
    store.finish(job.id, claimed[1], "failed", reason, None, {}, {}, retry=True)
    assert store.get(owner, job.id).status == "failed" and store.claim(uuid4()) is None


@pytest.mark.parametrize("cancel", [False, True])
def test_retry_does_not_reset_expired_budget_or_override_cancellation(
    client: TestClient, application: FastAPI, cancel: bool
) -> None:
    store, owner, inputs = queued(client, application)
    job = enqueue(store, owner, inputs)
    claimed = store.claim(uuid4())
    assert claimed is not None
    if cancel:
        store.cancel(owner, job.id)
    else:
        with store.projects.write() as connection:
            connection.execute(
                text("UPDATE local_jobs SET deadline_at=:at WHERE id=:id"),
                {"id": str(job.id), "at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
            )
    store.finish(job.id, claimed[1], "interrupted", "worker_interrupted", None, {}, {}, retry=True)
    final = store.get(owner, job.id)
    assert final.status == ("cancelled" if cancel else "failed")
    assert final.reason_code == ("cancelled" if cancel else "job_wall_limit")
    assert len(final.attempts) == 1 and store.claim(uuid4()) is None


def test_populated_legacy_attempt_migration_preserves_terminal_and_active_jobs(
    client: TestClient, application: FastAPI
) -> None:
    store, owner, inputs = queued(client, application)
    terminal = enqueue(store, owner, inputs)
    claimed = store.claim(uuid4())
    assert claimed is not None
    store.finish(terminal.id, claimed[1], "failed", "legacy", None, {}, {})
    active = enqueue(store, owner, inputs)
    assert store.claim(uuid4()) is not None
    database = store.projects.database
    database.migrate("0011_archives", downgrade=True)
    database.migrate()
    assert store.get(owner, terminal.id).attempts[0].reason_code == "legacy"
    migrated = store.get(owner, active.id)
    assert migrated.status == "running" and len(migrated.attempts) == 1
    assert migrated.started_at is not None
    assert migrated.deadline_at == migrated.started_at + timedelta(seconds=180)


def test_checkpoints_and_attempts_share_aggregate_output_budget(
    client: TestClient, application: FastAPI
) -> None:
    from app.jobs.runner import LocalWorker

    store, owner, inputs = queued(client, application)
    job = enqueue(store, owner, inputs)
    claimed = store.claim(uuid4())
    assert claimed is not None
    worker = LocalWorker(application.state.job_service)
    directory = application.state.job_service.storage.directory("jobs", job.id)
    paths = {}
    for number, value in enumerate((b"a", b"b")):
        path = directory / str(number)
        path.write_bytes(value * (24 * 1024**2))
        paths[str(number)] = path
    manifest, intact = worker.capture(job.project_id, paths, required=True, job_id=job.id)
    assert intact and len(manifest) == 2
    store.checkpoint(job.id, claimed[1], manifest, {})
    third = directory / "third"
    third.write_bytes(b"c" * (24 * 1024**2))
    extra, intact = worker.capture(job.project_id, {"third": third}, required=True, job_id=job.id)
    assert not intact and not extra
    # The same hashed bytes do not consume a second allowance when reused.
    same, intact = worker.capture(job.project_id, paths, required=True, job_id=job.id)
    assert intact and same == manifest
