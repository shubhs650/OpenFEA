"""Owner review must bind exact criteria before any acceptance job starts."""

import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from worker.approval import criteria_sha256, require_benchmark_approval
from worker.benchmark import run_case
from worker.runtime import ROOT


def approved_manifest() -> dict[str, Any]:
    manifest = json.loads((ROOT / "tests/benchmarks/B01.json").read_text())
    manifest["reviewer_signoff"] = {
        "disposition": "APPROVED",
        "reviewer": "Example owner",
        "reviewed_on": "2026-10-13",
        "criteria_sha256": criteria_sha256(manifest),
    }
    return cast(dict[str, Any], manifest)


def test_bound_owner_record_can_authorize_and_diagnostics_stay_development() -> None:
    manifest = approved_manifest()
    assert require_benchmark_approval(manifest, development=False)
    assert not require_benchmark_approval(manifest, development=True)


@pytest.mark.parametrize(
    "signoff",
    [
        "",
        " ",
        "REJECTED by engineering owner",
        "PENDING engineering owner",
        {},
        {"disposition": "REJECTED", "reviewer": "Owner", "reviewed_on": "2026-10-13"},
        {"disposition": "APPROVED", "reviewer": "", "reviewed_on": "2026-10-13"},
        {"disposition": "APPROVED", "reviewer": "PENDING owner", "reviewed_on": "2026-10-13"},
        {"disposition": "APPROVED", "reviewer": "Owner", "reviewed_on": "2026-02-30"},
        {
            "disposition": "APPROVED",
            "reviewer": "Owner",
            "reviewed_on": "2026-10-13",
            "criteria_sha256": "0" * 64,
        },
    ],
)
def test_missing_rejected_and_malformed_review_never_authorize(signoff: Any) -> None:
    manifest = approved_manifest()
    manifest["reviewer_signoff"] = signoff
    with pytest.raises(ValueError, match="Engineering-owner review"):
        require_benchmark_approval(manifest, development=False)


def test_changed_criteria_invalidate_owner_record() -> None:
    manifest = approved_manifest()
    original = copy.deepcopy(manifest)
    manifest["tolerances"]["relative"] *= 2
    assert manifest["reviewer_signoff"] == original["reviewer_signoff"]
    with pytest.raises(ValueError, match="stale"):
        require_benchmark_approval(manifest, development=False)


@pytest.mark.parametrize("case", ["B01", "B02", "B07", "B09"])
def test_empty_signoff_cannot_create_any_benchmark_job(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_name = "B07-mortar.json" if case == "B07" else f"{case}.json"
    read_text = Path.read_text

    def empty_signoff(path: Path, *args: Any, **kwargs: Any) -> str:
        text = read_text(path, *args, **kwargs)
        if path.name == manifest_name and path.parent.name == "benchmarks":
            manifest = json.loads(text)
            manifest["reviewer_signoff"] = ""
            return json.dumps(manifest)
        return text

    monkeypatch.setattr(Path, "read_text", empty_signoff)
    output = tmp_path / case
    with pytest.raises(ValueError, match="Engineering-owner review"):
        run_case(case, output, development=False)
    assert not output.exists()
