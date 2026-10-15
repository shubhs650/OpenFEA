"""Real STEP/Gmsh/CCX -> historical report -> actual offline Chromium A4 PDF."""

import fcntl
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain import report_service
from app.domain.errors import DomainError
from app.domain.reports import ReportModel, ReportRequest, ReportTable
from tests.native import test_step_import as step_tests
from tests.native.test_local_jobs import prepared, submit, wait_job
from tests.unit.test_materials import custom
from worker.reports.html import report_html
from worker.reports.render import render_pdf

application = step_tests.application
client = step_tests.client

OUT = Path(".local/reports/T025")


def payload(body: str) -> dict[str, Any]:
    return {
        "title": "T025 historical <analysis>",
        "units": "mm-N-MPa",
        "user_conclusion": "User conclusion <script>alert('x')</script> & review required.",
        "views": [
            {
                "field": "sxx",
                "smoothed": True,
                "deformation_scale": 50,
                "range_si": [-1200, -800],
                "visible_body_ids": [body],
                "camera": {
                    "position": [2, 2, 2],
                    "focal": [0, 0, 0],
                    "up": [0, 0, 1],
                    "parallel": True,
                    "parallel_scale": 1.1,
                    "angle": 30,
                },
                "section": None,
            }
        ],
    }


def pdf_text(path: Path) -> str:
    if not shutil.which("pdftotext"):
        pytest.fail("Poppler pdftotext is required for report content/layout verification")
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], check=True, capture_output=True, text=True
    ).stdout


def assert_a4_bounds(path: Path) -> int:
    raw = subprocess.run(
        ["pdftotext", "-bbox", str(path), "-"], check=True, capture_output=True
    ).stdout
    root = ET.fromstring(raw)
    pages = root.findall(".//{*}page")
    assert pages
    for page in pages:
        w, h = float(page.attrib["width"]), float(page.attrib["height"])
        assert abs(w - 595.28) < 1 and abs(h - 841.89) < 1
        for word in page.findall(".//{*}word"):
            assert 25 <= float(word.attrib["xMin"]) < float(word.attrib["xMax"]) <= w - 25, (
                word.attrib
            )
            assert 15 <= float(word.attrib["yMin"]) < float(word.attrib["yMax"]) <= h - 15, (
                word.attrib
            )
    return len(pages)


