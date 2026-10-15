"""Run the frozen M3 subset without converting diagnostics into owner acceptance."""

import argparse
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from worker.approval import criteria_sha256, require_benchmark_approval
from worker.benchmark import run_case
from worker.runtime import ROOT, sha256, verified_tool

CASES = ("B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B09", "B11")
MANIFESTS = {case: f"tests/benchmarks/{case}.json" for case in CASES} | {
    "B07": "tests/benchmarks/B07-mortar.json",
    "M3": "tests/benchmarks/M3.json",
}


def snapshot() -> dict[str, Any]:
    """Hash actual tracked engineering inputs, independently of a clean git label."""
    files = subprocess.check_output(
        [
            "git",
            "ls-files",
            "services",
            "scripts",
            "tests",
            "migrations",
            "packages",
            "apps",
            "Makefile",
            "pyproject.toml",
            "uv.lock",
            "package.json",
            "package-lock.json",
        ],
        cwd=ROOT,
        text=True,
    ).splitlines()
    return {
        "code_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "sources": {name: sha256(ROOT / name) for name in files},
    }


def review_packet() -> dict[str, Any]:
    manifests = {case: json.loads((ROOT / name).read_text()) for case, name in MANIFESTS.items()}
    gate = manifests["M3"]
    expected = {case: criteria_sha256(manifests[case]) for case in CASES}
    if gate["required_criteria_sha256"] != expected:
        raise ValueError("M3 required benchmark criteria changed; review the gate manifest")
    for name, digest in gate["frozen_contracts_sha256"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError(f"M3 reviewed contract changed: {name}")
    records = {}
    for case, manifest in manifests.items():
        try:
            require_benchmark_approval(manifest, development=False)
            refusal = None
        except ValueError as error:
            refusal = str(error)
        records[case] = {
            "manifest": MANIFESTS[case],
            "manifest_sha256": sha256(ROOT / MANIFESTS[case]),
            "criteria_sha256": criteria_sha256(manifest),
            "reviewer_signoff": manifest["reviewer_signoff"],
            "approval_blocker": refusal,
        }
    return {"records": records, "scope": gate["scope"], **snapshot()}


def run_gate(output: Path, development: bool = False) -> dict[str, Any]:
    packet = review_packet()
    blockers = [case for case, record in packet["records"].items() if record["approval_blocker"]]
    if blockers and not development:
        raise ValueError(
            "Engineering-owner approval required before acceptance execution: "
            + ", ".join(blockers)
        )
    if output.exists():
        raise ValueError(
            "M3 gate requires a fresh output directory; retained evidence is immutable"
        )
    tools = {
        "ccx_sha256": sha256(verified_tool("ccx")),
        "netdeny_sha256": sha256(verified_tool("netdeny")),
    }
    output.mkdir(parents=True)
    (output / "review-packet.json").write_text(json.dumps(packet, indent=2, allow_nan=False) + "\n")
    frozen = {key: packet[key] for key in ("code_commit", "sources")}
    report: dict[str, Any] = {
        "gate": "M3",
        "development": development,
        **frozen,
        "started_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "threads": 1,
        **tools,
        "approval_blockers": blockers,
        "cases": {
            case: {"status": "NOT RUN", "reason": "Earlier required case did not complete"}
            for case in CASES
        },
        "not_in_this_subset": {
            "B10": "Tutorial/convergence reference belongs to T028",
            "B12": "Public external reference selection belongs to T028; mandatory at M4",
            "B13/B14": "External reference selection/permissions or owner replacement at T028",
        },
        "m3_exit_status": "NOT DETERMINED; product regressions and owner review also required",
    }
    failed = False
    for case in CASES:
        print(
            f"M3: running {case} ({'development' if development else 'reviewed acceptance'})",
            flush=True,
        )
        try:
            if snapshot() != frozen:
                raise ValueError("Engineering inputs changed during M3 execution")
            result = run_case(case, output / case, development)
            expected_status = "DEVELOPMENT PASS" if development else "PASS"
            if (development and not result["status"].startswith(expected_status)) or (
                not development and result["status"] != "PASS"
            ):
                raise ValueError("Benchmark did not return the requested passing disposition")
            saved = json.loads((output / case / "result.json").read_text())
            if saved != json.loads(json.dumps(result, allow_nan=False)):
                raise ValueError("Saved benchmark record differs from returned evidence")
            if (
                result["case"] != case
                or result["manifest_sha256"] != packet["records"][case]["manifest_sha256"]
                or result["code_commit"] != frozen["code_commit"]
                or result["ccx_sha256"] != report["ccx_sha256"]
                or snapshot() != frozen
            ):
                raise ValueError("Benchmark source/manifest/tool identity changed")
            report["cases"][case] = {
                "status": "PASS",
                "result": f"{case}/result.json",
                "disposition": result["status"],
            }
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            report["cases"][case] = {
                "status": "FAILED",
                "reason": f"{type(error).__name__}: {error}",
            }
            failed = True
            break
    report["numerical_status"] = "FAILED" if failed else "PASS"
    report["benchmark_acceptance"] = "BLOCKED" if failed or development or blockers else "PASS"
    report["completed_at"] = datetime.now(UTC).isoformat()
    report["artifacts_sha256"] = {
        str(path.relative_to(output)): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local/native/validation/T024/benchmarks"
    )
    parser.add_argument(
        "--review-packet",
        action="store_true",
        help="Print exact review hashes without running jobs",
    )
    args = parser.parse_args()
    try:
        if args.review_packet:
            print(json.dumps(review_packet(), indent=2, allow_nan=False))
            return 0
        report = run_gate(args.output, args.development)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"BLOCKED/FAILED: {error}\n")
    print(
        f"Numerics: {report['numerical_status']}; "
        f"benchmark acceptance: {report['benchmark_acceptance']}; "
        f"see {args.output / 'summary.json'}"
    )
    return 0 if report["numerical_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
