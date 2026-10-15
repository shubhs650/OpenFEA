"""Actual owned Word export from an immutable historical report through the public API."""

import fcntl
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.domain import word_service
from app.domain.errors import DomainError
from app.main import create_app
from tests.native import test_step_import as step_tests
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.reports.test_reports import payload
from tests.reports.test_word import OUT, parity
from worker.reports.render import render_word

application = step_tests.application
client = step_tests.client


def test_actual_owned_word_history_failure_expiry_and_tombstones(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    report_path = f"/api/v1/runs/{run['id']}/reports"
    response = client.post(report_path, json=payload(geometry["bodies"][0]["id"]))
    assert response.status_code == 201, response.text
    report = response.json()
    base = f"/api/v1/reports/{report['id']}"
    model_bytes, pdf_bytes = [client.get(base + "/" + kind).content for kind in ("model", "pdf")]
    # Current analysis can change without rewriting this original report or its Word facts.
    revision = client.get(path).json()["revision"]
    assert (
        client.patch(
            path, json={"name": "Later edit"}, headers={"If-Match": f'"{revision}"'}
        ).status_code
        == 200
    )
    route = base + "/exports/word"
    assert client.get(route).json() == []
    assert client.post(route, json={}, headers={"X-CSRF-Token": ""}).status_code == 403
    assert client.post(route, json={"image_url": "https://invalid.example"}).status_code == 422
    service = application.state.word_service
    with pytest.raises(DomainError) as denied:
        service.create(uuid4(), UUID(report["id"]))
    assert denied.value.status == 404
    with (service.storage.root / "report.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert client.post(route, json={}).status_code == 429
    response = client.post(route, json={})
    assert response.status_code == 201, response.text
    record = response.json()
    artifact = f"/api/v1/word-exports/{record['id']}/docx"
    downloaded = client.get(artifact)
    assert (
        downloaded.status_code == 200 and "wordprocessingml" in downloaded.headers["content-type"]
    )
    assert hashlib.sha256(downloaded.content).hexdigest() == record["docx_sha256"]
    assert (
        record["model_sha256"] == report["model_sha256"]
        and record["pdf_sha256"] == report["pdf_sha256"]
    )
    from app.domain.reports import ReportModel

    parity(ReportModel.model_validate_json(model_bytes), downloaded.content)
    assert client.get(base + "/model").content == model_bytes
    assert client.get(base + "/pdf").content == pdf_bytes
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "api.docx").write_bytes(downloaded.content)
    (OUT / "api-record.json").write_text(json.dumps(record, indent=2) + "\n")
    for lookup in (service.get, service.artifact):
        with pytest.raises(DomainError) as denied:
            lookup(uuid4(), UUID(record["id"]))
        assert denied.value.status == 404
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 55001)
    ) as reopened:
        reopened.get("/api/v1/session")
        assert reopened.get(artifact).content == downloaded.content
    native = service.storage.blob_path(
        UUID(geometry["project_id"]), run["artifacts"]["analysis.dat"]["sha256"]
    )
    original = native.read_bytes()
    native.unlink()
    assert client.post(route, json={}).status_code == 503
    assert client.get(artifact).content == downloaded.content
    native.write_bytes(original)

    def fail(directory: Path) -> dict[str, str]:
        raise RuntimeError("deliberate word failure")

    monkeypatch.setattr(word_service, "render_word", fail)
    assert client.post(route, json={}).status_code == 503
    assert len(client.get(route).json()) == 1
    assert not list((service.storage.root / "exports").glob("*"))

    def expire(directory: Path) -> dict[str, str]:
        audit = render_word(directory)
        native.unlink()
        return audit

    monkeypatch.setattr(word_service, "render_word", expire)
    assert client.post(route, json={}).status_code == 503
    assert len(client.get(route).json()) == 1
    native.write_bytes(original)
    blob = service.storage.blob_path(UUID(record["project_id"]), record["docx_sha256"])
    blob.chmod(0o600)
    blob.write_bytes(b"corrupt")
    assert client.get(artifact).status_code == 503
    blob.write_bytes(downloaded.content)
    with pytest.raises(IntegrityError), service.projects.write() as connection:
        connection.execute(
            text("UPDATE report_word_exports SET record_json='{}' WHERE id=:id"),
            {"id": record["id"]},
        )
    project = client.get(f"/api/v1/projects/{geometry['project_id']}").json()
    assert (
        client.delete(
            f"/api/v1/projects/{geometry['project_id']}",
            headers={"If-Match": f'"{project["revision"]}"'},
        ).status_code
        == 204
    )
    assert client.get(artifact).status_code == 404
