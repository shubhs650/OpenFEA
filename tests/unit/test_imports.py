"""Upload, ownership, integrity and lifecycle checks without mocked CAD claims."""

import hashlib
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.domain.errors import DomainError
from app.domain.imports import ImportCreate, UploadCreate
from app.domain.models import ProjectCreate
from app.main import create_app
from app.storage.geometry import GeometryStorage


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastAPI:
    monkeypatch.setenv("FEA_ENV", "test")
    monkeypatch.setenv("FEA_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("FEA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("FEA_AUTH_MODE", "local")
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/v1/session").json()["csrf_token"]
        yield client


def ticket(client: TestClient, raw: bytes) -> tuple[str, str]:
    project = client.post("/api/v1/projects", json={"name": "Upload fixture"}).json()["id"]
    response = client.post(
        f"/api/v1/projects/{project}/geometry-uploads",
        json={"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
    )
    assert response.status_code == 201
    return project, response.json()["id"]


def test_verified_upload_and_single_claim(client: TestClient, app: FastAPI) -> None:
    raw = b"synthetic upload boundary bytes; not a CAD validation case"
    _, identifier = ticket(client, raw)
    path = f"/api/v1/geometry-uploads/{identifier}/content"
    response = client.put(path, content=raw)
    assert response.status_code == 200 and response.json()["status"] == "complete"
    assert (
        client.get(f"/api/v1/geometry-uploads/{identifier}").json()["sha256"]
        == hashlib.sha256(raw).hexdigest()
    )
    assert client.put(path, content=raw).status_code == 409
    storage: GeometryStorage = app.state.import_service.storage
    assert storage.read_fixed(storage.directory("uploads", UUID(identifier)) / "source.step") == raw


def test_upload_limits_and_hash_mismatch(client: TestClient, app: FastAPI) -> None:
    project, identifier = ticket(client, b"correct")
    path = f"/api/v1/projects/{project}/geometry-uploads"
    assert (
        client.post(path, json={"size_bytes": 16 * 1024**2 + 1, "sha256": "a" * 64}).status_code
        == 422
    )
    assert client.post(path, json={"size_bytes": 0, "sha256": "a" * 64}).status_code == 422
    assert client.post(path, json={"size_bytes": 10, "sha256": "../path"}).status_code == 422
    upload_path = f"/api/v1/geometry-uploads/{identifier}/content"
    assert client.put(upload_path, content=b"wrong!!").status_code == 422
    assert client.get(f"/api/v1/geometry-uploads/{identifier}").json()["status"] == "failed"
    assert not (
        app.state.import_service.storage.directory("uploads", UUID(identifier)) / "source.step"
    ).exists()
    assert (
        client.put(
            upload_path, content=b"x", headers={"Content-Length": str(16 * 1024**2 + 1)}
        ).status_code
        == 413
    )


def test_upload_actual_size_and_incomplete_import(client: TestClient) -> None:
    project, identifier = ticket(client, b"abc")
    path = f"/api/v1/geometry-uploads/{identifier}/content"
    assert client.put(path, content=b"abcdef", headers={"Content-Length": "3"}).status_code == 413
    assert (
        client.post(
            f"/api/v1/projects/{project}/geometry-imports",
            json={"upload_id": identifier},
            headers={"If-Match": '"1"'},
        ).status_code
        == 409
    )


def test_upload_and_import_owner_scope(client: TestClient, app: FastAPI) -> None:
    repository = app.state.repository
    imports = app.state.import_service.repository
    other = uuid4()
    with repository.write() as connection:
        connection.execute(
            text("INSERT INTO users VALUES (:id,NULL,:time)"),
            {"id": str(other), "time": "2026-10-13T00:00:00+00:00"},
        )
    project = repository.create_project(other, ProjectCreate(name="Other owner"))
    upload = imports.create_upload(other, project.id, UploadCreate(size_bytes=3, sha256="a" * 64))
    assert client.get(f"/api/v1/geometry-uploads/{upload.id}").status_code == 404
    assert (
        client.put(f"/api/v1/geometry-uploads/{upload.id}/content", content=b"abc").status_code
        == 404
    )
    imports.transition_upload(other, upload.id, "pending", "uploading")
    imports.transition_upload(other, upload.id, "uploading", "complete")
    preview = imports.create_import(other, project.id, 1, ImportCreate(upload_id=upload.id))
    assert client.get(f"/api/v1/geometry-imports/{preview.id}").status_code == 404
    assert (
        client.post(
            f"/api/v1/geometry-imports/{preview.id}/confirm",
            json={"dimensions_confirmed": True},
            headers={"If-Match": '"1"'},
        ).status_code
        == 404
    )
    own, _ = ticket(client, b"abc")
    with pytest.raises(DomainError) as error:
        imports.create_import(app.state.owner, UUID(own), 1, ImportCreate(upload_id=upload.id))
    assert error.value.status == 404


def test_storage_symlinks_and_tampering_fail_closed(tmp_path: Path) -> None:
    storage = GeometryStorage(tmp_path / "storage")
    source = tmp_path / "source"
    source.write_bytes(b"immutable bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    project = uuid4()
    storage.save(project, source, digest)
    assert storage.read(project, digest) == source.read_bytes()
    blob = storage.blob_path(project, digest)
    blob.unlink()
    blob.symlink_to(source)
    with pytest.raises(DomainError) as symlink:
        storage.read(project, digest)
    assert symlink.value.code == "artifact_unavailable"
    blob.unlink()
    blob.write_bytes(b"corrupted")
    with pytest.raises(DomainError) as corrupted:
        storage.read(project, digest)
    assert corrupted.value.code == "artifact_integrity"


def test_interrupted_states_fail_without_retry(client: TestClient, app: FastAPI) -> None:
    project, identifier = ticket(client, b"abc")
    imports = app.state.import_service.repository
    owner = app.state.owner
    imports.transition_upload(owner, UUID(identifier), "pending", "uploading")
    imports.transition_upload(owner, UUID(identifier), "uploading", "complete")
    first = imports.create_import(owner, UUID(project), 1, ImportCreate(upload_id=UUID(identifier)))
    second_project, second_upload = ticket(client, b"xyz")
    imports.transition_upload(owner, UUID(second_upload), "pending", "uploading")
    imports.interrupt_incomplete()
    assert imports.get_import(owner, first.id).status == "failed"
    assert imports.get_import(owner, first.id).error_code == "interrupted"
    assert imports.upload(owner, UUID(second_upload)).status == "failed"
    assert app.state.repository.get_project(owner, UUID(second_project)).revision == 1
