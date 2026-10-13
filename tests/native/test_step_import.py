"""Real OCCT/API imports with analytical synthetic dimensions and namespace probes."""

import hashlib
import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from worker import step_import

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/geometry"


@pytest.fixture
def application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("FEA_ENV", "test")
    monkeypatch.setenv("FEA_AUTH_MODE", "local")
    monkeypatch.setenv("FEA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("FEA_DATA_ROOT", str(tmp_path))
    return create_app()


@pytest.fixture
def client(application: FastAPI) -> Iterator[TestClient]:
    with TestClient(
        application, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)
    ) as client:
        client.headers["X-CSRF-Token"] = client.get("/api/v1/session").json()["csrf_token"]
        yield client


def import_fixture(
    client: TestClient, fixture: str, unit: str | None = None
) -> tuple[str, dict[str, Any]]:
    raw = (FIXTURES / fixture).read_bytes()
    project = client.post("/api/v1/projects", json={"name": "Real synthetic CAD"}).json()["id"]
    upload = client.post(
        f"/api/v1/projects/{project}/geometry-uploads",
        json={"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
    ).json()
    assert (
        client.put(f"/api/v1/geometry-uploads/{upload['id']}/content", content=raw).status_code
        == 200
    )
    payload = {"upload_id": upload["id"]}
    if unit:
        payload["source_length_unit"] = unit
    response = client.post(
        f"/api/v1/projects/{project}/geometry-imports", json=payload, headers={"If-Match": '"1"'}
    )
    assert response.status_code == 201, response.text
    return project, response.json()


@pytest.mark.parametrize("fixture", ["cube-m.step", "cube-mm.step", "cube-inch.step"])
def test_real_metadata_units_convert_to_metres(client: TestClient, fixture: str) -> None:
    project, preview = import_fixture(client, fixture)
    assert preview["status"] == "ready", preview
    assert preview["inspection"]["bounds_m"] == pytest.approx([0, 0, 0, 1, 1, 1], rel=0, abs=1e-9)
    assert client.get(f"/api/v1/projects/{project}/geometry").json()["total"] == 0
    response = client.post(
        f"/api/v1/geometry-imports/{preview['id']}/confirm",
        json={"dimensions_confirmed": True},
        headers={"If-Match": '"1"'},
    )
    assert response.status_code == 200, response.text
    geometry = response.json()
    assert client.get(f"/api/v1/projects/{project}").json()["revision"] == 2
    assert geometry["validation"]["valid_solids"] is True
    display = client.get(f"/api/v1/geometry/{geometry['id']}/display").json()
    assert display["bodies"][0]["volume_m3"] == pytest.approx(1, rel=0, abs=1e-10)
    assert {f["id"] for f in display["faces"]} == {f["id"] for f in geometry["faces"]}


@pytest.mark.parametrize(("unit", "expected"), [("m", 1.0), ("mm", 0.001), ("inch", 0.0254)])
def test_missing_units_require_explicit_decision(
    tmp_path: Path, unit: str, expected: float
) -> None:
    source = FIXTURES / "cube-missing.step"
    first = step_import.inspect_step(source, tmp_path / "first")
    assert first["status"] == "needs_units"
    assert not (tmp_path / "first/geometry.brep").exists()
    selected = step_import.inspect_step(source, tmp_path / "selected", unit)
    assert selected["status"] == "ready", selected
    assert selected["inspection"]["bounds_m"][3:] == pytest.approx([expected] * 3, rel=0, abs=1e-9)
    assert selected["inspection"]["unit_origin"] == "explicit_missing_metadata"


@pytest.mark.parametrize(
    ("fixture", "code"),
    [
        ("surface-m.step", "solids_required"),
        ("eleven-m.step", "solids_required"),
        ("invalid.step", "invalid_step"),
        ("mixed-wire-m.step", "free_geometry"),
    ],
)
def test_invalid_and_surface_models_are_diagnosed(
    client: TestClient, fixture: str, code: str
) -> None:
    project, preview = import_fixture(client, fixture)
    assert preview["status"] == "failed" and preview["error_code"] == code, preview
    assert client.get(f"/api/v1/projects/{project}/geometry").json()["total"] == 0
    assert (
        client.post(
            f"/api/v1/geometry-imports/{preview['id']}/confirm",
            json={"dimensions_confirmed": True},
            headers={"If-Match": '"1"'},
        ).status_code
        == 409
    )


def test_multibody_and_curved_lod_keep_immutable_face_ids(tmp_path: Path) -> None:
    for fixture, bodies, volume in (("two-m.step", 2, 1.0), ("cylinder-m.step", 1, math.pi / 4)):
        output = tmp_path / fixture
        result = step_import.inspect_step(FIXTURES / fixture, output)
        assert result["status"] == "ready", result
        coarse = json.loads((output / "display-coarse.json").read_text())
        fine = json.loads((output / "display-fine.json").read_text())
        assert len(coarse["bodies"]) == bodies
        assert {f["id"]: f["body_id"] for f in coarse["faces"]} == {
            f["id"]: f["body_id"] for f in fine["faces"]
        }
        for body in coarse["bodies"]:
            assert body["volume_m3"] == pytest.approx(volume, rel=0, abs=1e-10)
        assert (
            hashlib.sha256((output / "geometry.brep").read_bytes()).hexdigest()
            == result["metadata"]["brep_sha256"]
        )
        if fixture == "cylinder-m.step":
            assert result["inspection"]["fine_triangles"] > result["inspection"]["coarse_triangles"]
        else:
            assert result["inspection"]["bounds_m"] == pytest.approx(
                [0, 0, 0, 3, 1, 1], rel=0, abs=1e-9
            )


def test_detected_units_cannot_be_silently_overridden(tmp_path: Path) -> None:
    result = step_import.inspect_step(FIXTURES / "cube-mm.step", tmp_path / "conflict", "inch")
    assert result["status"] == "failed" and result["error_code"] == "unit_conflict"
    assert not (tmp_path / "conflict/geometry.brep").exists()


def test_stale_confirmation_and_corrupted_artifact_refuse(
    client: TestClient, application: FastAPI
) -> None:
    project, preview = import_fixture(client, "cube-m.step")
    assert (
        client.patch(
            f"/api/v1/projects/{project}", json={"name": "Changed"}, headers={"If-Match": '"1"'}
        ).status_code
        == 200
    )
    path = f"/api/v1/geometry-imports/{preview['id']}/confirm"
    assert (
        client.post(
            path, json={"dimensions_confirmed": True}, headers={"If-Match": '"1"'}
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/projects/{project}/geometry").json()["total"] == 0
    project, preview = import_fixture(client, "cube-m.step")
    service = application.state.import_service
    metadata = service.repository.preview(application.state.owner, preview["id"])["metadata"]
    from uuid import UUID

    blob = service.storage.blob_path(UUID(project), metadata["brep_sha256"])
    blob.chmod(0o600)
    blob.write_bytes(b"corrupted")
    response = client.post(
        f"/api/v1/geometry-imports/{preview['id']}/confirm",
        json={"dimensions_confirmed": True},
        headers={"If-Match": '"1"'},
    )
    assert response.status_code == 503 and response.json()["code"] == "artifact_integrity"


def test_sandbox_denies_host_files_source_mutation_network_and_fork(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "host-sentinel"
    secret.write_text("synthetic host access sentinel")
    worker = tmp_path / "worker/services/worker/worker/geometry_native/import_step.py"
    worker.parent.mkdir(parents=True)
    worker.write_text(f"""import json,pathlib,socket,os
checks={{}}
for name,action in [
 ('host_read',lambda:pathlib.Path({str(secret)!r}).read_bytes()),
 ('host_write',lambda:pathlib.Path({str(secret)!r}).write_text('changed')),
 ('source_write',lambda:pathlib.Path('/work/source.step').write_text('changed')),
 ('network',lambda:socket.socket()),('fork',lambda:os.fork())]:
    try: action(); checks[name]=False
    except (OSError,PermissionError): checks[name]=True
pathlib.Path('inspection.json').write_text(json.dumps({{'status':'needs_units','checks':checks}}))
""")
    monkeypatch.setattr(step_import, "ROOT", tmp_path / "worker")
    result = step_import.inspect_step(FIXTURES / "cube-m.step", tmp_path / "isolated")
    assert all(result["checks"].values()), result
    assert secret.read_text() == "synthetic host access sentinel"
