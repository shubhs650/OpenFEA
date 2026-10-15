"""Real two-mesh comparison survives the shared model and PDF with original semantics."""

import hashlib
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain import report_service
from tests.native import test_step_import as step_tests
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.native.test_mesh_controls import controls
from tests.native.test_result_comparison import request as comparison_request
from tests.reports.test_reports import OUT, payload, pdf_text
from worker.reports.render import render_pdf

application = step_tests.application
client = step_tests.client


def test_two_mesh_comparison_retained_and_other_run_deletion_refuses_publication(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, geometry = prepared(client)
    first_mesh = wait_job(client, submit(client, path)["id"])
    first = wait_job(client, submit(client, path, first_mesh["id"])["id"])
    controls(client, path, global_size=0.3)
    second_mesh = wait_job(client, submit(client, path)["id"])
    second = wait_job(client, submit(client, path, second_mesh["id"])["id"])
    assert first["status"] == second["status"] == "succeeded"
    wires = [
        client.get(f"/api/v1/jobs/{r['id']}/artifacts/mesh.json").json() for r in (first, second)
    ]
    request = payload(geometry["bodies"][0]["id"])
    request["comparison"] = comparison_request(
        second, wires[0], wires[1], geometry["bodies"][0]["id"], field="ux"
    )
    route = f"/api/v1/runs/{first['id']}/reports"
    response = client.post(route, json=request)
    assert response.status_code == 201, response.text
    record = response.json()
    base = f"/api/v1/reports/{record['id']}"
    model = client.get(base + "/model").json()
    compare = model["comparison"]
    assert not compare["convergence_claim"]
    assert compare["reference"]["elements"] != compare["compared"]["elements"]
    assert compare["compared"]["source"]["job_id"] == second["id"]
    for row in compare["rows"]:
        expected = -1000 * row["sample"]["point_m"][0] / 210e9
        assert row["change"]["reference"] == pytest.approx(expected, abs=1e-13)
        assert row["change"]["compared"] == pytest.approx(expected, abs=1e-13)
    assert compare["rows"][1]["change"]["relative_change"] is None
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = client.get(base + "/pdf").content
    (OUT / "comparison.pdf").write_bytes(pdf)
    text = pdf_text(OUT / "comparison.pdf")
    assert "no convergence certification" in text
    assert "Compared run" in text and second["id"] in text
    assert "Native peaks may move" in text
    assert hashlib.sha256(pdf).hexdigest() == record["pdf_sha256"]
    # The second run is independently rechecked after renderer completion.
    service = application.state.report_service
    blob = service.storage.blob_path(
        UUID(geometry["project_id"]), second["artifacts"]["analysis.dat"]["sha256"]
    )

    def expire_compared(directory: Path) -> dict[str, str]:
        audit = render_pdf(directory)
        blob.unlink()
        return audit

    monkeypatch.setattr(report_service, "render_pdf", expire_compared)
    assert client.post(route, json=request).status_code == 503
    assert len(client.get(route).json()) == 1
