"""Actual native setup/solve/archive round trip, privacy and publication boundaries."""

import hashlib
import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.domain.errors import DomainError
from app.storage.archives import json_bytes, read_archive, write_archive
from tests.native import test_step_import as step_tests
from tests.native.test_local_jobs import prepared, submit, wait_job

application = step_tests.application
client = step_tests.client
OUT = Path(".local/archives/T027")


def export(client: TestClient, project: str, outputs: bool = False) -> tuple[dict[str, Any], bytes]:
    response = client.post(f"/api/v1/projects/{project}/exports", json={"include_outputs": outputs})
    assert response.status_code == 201, response.text
    record = response.json()
    response = client.get(f"/api/v1/portable-bundles/{record['id']}/zip")
    assert response.status_code == 200, response.text
    raw = response.content
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    return record, raw


def restore(client: TestClient, raw: bytes) -> dict[str, Any]:
    response = client.post(
        "/api/v1/archive-imports", content=raw, headers={"Content-Type": "application/zip"}
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, Any], response.json())


def test_actual_archive_setup_history_expiry_and_privacy(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = prepared(client)
    project = geometry["project_id"]
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    original = client.get(path + "/loads").json()
    record, raw = export(client, project, True)
    manifest, files = read_archive(raw)
    restored = restore(client, raw)
    new_path = f"/api/v1/analyses/{restored['id_map'][path.split('/')[-1]]}"
    assert restored["project"]["owner_id"] == client.get("/api/v1/session").json()["owner_id"]
    assert restored["project"]["id"] != project
    new_loads = client.get(new_path + "/loads").json()
    assert len(original["setup"]["assignments"]) == len(new_loads["setup"]["assignments"])
    for old, new in zip(
        original["setup"]["assignments"], new_loads["setup"]["assignments"], strict=True
    ):
        assert new["id"] != old["id"]
        assert new["geometry_revision_id"] == restored["id_map"][old["geometry_revision_id"]]
        assert {k: v for k, v in old.items() if k not in ("id", "geometry_revision_id")} == {
            k: v for k, v in new.items() if k not in ("id", "geometry_revision_id")
        }
    assert client.get(new_path + "/jobs").json() == []
    item = next(h for h in restored["history"] if h["source_id"] == run["id"])
    history_url = f"/api/v1/archive-imports/{restored['id']}/history/{item['id']}/analysis.inp"
    assert (
        client.get(history_url).content
        == client.get(f"/api/v1/jobs/{run['id']}/artifacts/analysis.inp").content
    )
    # Re-solve is a fresh current-tool job; imported deck never becomes executable.
    new_mesh = wait_job(client, submit(client, new_path)["id"])
    new_run = wait_job(client, submit(client, new_path, new_mesh["id"])["id"])
    assert new_run["status"] == "succeeded", new_run
    assert new_run["id"] != run["id"]
    assert new_run["summary"]["equilibrium"] == run["summary"]["equilibrium"]
    _, second_raw = export(client, restored["project"]["id"], True)
    second = restore(client, second_raw)
    assert len(second["history"]) == 4
    # Default diagnostics expose neither names, setup, coordinates, IDs nor raw logs.
    endpoint = f"/api/v1/projects/{project}/diagnostic-previews"
    preview = client.post(endpoint, json={}).json()
    diag_raw = client.get(f"/api/v1/portable-bundles/{preview['id']}/zip").content
    _, diag_files = read_archive(diag_raw)
    assert set(diag_files) == {"diagnostic.json"}
    for secret in (
        project,
        geometry["id"],
        geometry["brep_sha256"],
        run["id"],
        geometry["bodies"][0]["id"],
        "points_m",
        "source.step",
    ):
        assert secret.encode() not in diag_raw
    explicit = client.post(endpoint, json={"include_geometry": True, "include_results": True})
    assert explicit.status_code == 201, explicit.text
    assert len(explicit.json()["manifest"]["files"]) > 2
    # A genuinely absent retained output is omitted, never regenerated; corruption fails.
    service = application.state.archive_service
    missing = run["artifacts"]["analysis.dat"]["sha256"]
    service.storage.blob_path(UUID(project), missing).unlink()
    _, expired = export(client, project, True)
    _, expired_files = read_archive(expired)
    expired_setup = json.loads(expired_files["project.json"])
    assert (
        next(h for h in expired_setup["history"] if h["id"] == run["id"])["omitted"]["analysis.dat"]
        == "unavailable"
    )
    restore(client, expired)
    with pytest.raises(DomainError) as denied:
        service.bundle(uuid4(), UUID(record["id"]))
    assert denied.value.status == 404
    assert (
        client.post(
            f"/api/v1/projects/{project}/exports", json={}, headers={"X-CSRF-Token": ""}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/archive-imports",
            content=raw,
            headers={"Content-Type": "application/zip", "X-CSRF-Token": ""},
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/jobs/{item['id']}").status_code == 404
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "project.zip").write_bytes(raw)
    (OUT / "diagnostic.zip").write_bytes(diag_raw)
    (OUT / "roundtrip.json").write_text(
        json.dumps(
            {
                "original_project": project,
                "import": restored,
                "manifest": manifest.model_dump(mode="json"),
                "run": run["id"],
                "fresh_run": new_run["id"],
            },
            indent=2,
        )
        + "\n"
    )
    current = client.get(f"/api/v1/projects/{restored['project']['id']}").json()
    assert (
        client.delete(
            f"/api/v1/projects/{current['id']}", headers={"If-Match": f'"{current["revision"]}"'}
        ).status_code
        == 204
    )
    assert client.get(history_url).status_code == 404


def test_reject_forged_catalog_and_rollback(client: TestClient, application: FastAPI) -> None:
    _, geometry = prepared(client)
    _, raw = export(client, geometry["project_id"])
    manifest, files = read_archive(raw)
    setup = json.loads(files["project.json"])
    # Incoming derived metric claims never become trusted runtime geometry.
    setup["geometries"][0]["faces"][0]["signature"]["area_m2"] = 12345
    files["project.json"] = json_bytes(setup)
    sanitized = restore(client, write_archive(manifest, files))
    native = client.get(f"/api/v1/projects/{sanitized['project']['id']}/geometry").json()["items"][
        0
    ]
    assert native["faces"][0]["signature"]["area_m2"] == 1
    setup["geometries"][0]["faces"][0]["id"] = "forged-face"
    files["project.json"] = json_bytes(setup)
    forged = write_archive(manifest, files)
    before = client.get("/api/v1/projects").json()["total"]
    response = client.post(
        "/api/v1/archive-imports", content=forged, headers={"Content-Type": "application/zip"}
    )
    assert response.status_code == 422, response.text
    assert client.get("/api/v1/projects").json()["total"] == before
    # Simulate a failed database publication after native validation/storage.
    service = application.state.archive_service
    with service.projects.database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM archive_imports")).scalar() == 1


def test_new_owner_atomic_publication_and_size_guards(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, geometry = prepared(client)
    _, raw = export(client, geometry["project_id"])
    service = application.state.archive_service
    owner = uuid4()
    with service.projects.write() as connection:
        connection.execute(
            text("INSERT INTO users VALUES (:id,NULL,'2026-10-15T00:00:00Z')"), {"id": str(owner)}
        )
    imported = service.import_archive(owner, raw)
    assert imported.project.owner_id == owner
    assert imported.project.id != UUID(geometry["project_id"])
    assert client.get(f"/api/v1/projects/{imported.project.id}").status_code == 404
    with pytest.raises(DomainError):
        service.imported(UUID(client.get("/api/v1/session").json()["owner_id"]), imported.id)
    before = client.get("/api/v1/projects").json()["total"]
    directories = set((service.storage.root / "artifacts").iterdir())

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Synthetic publication failure")

    with monkeypatch.context() as patch:
        patch.setattr(service.projects, "_insert_analysis_revision", fail)
        with pytest.raises(RuntimeError, match="publication failure"):
            service.import_archive(UUID(client.get("/api/v1/session").json()["owner_id"]), raw)
    assert client.get("/api/v1/projects").json()["total"] == before
    assert set((service.storage.root / "artifacts").iterdir()) == directories
    assert list((service.storage.root / "imports").glob("*/verified-*")) == []
    assert (
        client.post(
            "/api/v1/archive-imports", content=b"bad", headers={"Content-Type": "application/zip"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/archive-imports",
            content=b"bad",
            headers={"Content-Type": "application/zip", "Content-Length": str(64 * 1024**2 + 1)},
        ).status_code
        == 413
    )
    # A corrupt output refuses download instead of silently creating a replacement.
    record, _ = export(client, geometry["project_id"])
    blob = service.storage.blob_path(UUID(geometry["project_id"]), record["sha256"])
    blob.chmod(0o600)
    blob.write_bytes(b"corrupted")
    assert client.get(f"/api/v1/portable-bundles/{record['id']}/zip").status_code == 503


def test_saved_native_directions_bonds_and_geometry_ancestry(client: TestClient) -> None:
    from tests.native.test_connections import analysis, inspect, request
    from tests.native.test_directions import patch
    from tests.native.test_geometry_edits import accepted, commit, preview

    path, geometry = patch(client, True, 0.7)
    original = client.get(path + "/loads").json()
    _, raw = export(client, geometry["project_id"])
    restored = restore(client, raw)
    new_path = "/api/v1/analyses/" + restored["id_map"][path.split("/")[-1]]
    fresh = client.get(new_path + "/loads").json()
    assert (
        fresh["setup"]["assignments"][-1]["force_n"]
        == original["setup"]["assignments"][-1]["force_n"]
    )
    assert not fresh["blockers"], fresh
    path, geometry = analysis(client, "bond-zero-m.step")
    candidates = inspect(client, path)
    response = client.post(
        path + "/bonds",
        json=request(geometry, candidates["report"]["pairs"][0]),
        headers={"If-Match": f'"{client.get(path).json()["revision"]}"'},
    )
    assert response.status_code == 200, response.text
    _, raw = export(client, geometry["project_id"])
    restored = restore(client, raw)
    state = client.get(
        "/api/v1/analyses/" + restored["id_map"][path.split("/")[-1]] + "/bonds"
    ).json()
    assert len(state["setup"]["assignments"]) == 1
    assert not state["review_required"], state
    assert not state["solve_blockers"], state
    geometry = accepted(client)
    edited = commit(client, geometry, preview(client, geometry))
    _, raw = export(client, geometry["project_id"])
    restored = restore(client, raw)
    page = client.get(f"/api/v1/projects/{restored['project']['id']}/geometry").json()
    assert len(page["items"]) == 2
    assert page["items"][1]["parent_id"] == page["items"][0]["id"]
    assert page["items"][1]["brep_sha256"] == edited["geometry"]["brep_sha256"]
