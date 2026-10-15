"""Gate orchestration tests; synthetic records here never count as physics evidence."""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import m3_gate as gate
from worker.runtime import ROOT, sha256


def test_current_required_criteria_are_exact_and_unsigned_acceptance_cannot_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = gate.review_packet()
    assert set(packet["records"]) == set(gate.CASES) | {"M3"}
    for record in packet["records"].values():
        record["approval_blocker"] = "Synthetic pending review"
    monkeypatch.setattr(gate, "review_packet", lambda: packet)
    output = tmp_path / "acceptance"
    with pytest.raises(ValueError, match="Engineering-owner approval required"):
        gate.run_gate(output)
    assert not output.exists()


def test_changed_physical_criteria_invalidate_the_whole_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = Path.read_text

    def altered(path: Path, *args: Any, **kwargs: Any) -> str:
        raw = read(path, *args, **kwargs)
        if path == ROOT / gate.MANIFESTS["B03"]:
            manifest = json.loads(raw)
            manifest["tolerances"]["stress_relative"] *= 2
            return json.dumps(manifest)
        return raw

    monkeypatch.setattr(Path, "read_text", altered)
    with pytest.raises(ValueError, match="criteria changed"):
        gate.review_packet()


def test_changed_formulation_invalidates_the_whole_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    real = sha256
    monkeypatch.setattr(
        gate, "sha256", lambda path: "0" * 64 if path.name == "ADR-028.md" else real(path)
    )
    with pytest.raises(ValueError, match="reviewed contract changed"):
        gate.review_packet()


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    packet = gate.review_packet()
    for record in packet["records"].values():
        record["approval_blocker"] = "Synthetic pending review"
    frozen = {"code_commit": "synthetic-orchestration-only", "sources": {"fixture": "abc"}}
    packet.update(frozen)
    monkeypatch.setattr(gate, "snapshot", lambda: frozen)
    monkeypatch.setattr(gate, "review_packet", lambda: packet)
    tool = ROOT / "tests/benchmarks/B01.json"
    monkeypatch.setattr(gate, "verified_tool", lambda _name: tool)
    calls: list[str] = []

    def run(case: str, output: Path, development: bool) -> dict[str, Any]:
        calls.append(case)
        output.mkdir()
        result = {
            "case": case,
            "native_vector": (1.0, 2.0, 3.0),
            "code_commit": frozen["code_commit"],
            "manifest_sha256": packet["records"][case]["manifest_sha256"],
            "ccx_sha256": sha256(tool),
            "status": "DEVELOPMENT PASS; synthetic metadata only" if development else "PASS",
        }
        (output / "result.json").write_text(json.dumps(result))
        return result

    monkeypatch.setattr(gate, "run_case", run)
    return {"packet": packet, "frozen": frozen, "calls": calls, "run": run}


def test_development_pass_cannot_grant_acceptance_and_evidence_is_immutable(
    tmp_path: Path, records: dict[str, Any]
) -> None:
    output = tmp_path / "development"
    result = gate.run_gate(output, development=True)
    assert result["numerical_status"] == "PASS"
    assert result["benchmark_acceptance"] == "BLOCKED"
    assert result["m3_exit_status"].startswith("NOT DETERMINED")
    assert records["calls"] == list(gate.CASES)
    assert set(result["approval_blockers"]) == set(gate.MANIFESTS)
    for name, digest in result["artifacts_sha256"].items():
        assert sha256(output / name) == digest
    original = (output / "summary.json").read_bytes()
    with pytest.raises(ValueError, match="fresh output directory"):
        gate.run_gate(output, development=True)
    assert (output / "summary.json").read_bytes() == original


@pytest.mark.parametrize(
    "fault",
    [
        "resource",
        "wrong_manifest",
        "wrong_tool",
        "wrong_commit",
        "wrong_case",
        "saved_record",
        "nonpassing",
        "source_changed",
    ],
)
def test_failure_retains_diagnostics_and_never_runs_later_cases(
    tmp_path: Path, records: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    def run(case: str, output: Path, development: bool) -> dict[str, Any]:
        result: dict[str, Any] = records["run"](case, output, development)
        if case == "B02":
            if fault == "resource":
                (output / "solver.log").write_text("Synthetic resource-stop orchestration record")
                raise RuntimeError("Synthetic resource stop")
            if fault == "source_changed":
                monkeypatch.setattr(
                    gate, "snapshot", lambda: {"code_commit": "changed", "sources": {}}
                )
            elif fault == "saved_record":
                (output / "result.json").write_text("{}")
            else:
                key = {
                    "wrong_manifest": "manifest_sha256",
                    "wrong_tool": "ccx_sha256",
                    "wrong_commit": "code_commit",
                    "wrong_case": "case",
                    "nonpassing": "status",
                }[fault]
                result[key] = "incorrect"
                (output / "result.json").write_text(json.dumps(result))
        return result

    monkeypatch.setattr(gate, "run_case", run)
    output = tmp_path / fault
    result = gate.run_gate(output, development=True)
    assert records["calls"] == ["B01", "B02"]
    assert result["numerical_status"] == "FAILED" and result["benchmark_acceptance"] == "BLOCKED"
    assert result["cases"]["B01"]["status"] == "PASS"
    assert result["cases"]["B02"]["status"] == "FAILED"
    assert all(result["cases"][case]["status"] == "NOT RUN" for case in gate.CASES[2:])
    assert json.loads((output / "summary.json").read_text()) == result


def test_missing_required_tool_cannot_start_a_job(
    tmp_path: Path, records: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(_name: str) -> Path:
        raise RuntimeError("Required native tool unavailable")

    monkeypatch.setattr(gate, "verified_tool", missing)
    output = tmp_path / "missing"
    with pytest.raises(RuntimeError, match="Required native tool"):
        gate.run_gate(output, development=True)
    assert not records["calls"] and not output.exists()


def test_reviewed_benchmarks_still_cannot_self_approve_the_product_exit(
    tmp_path: Path, records: dict[str, Any]
) -> None:
    # Synthetic review metadata tests orchestration only; committed records stay PENDING.
    for record in records["packet"]["records"].values():
        record["approval_blocker"] = None
    result = gate.run_gate(tmp_path / "synthetic-reviewed")
    assert result["benchmark_acceptance"] == "PASS"
    assert result["m3_exit_status"].startswith("NOT DETERMINED")


def test_source_change_after_review_packet_cannot_start_a_native_case(
    tmp_path: Path, records: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gate, "snapshot", lambda: {"code_commit": "changed", "sources": {}})
    result = gate.run_gate(tmp_path / "changed-before-start", development=True)
    assert records["calls"] == []
    assert result["numerical_status"] == "FAILED"
    assert result["code_commit"] == records["packet"]["code_commit"]
    assert result["cases"]["B01"]["status"] == "FAILED"
    assert all(result["cases"][case]["status"] == "NOT RUN" for case in gate.CASES[1:])
