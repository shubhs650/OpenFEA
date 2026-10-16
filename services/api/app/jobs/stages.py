"""Fixed parser command: readonly frozen inputs/raw outputs, bounded private scratch."""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from app.domain.deck_service import canonical
from app.domain.errors import DomainError
from app.domain.jobs import JobInput
from app.jobs.postprocess import ValidationFailure
from app.storage.geometry import GeometryStorage
from worker.local_process import NativeControl, NativeStop, supervise
from worker.runtime import ROOT, verified_tool
from worker.step_import import ImportSandboxError


def postprocess(
    directory: Path,
    inputs: JobInput,
    input_hash: str,
    execution: dict[str, Any],
    control: NativeControl,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bwrap = shutil.which("bwrap")
    if bwrap is None:
        raise ImportSandboxError("Bubblewrap is required for result validation")
    output = directory / "validation"
    output.mkdir(mode=0o700)
    (output / "tmp").mkdir()
    request = directory / "parse-request.json"
    request.write_bytes(
        canonical(
            {
                "inputs": inputs.model_dump(mode="json"),
                "input_hash": input_hash,
                "execution": execution,
            }
        )
    )
    command = [bwrap, "--unshare-all", "--new-session", "--die-with-parent", "--cap-drop", "ALL"]
    for path in dict.fromkeys(
        (
            "/usr",
            "/lib",
            "/lib64",
            str(Path(sys.base_prefix).resolve()),
            str(ROOT / ".venv"),
            str(ROOT / "services/api"),
            str(ROOT / "services/worker"),
        )
    ):
        command += ["--ro-bind", path, path]
    if Path("/etc/ld.so.cache").is_file():
        command += ["--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"]
    command += [
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--dir",
        "/work",
        "--bind",
        str(output),
        "/work/out",
        "--symlink",
        "/work/out/tmp",
        "/tmp",
        "--chdir",
        "/work/out",
    ]
    files = {
        "request.json": request,
        "mesh.json": directory / "mesh.json",
        "analysis.inp": directory / "analysis.inp",
    }
    files.update(
        {
            name: directory / "output" / name
            for name in ("solver.log", "analysis.dat", "analysis.frd")
        }
    )
    for name, source in files.items():
        command += ["--ro-bind", str(source), "/work/out/" + name]
    launch = (
        "import sys,runpy;sys.path[:0]="
        + repr([str(ROOT / "services/api"), str(ROOT / "services/worker")])
        + ";runpy.run_module('app.jobs.postprocess',run_name='__main__')"
    )
    command += [
        "--ro-bind",
        str(verified_tool("netdeny")),
        "/limits",
        "/limits",
        str(ROOT / ".venv/bin/python"),
        "-I",
        "-c",
        launch,
    ]
    measured = supervise(command, output, control, "validation.log")
    # A positively observed terminated parser is an infrastructure interruption.
    # Unexplained exits/protocol errors are reviewed failures, never auto-retried.
    if measured["returncode"] in (-15, 143):
        raise NativeStop("parser_interrupted")
    if measured["returncode"] != 0:
        raise DomainError(
            500, "parser_failed", "Result parser failed; raw outputs retained for review"
        )
    outcome = json.loads(GeometryStorage.read_fixed(output / "outcome.json"))
    if "error" in outcome:
        raise ValidationFailure(outcome["error"], outcome.get("summary", {}))
    outcome["summary"]["validation_execution"] = measured
    return outcome["result"], outcome["summary"]
