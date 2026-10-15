"""Real reports and editable Word survive portable, nonexecuting history import."""

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from tests.native import test_step_import as step_tests
from tests.native.test_archives import export, restore
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.reports.test_reports import payload

application = step_tests.application
client = step_tests.client


def test_actual_pdf_word_model_views_roundtrip(client: TestClient) -> None:
    path, geometry = prepared(client)
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    report_response = client.post(
        f"/api/v1/runs/{run['id']}/reports", json=payload(geometry["bodies"][0]["id"])
    )
    assert report_response.status_code == 201, report_response.text
    report = report_response.json()
    word_response = client.post(f"/api/v1/reports/{report['id']}/exports/word", json={})
    assert word_response.status_code == 201, word_response.text
    word = word_response.json()
    _, raw = export(client, geometry["project_id"], True)
    imported = restore(client, raw)
    originals = {
        report["id"]: {
            "model.json": client.get(f"/api/v1/reports/{report['id']}/model").content,
            "report.pdf": client.get(f"/api/v1/reports/{report['id']}/pdf").content,
        },
        word["id"]: {"report.docx": client.get(f"/api/v1/word-exports/{word['id']}/docx").content},
    }
    for source, files in originals.items():
        item = next(h for h in imported["history"] if h["source_id"] == source)
        assert item["id"] != source
        for name, data in files.items():
            response = client.get(
                f"/api/v1/archive-imports/{imported['id']}/history/{item['id']}/{name}"
            )
            assert response.status_code == 200, response.text
            assert response.content == data
            assert response.headers["content-type"] == "application/octet-stream"
            assert "attachment" in response.headers["content-disposition"]
            assert "sandbox" in response.headers["content-security-policy"]
            assert hashlib.sha256(data).hexdigest() == item["files"][name]
    assert client.get(f"/api/v1/reports/{imported['id_map'][report['id']]}").status_code == 404
    out = Path(".local/archives/T027")
    out.mkdir(parents=True, exist_ok=True)
    (out / "with-reports.zip").write_bytes(raw)
