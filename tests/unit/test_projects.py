"""Synthetic metadata tests; these do not claim STEP import or numerical validation."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth.local import COOKIE
from app.domain.errors import DomainError
from app.domain.models import (
    AnalysisCreate,
    AnalysisPatch,
    GeometryMetadata,
    ProjectCreate,
)
from app.main import create_app
from app.persistence.database import Database
from app.persistence.repository import Repository


@pytest.fixture(autouse=True)
def local_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEA_ENV", "test")
    monkeypatch.setenv("FEA_AUTH_MODE", "local")
    monkeypatch.setenv("FEA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("FEA_DATA_ROOT", str(tmp_path))


@pytest.fixture
def application() -> FastAPI:
    return create_app()


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(application, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as api:
        response = api.get("/api/v1/session")
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        api.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield api


@pytest.fixture
def metadata() -> GeometryMetadata:
    return GeometryMetadata.model_validate(
        {
            "source_sha256": "a" * 64,
            "brep_sha256": "b" * 64,
            "units": {"source_length_unit": "m", "confirmed": True},
            "bodies": [{"id": "body-1"}],
            "faces": [{"id": "face-1", "body_id": "body-1", "signature": {"type": "synthetic"}}],
            "validation": {"test_metadata_only": True},
        }
    )


def create_project(client: TestClient, name: str = "Bracket") -> dict[str, Any]:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201, response.text
    assert response.headers["etag"] == '"1"'
    assert response.headers["location"].endswith(response.json()["id"])
    return response.json()  # type: ignore[no-any-return]


def test_project_crud_and_tombstone(client: TestClient, application: FastAPI) -> None:
    project = create_project(client, "  Bracket  ")
    assert project["name"] == "Bracket"
    path = f"/api/v1/projects/{project['id']}"
    assert client.get(path).json() == project
    assert client.get("/api/v1/projects").json()["items"] == [project]
    edited = client.patch(path, json={"name": "Revised"}, headers={"If-Match": '"1"'})
    assert edited.status_code == 200
    assert edited.json()["revision"] == 2
    assert edited.headers["etag"] == '"2"'
    assert (
        client.patch(path, json={"name": "Lost edit"}, headers={"If-Match": '"1"'}).status_code
        == 409
    )
    assert client.delete(path, headers={"If-Match": '"1"'}).status_code == 409
    assert client.delete(path, headers={"If-Match": '"2"'}).status_code == 204
    assert client.get(path).status_code == 404
    assert client.delete(path, headers={"If-Match": '"3"'}).status_code == 404
    assert client.get("/api/v1/projects").json()["total"] == 0
    with application.state.repository.database.engine.connect() as connection:
        row = connection.execute(text("SELECT revision, deleted_at FROM projects")).one()
        assert row[0] == 3 and row[1] is not None


def test_analysis_revision_history_and_independence(client: TestClient) -> None:
    project = create_project(client)
    path = f"/api/v1/projects/{project['id']}/analyses"
    first = client.post(path, json={"name": "First"}, headers={"If-Match": '"1"'})
    second = client.post(path, json={"name": "Second"}, headers={"If-Match": '"1"'})
    assert first.status_code == second.status_code == 201
    assert first.json()["status"] == "draft"
    assert first.json()["geometry_revision_id"] is None
    analysis_path = f"/api/v1/analyses/{first.json()['id']}"
    edited = client.patch(analysis_path, json={"name": "Revised"}, headers={"If-Match": '"1"'})
    assert edited.status_code == 200 and edited.json()["revision"] == 2
    assert client.get(analysis_path).json() == edited.json()
    assert client.get(analysis_path + "/revisions/1").json() == first.json()
    assert client.get(analysis_path + "/revisions/2").json() == edited.json()
    assert client.get(analysis_path + "/revisions/3").status_code == 404
    assert (
        client.patch(analysis_path, json={"name": "Stale"}, headers={"If-Match": '"1"'}).status_code
        == 409
    )
    assert client.get(f"/api/v1/analyses/{second.json()['id']}").json()["name"] == "Second"
    assert client.get(path).json()["total"] == 2


@pytest.mark.parametrize("match", [None, "1", '"0"', '"-1"', "*", 'W/"1"', '"1", "2"'])
def test_required_revision(client: TestClient, match: str | None) -> None:
    project = create_project(client)
    headers = {} if match is None else {"If-Match": match}
    response = client.patch(
        f"/api/v1/projects/{project['id']}", json={"name": "Changed"}, headers=headers
    )
    assert response.status_code == (428 if match is None else 422)
    assert client.get(f"/api/v1/projects/{project['id']}").json()["revision"] == 1


def test_request_validation_and_size(client: TestClient) -> None:
    for payload in ({"name": " "}, {"name": "x" * 201}, {"name": "X", "owner_id": str(uuid4())}):
        response = client.post("/api/v1/projects", json=payload)
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_request"
        assert set(response.json()) == {
            "code",
            "message",
            "field_errors",
            "retryable",
            "request_id",
        }
        assert response.headers["X-Request-ID"] == response.json()["request_id"]
    large = client.post("/api/v1/projects", content=b"x" * 65537)
    assert large.status_code == 413
    dishonest = client.post(
        "/api/v1/projects", content=b"x" * 65537, headers={"Content-Length": "1"}
    )
    assert dishonest.status_code == 413
    chunked = client.post("/api/v1/projects", content=iter([b'{"name":"X"}']))
    assert chunked.status_code == 411
    assert client.get("/api/v1/projects?limit=101").status_code == 422
    assert client.get("/api/v1/projects?offset=-1").status_code == 422
    assert client.get("/api/v1/projects").json()["total"] == 0


def test_stable_pagination(client: TestClient) -> None:
    projects = [create_project(client, str(i)) for i in range(3)]
    page = client.get("/api/v1/projects?limit=1&offset=1").json()
    assert page == {"items": [projects[1]], "total": 3, "offset": 1, "limit": 1}


def test_local_session_and_csrf(application: FastAPI) -> None:
    with TestClient(application, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as api:
        assert api.get("/api/v1/projects").status_code == 401
        assert api.post("/api/v1/projects", json={"name": "X"}).status_code == 401
        session = api.get("/api/v1/session").json()
        assert api.get("/api/v1/projects").status_code == 200
        assert api.post("/api/v1/projects", json={"name": "X"}).status_code == 403
        assert (
            api.post(
                "/api/v1/projects", json={"name": "X"}, headers={"X-CSRF-Token": "wrong"}
            ).status_code
            == 403
        )
        assert (
            api.post(
                "/api/v1/projects",
                json={"name": "X"},
                headers={"X-CSRF-Token": session["csrf_token"]},
            ).status_code
            == 201
        )


@pytest.mark.parametrize(
    ("host", "peer", "headers"),
    [
        ("127.0.0.1", "192.0.2.3", {}),
        ("evil.example", "127.0.0.1", {}),
        ("127.0.0.1", "127.0.0.1", {"Origin": "https://evil.example"}),
        ("127.0.0.1", "127.0.0.1", {"Origin": "null"}),
        ("127.0.0.1", "127.0.0.1", {"Origin": "http://127.0.0.1:9999"}),
        ("127.0.0.1", "127.0.0.1", {"Sec-Fetch-Site": "cross-site"}),
        (
            "127.0.0.1",
            "192.0.2.3",
            {"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "localhost"},
        ),
    ],
)
def test_local_boundary(
    application: FastAPI, host: str, peer: str, headers: dict[str, str]
) -> None:
    with TestClient(application, base_url=f"http://{host}", client=(peer, 55000)) as api:
        response = api.get("/api/v1/session", headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == "local_access_only"


def test_same_origin_and_forwarded_owner_ignored(client: TestClient) -> None:
    project = create_project(client)
    actual = client.get("/api/v1/session").json()["owner_id"]
    assert project["owner_id"] == actual
    response = client.get(
        "/api/v1/projects", headers={"X-Owner-ID": str(uuid4()), "Origin": "http://127.0.0.1"}
    )
    assert response.status_code == 200 and response.json()["items"] == [project]


def test_owner_isolation_and_deleted_children(
    client: TestClient, application: FastAPI, metadata: GeometryMetadata
) -> None:
    store: Repository = application.state.repository
    owner: UUID = application.state.owner
    other_owner = uuid4()
    with store.write() as connection:
        connection.execute(
            text("INSERT INTO users VALUES (:id, NULL, :time)"),
            {"id": str(other_owner), "time": "2026-10-13T00:00:00+00:00"},
        )
    foreign = store.create_project(other_owner, ProjectCreate(name="Private"))
    foreign_geometry = store.register_geometry(other_owner, foreign.id, 1, metadata)
    foreign_analysis = store.create_analysis(
        other_owner,
        foreign.id,
        2,
        AnalysisCreate(name="Private", geometry_revision_id=foreign_geometry.id),
    )
    for path in (
        f"/projects/{foreign.id}",
        f"/projects/{foreign.id}/analyses",
        f"/projects/{foreign.id}/geometry",
        f"/geometry/{foreign_geometry.id}",
        f"/analyses/{foreign_analysis.id}",
        f"/analyses/{foreign_analysis.id}/revisions/1",
    ):
        assert client.get("/api/v1" + path).status_code == 404
    assert (
        client.patch(
            f"/api/v1/projects/{foreign.id}", json={"name": "Steal"}, headers={"If-Match": '"2"'}
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/projects/{foreign.id}", headers={"If-Match": '"2"'}).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/analyses/{foreign_analysis.id}",
            json={"name": "Steal"},
            headers={"If-Match": '"1"'},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/projects").json()["items"] == []
    own = store.create_project(owner, ProjectCreate(name="Own"))
    rejected = client.post(
        f"/api/v1/projects/{own.id}/analyses",
        json={"name": "Wrong", "geometry_revision_id": str(foreign_geometry.id)},
        headers={"If-Match": '"1"'},
    )
    assert rejected.status_code == 404
    assert (
        client.post(
            f"/api/v1/projects/{foreign.id}/analyses",
            json={"name": "Wrong"},
            headers={"If-Match": '"2"'},
        ).status_code
        == 404
    )
    geometry = store.register_geometry(owner, own.id, 1, metadata)
    analysis = store.create_analysis(
        owner, own.id, 2, AnalysisCreate(name="Own", geometry_revision_id=geometry.id)
    )
    assert (
        client.delete(f"/api/v1/projects/{own.id}", headers={"If-Match": '"2"'}).status_code == 204
    )
    assert client.get(f"/api/v1/geometry/{geometry.id}").status_code == 404
    assert client.get(f"/api/v1/analyses/{analysis.id}").status_code == 404
    assert client.get(f"/api/v1/analyses/{analysis.id}/revisions/1").status_code == 404


def test_immutable_geometry_and_pinned_analysis(
    client: TestClient, application: FastAPI, metadata: GeometryMetadata
) -> None:
    store: Repository = application.state.repository
    owner: UUID = application.state.owner
    project = store.create_project(owner, ProjectCreate(name="Part"))
    first = store.register_geometry(owner, project.id, 1, metadata)
    analysis = store.create_analysis(
        owner, project.id, 2, AnalysisCreate(name="A", geometry_revision_id=first.id)
    )
    second = store.register_geometry(
        owner, project.id, 2, metadata.model_copy(update={"brep_sha256": "c" * 64}), parent=first.id
    )
    assert second.parent_id == first.id
    assert client.get(f"/api/v1/geometry/{first.id}").json() == first.model_dump(mode="json")
    assert client.get(f"/api/v1/analyses/{analysis.id}").json()["geometry_revision_id"] == str(
        first.id
    )
    assert client.get(f"/api/v1/projects/{project.id}/geometry").json()["total"] == 2
    with pytest.raises(DomainError) as stale:
        store.register_geometry(owner, project.id, 2, metadata)
    assert stale.value.code == "stale_revision"
    different = store.create_project(owner, ProjectCreate(name="Other"))
    with pytest.raises(DomainError):
        store.register_geometry(owner, different.id, 1, metadata, parent=first.id)
    for statement in (
        "UPDATE geometry_revisions SET metadata_json='{}'",
        "DELETE FROM geometry_revisions",
        "UPDATE analysis_revisions SET name='overwrite'",
        "DELETE FROM analysis_revisions",
    ):
        with pytest.raises(IntegrityError), store.write() as connection:
            connection.execute(text(statement))
    assert store.get_geometry(owner, first.id) == first
    assert store.get_analysis(owner, analysis.id, 1) == analysis


def test_concurrent_analysis_save_has_one_winner(client: TestClient, application: FastAPI) -> None:
    store: Repository = application.state.repository
    owner: UUID = application.state.owner
    project = store.create_project(owner, ProjectCreate(name="Part"))
    analysis = store.create_analysis(owner, project.id, 1, AnalysisCreate(name="Original"))

    def save(name: str) -> str:
        try:
            return store.edit_analysis(owner, analysis.id, 1, AnalysisPatch(name=name)).name
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["First edit", "Second edit"]))
    assert results.count("stale_revision") == 1
    assert store.get_analysis(owner, analysis.id).revision == 2
    assert store.get_analysis(owner, analysis.id, 1).name == "Original"


def test_restart_recovers_identity_history_and_tombstones(
    tmp_path: Path, metadata: GeometryMetadata
) -> None:
    first = create_app()
    with TestClient(first, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as client:
        session = client.get("/api/v1/session").json()
        old_cookie = client.cookies.get(COOKIE)
        store: Repository = first.state.repository
        owner = UUID(session["owner_id"])
        project = store.create_project(owner, ProjectCreate(name="Retained"))
        deleted = store.create_project(owner, ProjectCreate(name="Deleted"))
        store.edit_project(owner, deleted.id, 1, None)
        geometry = store.register_geometry(owner, project.id, 1, metadata)
        analysis = store.create_analysis(
            owner, project.id, 2, AnalysisCreate(name="Original", geometry_revision_id=geometry.id)
        )
        store.edit_analysis(owner, analysis.id, 1, AnalysisPatch(name="New name"))
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        client.cookies.set(COOKIE, old_cookie or "", path="/api/v1")
        assert client.get("/api/v1/projects").status_code == 401
        client.cookies.clear()
        assert client.get("/api/v1/session").json()["owner_id"] == session["owner_id"]
        assert client.get(f"/api/v1/projects/{project.id}").json()["revision"] == 2
        assert client.get(f"/api/v1/projects/{deleted.id}").status_code == 404
        assert client.get(f"/api/v1/geometry/{geometry.id}").json() == geometry.model_dump(
            mode="json"
        )
        assert client.get(f"/api/v1/analyses/{analysis.id}").json()["name"] == "New name"
        assert (
            client.get(f"/api/v1/analyses/{analysis.id}/revisions/1").json()["name"] == "Original"
        )
    assert (tmp_path / "metadata.sqlite3").stat().st_mode & 0o777 == 0o600


def test_migration_reversibility_and_sqlite_integrity(
    tmp_path: Path, metadata: GeometryMetadata
) -> None:
    database = Database(tmp_path / "migrations.sqlite3")
    try:
        database.migrate()
        database.migrate()
        store = Repository(database)
        owner = store.local_owner()
        project = store.create_project(owner, ProjectCreate(name="Populated"))
        geometry = store.register_geometry(owner, project.id, 1, metadata)
        store.create_analysis(
            owner, project.id, 2, AnalysisCreate(name="A", geometry_revision_id=geometry.id)
        )
        with database.engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar_one() == "ok"
            assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        database.migrate("base", downgrade=True)
        with database.engine.connect() as connection:
            tables = (
                connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
                .scalars()
                .all()
            )
            assert tables == ["alembic_version"]
            assert (
                connection.exec_driver_sql("SELECT count(*) FROM alembic_version").scalar_one() == 0
            )
        database.migrate()
        assert (
            Repository(database).list_projects(Repository(database).local_owner(), 0, 50).total == 0
        )
    finally:
        database.close()


def test_catalog_references_must_resolve(metadata: GeometryMetadata) -> None:
    fields = metadata.model_dump()
    fields["faces"][0]["body_id"] = "missing-body"
    with pytest.raises(ValidationError):
        GeometryMetadata.model_validate(fields)


def test_failed_migration_rolls_back_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from alembic.operations import Operations

    original = Operations.execute
    count = 0

    def fail_after_first_statement(self: Operations, statement: Any, **kwargs: Any) -> None:
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("Injected migration failure")
        original(self, statement, **kwargs)

    database = Database(tmp_path / "failed.sqlite3")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(Operations, "execute", fail_after_first_statement)
            with pytest.raises(RuntimeError, match="Injected migration failure"):
                database.migrate()
        with database.engine.connect() as connection:
            assert (
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).all()
                == []
            )
        database.migrate()
        assert Repository(database).local_owner()
    finally:
        database.close()


def test_storage_failure_is_redacted(client: TestClient, application: FastAPI) -> None:
    with application.state.repository.database.engine.begin() as connection:
        connection.execute(text("DROP TABLE projects"))
    response = client.get("/api/v1/projects")
    assert response.status_code == 503
    assert response.json()["retryable"] is True
    assert "SELECT" not in response.text and "sqlite" not in response.text
