"""Frozen fourteen-case M4 review/replay; automation cannot grant laptop/owner acceptance."""

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.validation import m3_gate
from worker.approval import criteria_sha256, require_benchmark_approval
from worker.benchmark import run_case
from worker.runtime import ROOT, sha256, verified_tool

ADDITIONAL = ("B10", "B12", "B13", "B14")
CASES = (*m3_gate.CASES, *ADDITIONAL)
MANIFEST = "tests/benchmarks/M4.json"


def review_packet() -> dict[str, Any]:
    previous = m3_gate.review_packet()
    gate = json.loads((ROOT / MANIFEST).read_text())
    manifests = {
        case: json.loads((ROOT / f"tests/benchmarks/{case}.json").read_text())
        for case in ADDITIONAL
    }
    expected = {case: record["criteria_sha256"] for case, record in previous["records"].items()}
    expected.update({case: criteria_sha256(manifest) for case, manifest in manifests.items()})
    if gate["required_criteria_sha256"] != expected:
        raise ValueError("M4 required criteria changed; review the gate manifest")
    for name, digest in gate["frozen_contracts_sha256"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError(f"M4 reviewed contract changed: {name}")
    records = dict(previous["records"])
    manifests["M4"] = gate
    for case, manifest in manifests.items():
        try:
            require_benchmark_approval(manifest, development=False)
            blocker = None
        except ValueError as error:
            blocker = str(error)
        name = MANIFEST if case == "M4" else f"tests/benchmarks/{case}.json"
        records[case] = {
            "manifest": name,
            "manifest_sha256": sha256(ROOT / name),
            "criteria_sha256": criteria_sha256(manifest),
            "reviewer_signoff": manifest["reviewer_signoff"],
            "approval_blocker": blocker,
        }
    return {
        "gate": "M4",
        "records": records,
        "scope": gate["scope"],
        "external_evidence_required": gate["external_evidence_required"],
        **m3_gate.snapshot(),
    }


def run_gate(output: Path, development: bool = False) -> dict[str, Any]:
    packet = review_packet()
    blockers = [case for case, record in packet["records"].items() if record["approval_blocker"]]
    if blockers and not development:
        raise ValueError(
            "Engineering-owner approval required before M4 acceptance execution: "
            + ", ".join(blockers)
        )
    if output.exists():
        raise ValueError(
            "M4 gate requires a fresh output directory; retained evidence is immutable"
        )
    tools = {name + "_sha256": sha256(verified_tool(name)) for name in ("ccx", "netdeny")}
    output.mkdir(parents=True)
    (output / "review-packet.json").write_text(json.dumps(packet, indent=2, allow_nan=False) + "\n")
    report: dict[str, Any] = {
        "gate": "M4",
        "development": development,
        "code_commit": packet["code_commit"],
        "sources": packet["sources"],
        **tools,
        "started_at": datetime.now(UTC).isoformat(),
        "approval_blockers": blockers,
        "cases": {
            case: {"status": "NOT RUN", "reason": "Earlier required case did not complete"}
            for case in CASES
        },
        "m4_exit_status": "BLOCKED; target-laptop/browser/usability evidence "
        "and owner exit review remain separate",
        "external_evidence_required": packet["external_evidence_required"],
    }
    failed = False
    try:
        if review_packet() != packet:
            raise ValueError("Reviewed inputs changed before M4 execution")
        previous = m3_gate.run_gate(output / "M3", development)
        report["cases"].update(
            {
                case: dict(record, result="M3/" + record["result"])
                if "result" in record
                else record
                for case, record in previous["cases"].items()
            }
        )
        if previous["numerical_status"] != "PASS":
            failed = True
        for case in ADDITIONAL if not failed else ():
            print(f"M4: running {case}", flush=True)
            try:
                if review_packet() != packet:
                    raise ValueError("Reviewed inputs changed during M4 execution")
                result = run_case(case, output / case, development)
                expected = "DEVELOPMENT PASS" if development else "PASS"
                if not (
                    result["status"].startswith(expected)
                    if development
                    else result["status"] == expected
                ):
                    raise ValueError("Benchmark did not return requested passing disposition")
                saved = json.loads((output / case / "result.json").read_text())
                if saved != json.loads(json.dumps(result, allow_nan=False)):
                    raise ValueError("Saved benchmark differs from returned evidence")
                if (
                    result["case"] != case
                    or result["code_commit"] != packet["code_commit"]
                    or result["manifest_sha256"] != packet["records"][case]["manifest_sha256"]
                    or result["ccx_sha256"] != tools["ccx_sha256"]
                    or review_packet() != packet
                ):
                    raise ValueError("Benchmark source/manifest/tool identity changed")
                report["cases"][case] = {
                    "status": "PASS",
                    "disposition": result["status"],
                    "result": f"{case}/result.json",
                }
            except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
                report["cases"][case] = {
                    "status": "FAILED",
                    "reason": f"{type(error).__name__}: {error}",
                }
                failed = True
                break
        if review_packet() != packet:
            raise ValueError("Reviewed inputs changed before M4 evidence publication")
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        failed = True
        report["failure"] = f"{type(error).__name__}: {error}"
    report["numerical_status"] = "FAILED" if failed else "PASS"
    report["benchmark_acceptance"] = "BLOCKED" if failed or development or blockers else "PASS"
    report["completed_at"] = datetime.now(UTC).isoformat()
    report["artifacts_sha256"] = {
        str(p.relative_to(output)): sha256(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--review-packet", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local/native/validation/T030/benchmarks"
    )
    args = parser.parse_args()
    try:
        report = review_packet() if args.review_packet else run_gate(args.output, args.development)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"BLOCKED/FAILED: {error}\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if args.review_packet or report["numerical_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
