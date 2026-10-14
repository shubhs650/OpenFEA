"""Actual mesh refusal, transaction races, owner/integrity and namespace checks."""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.domain.models import AnalysisPatch
from tests.native import test_step_import as step_tests
from tests.native.test_face_decks import assign, exported, setup
from worker import deck_mesh
from worker.runtime import ROOT

application = step_tests.application
client = step_tests.client


def test_force_on_fixed_dofs_refuses_without_redistribution(client: TestClient) -> None:
    path, geometry = setup(client)
    face = geometry["faces"][0]["id"]
    assign(client, path, geometry, "fixed", [face])
    state = assign(client, path, geometry, "force", [face], units="m-N-Pa", force=[100, 0, 0])
    result = client.post(
        path + "/deck-exports", headers={"If-Match": f'"{state["analysis_revision"]}"'}
    )
    assert result.status_code == 422 and result.json()["code"] == "force_on_fixed_dof"
    assert client.get(path + "/deck-exports").json() == []
    assert client.get(path + "/loads").json() == state


def test_export_owner_stale_csrf_tombstone_and_corruption(
    client: TestClient, application: FastAPI
) -> None:
    path, geometry = setup(client)
    fixed = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 0)
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 1)
    assign(client, path, geometry, "fixed", [fixed])
    state = assign(client, path, geometry, "force", [loaded], units="m-N-Pa", force=[100, 0, 0])
    assert client.post(path + "/deck-exports").status_code == 428
    assert client.post(path + "/deck-exports", headers={"If-Match": '"1"'}).status_code == 409
    assert (
        client.post(
            path + "/deck-exports",
            headers={"If-Match": f'"{state["analysis_revision"]}"', "X-CSRF-Token": "bad"},
        ).status_code
        == 403
    )
    metadata, deck = exported(client, path)
    store = application.state.repository
    foreign = uuid4()
    with store.write() as connection:
        connection.exec_driver_sql("INSERT INTO users VALUES (?,NULL,'test')", (str(foreign),))
        connection.exec_driver_sql(
            "UPDATE projects SET owner_id=? WHERE id=?", (str(foreign), geometry["project_id"])
        )
    for suffix in ("", "/input", "/snapshot"):
        assert client.get(f"/api/v1/deck-exports/{metadata['id']}" + suffix).status_code == 404
    with store.write() as connection:
        connection.exec_driver_sql(
            "UPDATE projects SET owner_id=? WHERE id=?",
            (str(application.state.owner), geometry["project_id"]),
        )
        for command in ("UPDATE deck_exports SET metadata_json='{}'", "DELETE FROM deck_exports"):
            with pytest.raises(IntegrityError, match="immutable"):
                connection.exec_driver_sql(command)
    storage = application.state.deck_service.storage
    blob = storage.blob_path(UUID(geometry["project_id"]), metadata["deck_sha256"])
    blob.chmod(0o600)
    blob.write_text("corrupted")
    assert client.get(f"/api/v1/deck-exports/{metadata['id']}/input").status_code == 503
    assert (
        client.post(
            path + "/deck-exports", headers={"If-Match": f'"{state["analysis_revision"]}"'}
        ).status_code
        == 503
    )
    blob.write_text(deck)
    assert (
        client.delete(
            f"/api/v1/projects/{geometry['project_id']}", headers={"If-Match": '"2"'}
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/deck-exports/{metadata['id']}/input").status_code == 404


def test_edit_during_export_cannot_publish_stale_inputs(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.domain import deck_service

    path, geometry = setup(client)
    fixed = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 0)
    loaded = next(f["id"] for f in geometry["faces"] if f["signature"]["center_m"][0] == 1)
    assign(client, path, geometry, "fixed", [fixed])
    state = assign(client, path, geometry, "force", [loaded], units="m-N-Pa", force=[100, 0, 0])
    original = deck_mesh.mesh_snapshot

    def concurrent(
        inputs: Path, output: Path, sizes: list[float], **options: Any
    ) -> dict[str, Any]:
        mesh = original(inputs, output, sizes, **options)
        application.state.repository.edit_analysis(
            application.state.owner,
            UUID(path.split("/")[-1]),
            state["analysis_revision"],
            AnalysisPatch(name="Concurrent edit"),
        )
        return mesh

    monkeypatch.setattr(deck_service, "mesh_snapshot", concurrent)
    result = client.post(
        path + "/deck-exports", headers={"If-Match": f'"{state["analysis_revision"]}"'}
    )
    assert result.status_code == 409 and result.json()["code"] == "stale_revision"
    assert client.get(path + "/deck-exports").json() == []


def test_curved_geometry_saves_force_but_planar_export_refuses(client: TestClient) -> None:
    path, geometry = setup(client, "cylinder-m.step")
    curved = next(f for f in geometry["faces"] if "Cylinder" in f["signature"]["surface_type"])
    assign(client, path, geometry, "fixed", [geometry["faces"][-1]["id"]])
    state = assign(
        client, path, geometry, "force", [curved["id"]], units="m-N-Pa", force=[0, 0, 100]
    )
    result = client.post(
        path + "/deck-exports", headers={"If-Match": f'"{state["analysis_revision"]}"'}
    )
    assert result.status_code == 422 and result.json()["code"] == "unsupported_mesh"
    result = client.post(
        path + "/loads",
        json={
            "assignment": {
                "kind": "pressure",
                "name": "Curved pressure",
                "geometry_revision_id": geometry["id"],
                "face_ids": [curved["id"]],
                "units": "m-N-Pa",
                "pressure": 10,
            }
        },
        headers={"If-Match": f'"{state["analysis_revision"]}"'},
    )
    assert result.status_code == 422 and result.json()["code"] == "unsupported_pressure_face"


def test_mesh_namespace_denies_network_fork_private_files_and_input_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ROOT / "work/t010" / str(uuid4())
    script = root / "services/worker/worker/meshing_native/build.py"
    script.parent.mkdir(parents=True)
    sentinel = tmp_path / "private"
    sentinel.write_text("PRIVATE_SENTINEL")
    script.write_text(
        """import json,os,socket
from pathlib import Path
value={}
operations=[('network',lambda:socket.socket()),('fork',lambda:os.fork()),
            ('write',lambda:Path('catalog.json').write_text('bad'))]
for key,fn in operations:
    try: fn(); value[key]=False
    except OSError: value[key]=True
value['private_hidden']=not Path("""
        + repr(str(sentinel))
        + """).exists()
Path('mesh.json').write_text(json.dumps(value))
Path('mesh-status.json').write_text(json.dumps({'status':'passed'}))
"""
    )
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "catalog.json").write_text("{}")
    monkeypatch.setattr(deck_mesh, "ROOT", root)
    # Trusted isolation probe only, not a numerically valid mesh/job.
    result = deck_mesh._mesh_attempt(inputs, tmp_path / "out", [0.5])
    assert result == {"network": True, "fork": True, "write": True, "private_hidden": True}


@pytest.mark.parametrize(
    "finish_before_sampling", [False, True], ids=["live", "finished-before-first-sample"]
)
def test_mesh_recovery_stops_at_aggregate_retained_scratch_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finish_before_sampling: bool
) -> None:
    import json
    import subprocess

    from worker.local_process import NativeStop

    root = ROOT / "work/t014" / str(uuid4())
    script = root / "services/worker/worker/meshing_native/build.py"
    script.parent.mkdir(parents=True)
    # Controlled native resource probe, never a numerically accepted mesh.
    script.write_text(
        "from pathlib import Path\nimport time\n"
        "Path('allocation').write_bytes(b'x' * (70 * 1024**2))\ntime.sleep(5)\n"
    )
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    monkeypatch.setattr(deck_mesh, "ROOT", root)
    original = deck_mesh._mesh_attempt
    launched = []

    def retained(inputs: Path, output: Path, sizes: list[float], **options: Any) -> dict[str, Any]:
        # Represents retained previous attempt artifacts, outside the new child.
        with (output.parent / "retained-allocation").open("wb") as allocation:
            allocation.truncate(128 * 1024**2)
        launched.append(output.name)
        return original(inputs, output, sizes, **options)

    monkeypatch.setattr(deck_mesh, "_mesh_attempt", retained)
    if finish_before_sampling:
        launch = subprocess.Popen

        def finished(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
            process = launch(*args, **kwargs)
            # The real isolated writer exceeds its unchanged 64-MiB file cap.
            # Wait for that actual exit before exposing the process to sampling.
            process.wait(timeout=5)
            return process

        monkeypatch.setattr(subprocess, "Popen", finished)
    with pytest.raises(NativeStop, match="resource_exceeded"):
        deck_mesh.mesh_snapshot(inputs, tmp_path / "out", [0.5], recovery_enabled=True)
    assert launched == ["attempt-1"]
    report = json.loads((tmp_path / "out/recovery.json").read_bytes())
    assert report["mesh_attempts"][0]["status"] == "resource_exceeded"
    assert report["sizing_unchanged"] and not (tmp_path / "out/attempt-2").exists()
    resources = json.loads((tmp_path / "out/mesh-attempt-1-resources.json").read_bytes())
    assert resources["peak_scratch_bytes"] > 192 * 1024**2
    assert (tmp_path / "out/mesh-attempt-1.log").is_file()
