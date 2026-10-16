"""M4 fail-closed review and sequencing; synthetic orchestration is not physics evidence."""

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import m3_gate
from scripts.validation import m4_gate as gate
from worker.runtime import ROOT, sha256


def test_actual_packet_preserves_m3_and_blocks_pending_m4_before_any_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packet = gate.review_packet()
    assert set(packet["records"]) == set(gate.CASES) | {"M3", "M4"}
    assert {case for case, r in packet["records"].items() if r["approval_blocker"]} == {
        "B10",
        "B12",
        "B13",
        "B14",
        "M4",
    }
    monkeypatch.setattr(
        gate,
        "verified_tool",
        lambda _: pytest.fail("Pending acceptance must refuse before native setup"),
    )
    output = tmp_path / "reviewed"
    with pytest.raises(ValueError, match="Engineering-owner approval required"):
        gate.run_gate(output)
    assert not output.exists()


@pytest.mark.parametrize("name", ["B10", "M3"])
def test_changed_bound_criteria_refuse_before_output(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    read = Path.read_text

    def changed(path: Path, *args: Any, **kwargs: Any) -> str:
        raw = read(path, *args, **kwargs)
        if path == ROOT / f"tests/benchmarks/{name}.json":
            model = json.loads(raw)
            model["revision"] += 1
            return json.dumps(model)
        return raw

    monkeypatch.setattr(Path, "read_text", changed)
    with pytest.raises(ValueError, match="criteria changed"):
        gate.review_packet()


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    packet = gate.review_packet()
    packet["code_commit"] = "synthetic-orchestration-only"
    monkeypatch.setattr(gate, "review_packet", lambda: packet)
    tool = ROOT / "tests/benchmarks/B01.json"
    monkeypatch.setattr(gate, "verified_tool", lambda _: tool)
    calls = []

    def previous(output: Path, development: bool) -> dict[str, Any]:
        output.mkdir()
        return {
            "numerical_status": "PASS",
            "cases": {
                case: {"status": "PASS", "result": f"{case}/result.json"} for case in m3_gate.CASES
            },
        }

    def run(case: str, output: Path, development: bool) -> dict[str, Any]:
        calls.append(case)
        output.mkdir()
        record = {
            "case": case,
            "status": "DEVELOPMENT PASS; synthetic only" if development else "PASS",
            "code_commit": packet["code_commit"],
            "manifest_sha256": packet["records"][case]["manifest_sha256"],
            "ccx_sha256": sha256(tool),
        }
        (output / "result.json").write_text(json.dumps(record))
        return record

    monkeypatch.setattr(m3_gate, "run_gate", previous)
    monkeypatch.setattr(gate, "run_case", run)
    return {"packet": packet, "calls": calls, "run": run}


def test_development_replay_cannot_grant_benchmark_or_laptop_exit_and_never_overwrites(
    tmp_path: Path, records: dict[str, Any]
) -> None:
    output = tmp_path / "dev"
    result = gate.run_gate(output, True)
    assert result["numerical_status"] == "PASS" and result["benchmark_acceptance"] == "BLOCKED"
    assert result["m4_exit_status"].startswith("BLOCKED") and result["external_evidence_required"]
    assert records["calls"] == list(gate.ADDITIONAL)
    original = (output / "summary.json").read_bytes()
    with pytest.raises(ValueError, match="fresh output"):
        gate.run_gate(output, True)
    assert (output / "summary.json").read_bytes() == original


@pytest.mark.parametrize(
    "fault",
    [
        "resource",
        "raw_record",
        "case",
        "manifest_sha256",
        "ccx_sha256",
        "code_commit",
        "status",
        "source",
    ],
)
def test_interruption_identity_or_validation_failure_stops_later_references(
    tmp_path: Path, records: dict[str, Any], monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    def run(case: str, output: Path, development: bool) -> dict[str, Any]:
        result: dict[str, Any] = records["run"](case, output, development)
        if case == "B12":
            if fault == "resource":
                raise RuntimeError("Synthetic resource stop; not numerical evidence")
            if fault == "raw_record":
                (output / "result.json").write_text("{}")
            elif fault == "source":
                monkeypatch.setattr(gate, "review_packet", lambda: {"changed": True})
            else:
                result[fault] = "invalid"
                (output / "result.json").write_text(json.dumps(result))
        return result

    monkeypatch.setattr(gate, "run_case", run)
    result = gate.run_gate(tmp_path / "dev", True)
    assert result["numerical_status"] == "FAILED" and result["benchmark_acceptance"] == "BLOCKED"
    assert records["calls"] == ["B10", "B12"]
    assert result["cases"]["B12"]["status"] == "FAILED"
    assert result["cases"]["B13"]["status"] == "NOT RUN"
    assert result["cases"]["B14"]["status"] == "NOT RUN"


def test_even_reviewed_numerical_acceptance_never_self_approves_m4(
    tmp_path: Path, records: dict[str, Any]
) -> None:
    # Metadata-only simulation: no real review record or benchmark file is edited.
    for record in records["packet"]["records"].values():
        record["approval_blocker"] = None
    result = gate.run_gate(tmp_path / "reviewed")
    assert result["benchmark_acceptance"] == "PASS"
    assert result["m4_exit_status"].startswith("BLOCKED")
