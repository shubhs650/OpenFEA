"""Review-only failure injection: all statuses come from actual bounded native jobs."""

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path("services/worker").resolve()))
from worker.runtime import ROOT

spec = importlib.util.spec_from_file_location("feasibility_review", "scripts/native/feasibility.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
actual = module.measured_native
calls = []


def controlled_native(command, directory, name, **limits):
    # Use the known tiny h=.6 mesh to test sequencing, not to measure nominal capacity.
    if name == "mesh":
        command = list(command)
        command[3] = "0.6"
    if name == "prepare":
        # Deterministic real failing child, rather than manufactured completion/status data.
        command = [str(ROOT / ".venv/bin/python"), "-I", "-c", "raise SystemExit(7)"]
    report = actual(command, directory, name, **limits)
    calls.append(
        {
            "directory": directory.name,
            "stage": name,
            "status": report["status"],
            "returncode": report["returncode"],
            "actual_command": report["command"],
        }
    )
    return report


module.measured_native = controlled_native
output = Path(".local/reviews/M0/stop-probe").resolve()
sys.argv = ["feasibility.py", "--meshes", "--output", str(output)]
exit_code = module.main()
report = {
    "scope": (
        "Failure sequencing only; tiny real Gmsh meshes and actual exit-7 preparation child. "
        "Not a capacity/physics benchmark; manifests unchanged."
    ),
    "runner_exit_code": exit_code,
    "calls": calls,
    "finding_reproduced": len([c for c in calls if c["stage"] == "mesh"]) > 1,
}
Path(".local/reviews/M0/stop-probe-result.json").write_text(json.dumps(report, indent=2) + "\n")
assert report["finding_reproduced"] and exit_code == 2
print("CONFIRMED: real preparation failure did not stop mesh graduation")
