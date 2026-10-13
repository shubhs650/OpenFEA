"""Review-only invalid metadata probe. Frozen files and physical criteria stay unchanged."""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path("services/worker").resolve()))
from worker.benchmark import run_case
from worker.runtime import ROOT

manifest_path = ROOT / "tests/benchmarks/B01.json"
before = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
original = json.loads


def invalid_metadata(text, *args, **kwargs):
    result = original(text, *args, **kwargs)
    if isinstance(result, dict) and result.get("id") == "B01":
        result["reviewer_signoff"] = ""
    return result


output = ROOT / ".local/reviews/M0/empty-signoff"
with patch.object(json, "loads", side_effect=invalid_metadata):
    result = run_case("B01", output, development=False)
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == before
report = {
    "scope": (
        "Invalid approval-metadata diagnostic only; real B01 native pipeline, "
        "unchanged frozen physical criteria/files; not an approved benchmark."
    ),
    "provided_signoff": "",
    "requested_development": False,
    "observed_status": result["status"],
    "job_directory_created": output.exists(),
    "real_native_runs": len(result["runs"]),
    "manifest_sha256_unchanged": before,
    "finding_reproduced": result["status"] == "PASS",
}
(ROOT / ".local/reviews/M0/signoff-probe-result.json").write_text(
    json.dumps(report, indent=2) + "\n"
)
assert report["finding_reproduced"]
print(json.dumps(report, indent=2))
