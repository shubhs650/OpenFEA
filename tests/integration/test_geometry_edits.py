"""Native preview survives real API process restart; apply/undo preserve original bytes."""

import hashlib
import json
import urllib.request
from pathlib import Path

from tests.integration.test_local_jobs import configuration
from tests.integration.test_persistence import Browser, api_process


def test_cleanup_preview_apply_and_undo_survive_actual_api_restarts(tmp_path: Path) -> None:
    config = configuration(tmp_path)
    browser = Browser(config.port)
    with api_process(config, tmp_path / "preview.log"):
        status, session, _ = browser.request("GET", "/session")
        assert status == 200
        headers = {"X-CSRF-Token": session["csrf_token"]}
        status, project, _ = browser.request(
            "POST", "/projects", {"name": "Native cleanup restart"}, headers
        )
        assert status == 201
        raw = Path("tests/fixtures/geometry/hole-m.step").read_bytes()
        status, upload, _ = browser.request(
            "POST",
            f"/projects/{project['id']}/geometry-uploads",
            {"size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
            headers,
        )
        assert status == 201
        request = urllib.request.Request(
            browser.base + f"/geometry-uploads/{upload['id']}/content",
            data=raw,
            headers=headers,
            method="PUT",
        )
        with browser.opener.open(request, timeout=5) as response:
            assert response.status == 200
        status, inspection, _ = browser.request(
            "POST",
            f"/projects/{project['id']}/geometry-imports",
            {"upload_id": upload["id"]},
            headers | {"If-Match": '"1"'},
        )
        assert status == 201 and inspection["status"] == "ready"
        status, source, _ = browser.request(
            "POST",
            f"/geometry-imports/{inspection['id']}/confirm",
            {"dimensions_confirmed": True},
            headers | {"If-Match": '"1"'},
        )
        assert status == 200
        feature = next(
            f["id"]
            for f in source["faces"]
            if f["signature"]["surface_type"].endswith("GeomAbs_Cylinder")
        )
        status, edit, _ = browser.request(
            "POST",
            f"/geometry/{source['id']}/edits",
            {"operation": "remove_feature", "face_id": feature},
            headers | {"If-Match": '"2"'},
        )
        assert status == 201 and edit["status"] == "ready", edit
        display = browser.request("GET", f"/geometry-edits/{edit['id']}/display")[1]
    with api_process(config, tmp_path / "apply.log"):
        assert browser.request("GET", f"/geometry-edits/{edit['id']}")[0] == 401
        headers = {"X-CSRF-Token": browser.request("GET", "/session")[1]["csrf_token"]}
        assert browser.request("GET", f"/geometry-edits/{edit['id']}")[1] == edit
        assert browser.request("GET", f"/geometry-edits/{edit['id']}/display")[1] == display
        status, result, _ = browser.request(
            "POST",
            f"/geometry/{source['id']}/edit-commits",
            {"preview_id": edit["id"], "reviewed": True},
            headers | {"If-Match": '"2"'},
        )
        assert status == 200, result
        assert browser.request("GET", f"/geometry/{source['id']}")[1] == source
    with api_process(config, tmp_path / "undo.log"):
        headers = {"X-CSRF-Token": browser.request("GET", "/session")[1]["csrf_token"]}
        status, restored, _ = browser.request(
            "POST", f"/geometry-edits/{edit['id']}/undo", headers=headers | {"If-Match": '"3"'}
        )
        assert status == 200, restored
        assert restored["geometry"]["brep_sha256"] == source["brep_sha256"]
        assert browser.request("GET", f"/geometry/{source['id']}")[1] == source
        assert browser.request("GET", f"/geometry/{result['geometry']['id']}/display")[1] == display
        evidence = Path(".local/native/validation/T013")
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "restart.json").write_text(
            json.dumps(
                {
                    "preview_id": edit["id"],
                    "source": source["id"],
                    "applied": result["geometry"]["id"],
                    "restored": restored["geometry"]["id"],
                },
                indent=2,
            )
            + "\n"
        )