def test_actual_historical_pdf_security_retention_and_layout(
    client: TestClient, application: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:  # noqa: F811
    path, geometry = prepared(client)
    material = custom()
    material["material"]["values"]["yield_strength"] = 0.0005
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=material,
            headers={"If-Match": '"4"'},
        ).status_code
        == 200
    )
    mesh = wait_job(client, submit(client, path)["id"])
    run = wait_job(client, submit(client, path, mesh["id"])["id"])
    assert run["status"] == "succeeded", run
    raw_path = f"/api/v1/jobs/{run['id']}/artifacts/results.json"
    raw = client.get(raw_path).content
    request = payload(geometry["bodies"][0]["id"])
    request["views"].append(
        {
            **request["views"][0],
            "field": "displacement",
            "range_si": [0, 1e-8],
            "deformation_scale": 0,
            "section": {"point_m": [0.5, 0.5, 0.5], "normal": [1, 0, 0]},
        }
    )

    route = f"/api/v1/runs/{run['id']}/reports"
    # Current setup changes cannot change a report on the old selected run.
    rev = client.get(path).json()["revision"]
    assert (
        client.patch(
            path, json={"name": "Later edited analysis"}, headers={"If-Match": f'"{rev}"'}
        ).status_code
        == 200
    )
    later = custom()
    later["material"]["values"]["yield_strength"] = 250
    assert (
        client.put(
            path + "/materials/" + geometry["bodies"][0]["id"],
            json=later,
            headers={"If-Match": f'"{rev + 1}"'},
        ).status_code
        == 200
    )
    assert client.post(route, json=request, headers={"X-CSRF-Token": ""}).status_code == 403
    assert client.post(f"/api/v1/runs/{mesh['id']}/reports", json=request).status_code == 409
    bad = json.loads(json.dumps(request))
    bad["views"][0]["visible_body_ids"] = ["another-body"]
    assert client.post(route, json=bad).status_code == 422
    service = application.state.report_service
    with pytest.raises(DomainError) as denied:
        service.create(uuid4(), UUID(run["id"]), ReportRequest.model_validate(request))
    assert denied.value.status == 404
    with (service.storage.root / "report.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert client.post(route, json=request).status_code == 429
    response = client.post(route, json=request)
    assert response.status_code == 201, response.text
    record = response.json()
    base = f"/api/v1/reports/{record['id']}"
    outputs = {kind: client.get(base + "/" + kind) for kind in ("model", "html", "pdf")}
    assert all(r.status_code == 200 for r in outputs.values())
    model = ReportModel.model_validate(outputs["model"].json())
    assert model.source.analysis_revision == rev
    assert model.frozen_input.snapshot.analysis.name != "Later edited analysis"
    assert model.request.units == "mm-N-MPa" and model.request.views[0].range_si == (-1200, -800)
    assert model.request.views[0].camera.parallel
    assert (
        model.frozen_input.snapshot.materials.assignments[0].material.properties.yield_strength_pa
        == 500
    )
    assert model.generator["source_commit"] and model.generator["chromium_binary_sha256"]
    assert any("does not model plastic" in w for w in model.warnings)
    assert len(model.assumptions) >= 3
    assert "<script>" not in outputs["html"].text
    assert "&lt;script&gt;" in outputs["html"].text
    assert "sandbox" in outputs["html"].headers["content-security-policy"]
    for kind, r in outputs.items():
        assert (
            hashlib.sha256(r.content).hexdigest()
            == record[{"model": "model_sha256", "html": "html_sha256", "pdf": "pdf_sha256"}[kind]]
        )
        with pytest.raises(DomainError) as denied:
            service.artifact(uuid4(), UUID(record["id"]), kind)
        assert denied.value.status == 404
    OUT.mkdir(parents=True, exist_ok=True)
    for kind, suffix in (("model", "json"), ("html", "html"), ("pdf", "pdf")):
        (OUT / f"historical.{suffix}").write_bytes(outputs[kind].content)
    (OUT / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    text = pdf_text(OUT / "historical.pdf")
    for expected in (
        "Raw native extrema",
        "Material provenance",
        "Force and moment equilibrium",
        "User-written conclusion",
        "Reproducibility IDs",
        "T025 historical <analysis>",
        run["id"],
    ):
        assert expected in text
    assert "Later edited analysis" not in text
    assert "-0.0012" in text and "-0.0008" in text
    assert assert_a4_bounds(OUT / "historical.pdf") >= 4
    # A long table from the SAME shared model must paginate with repeated headers.
    long_table = ReportTable(
        title="Long material table",
        columns=["Material provenance row", "Source / condition"],
        rows=[[f"Material {i:03d}", "Long source title " * 8 + f" END-{i:03d}"] for i in range(90)],
    )
    long_model = model.model_copy(update={"tables": [long_table, *model.tables]})
    render_dir = tmp_path / "long-layout"
    render_dir.mkdir()
    (render_dir / "report.html").write_text(report_html(long_model))
    audit = render_pdf(render_dir)
    shutil.copyfile(render_dir / "report.pdf", OUT / "long-table.pdf")
    long_text = pdf_text(OUT / "long-table.pdf")
    assert "END-000" in long_text and "END-089" in long_text
    assert long_text.count("Material provenance row") >= 3
    pages = assert_a4_bounds(OUT / "long-table.pdf")
    (OUT / "layout.json").write_text(
        json.dumps({"long_table_pages": pages, "long_table_renderer": audit}, indent=2) + "\n"
    )
    assert client.get(raw_path).content == raw
    # Missing retained DAT forbids NEW reports; existing generated bytes remain downloadable.
    blob = service.storage.blob_path(
        UUID(geometry["project_id"]), run["artifacts"]["analysis.dat"]["sha256"]
    )
    native = blob.read_bytes()
    blob.unlink()
    assert client.post(route, json=request).status_code == 503
    assert client.get(base + "/pdf").content == outputs["pdf"].content
    blob.write_bytes(native)

    # Renderer failure must never create a success record or leave scratch behind.
    def failed(directory: Path) -> dict[str, str]:
        raise RuntimeError("deliberate renderer failure")

    monkeypatch.setattr(report_service, "render_pdf", failed)
    assert client.post(route, json=request).status_code == 503
    assert len(client.get(route).json()) == 1
    assert not list((service.storage.root / "exports").glob("*"))
    # Source deletion at publication refuses the newly generated report.
    real_render = render_pdf

    def delete_source(directory: Path) -> dict[str, str]:
        audit = real_render(directory)
        blob.unlink()
        return audit

    monkeypatch.setattr(report_service, "render_pdf", delete_source)
    assert client.post(route, json=request).status_code == 503
    assert len(client.get(route).json()) == 1
    blob.write_bytes(native)
    pdf_blob = service.storage.blob_path(UUID(record["project_id"]), record["pdf_sha256"])
    pdf_original = pdf_blob.read_bytes()
    pdf_blob.chmod(0o600)
    pdf_blob.write_bytes(b"corrupt")
    assert client.get(base + "/pdf").status_code == 503
    pdf_blob.write_bytes(pdf_original)
    # Published record is append-only, and access follows project tombstones.
    from sqlalchemy import text as sql
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), service.projects.write() as connection:
        connection.execute(
            sql("UPDATE reports SET record_json='{}' WHERE id=:id"), {"id": record["id"]}
        )
    # A newly opened API/database reads exactly the same immutable report bytes.
    from app.main import create_app

    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 55001)
    ) as reopened:
        reopened.get("/api/v1/session")
        assert reopened.get(base + "/pdf").content == outputs["pdf"].content
        assert reopened.get(base + "/model").content == outputs["model"].content
    project = client.get(f"/api/v1/projects/{geometry['project_id']}").json()
    assert (
        client.delete(
            f"/api/v1/projects/{geometry['project_id']}",
            headers={"If-Match": f'"{project["revision"]}"'},
        ).status_code
        == 204
    )
    assert client.get(base).status_code == 404
    assert client.get(base + "/pdf").status_code == 404
