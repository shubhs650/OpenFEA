"""Inject validator-boundary faults inside the real isolated parser, tests only."""

from pathlib import Path
from typing import Any

import pytest

from app.jobs import stages
from worker.local_process import NativeControl, supervise


def corrupt_parser(monkeypatch: pytest.MonkeyPatch, transform: str) -> None:
    def observed(
        command: list[str], output: Path, control: NativeControl, log_name: str
    ) -> dict[str, Any]:
        # Keep the product mounts, netdeny, seccomp, limits and actual native
        # outputs. Only the test's trusted launch code inserts the boundary fault.
        prefix = command[-1].split(";runpy.run_module", 1)[0]
        code = "\n".join("    " + line for line in transform.splitlines())
        command[-1] = (
            prefix + "\nimport app.jobs.postprocess as parser\noriginal=parser.validate_outputs\n"
            "def altered(*args, **kwargs):\n    result,summary=original(*args, **kwargs)\n"
            + code
            + "\n    return result,summary\nparser.validate_outputs=altered\nparser.main()"
        )
        return supervise(command, output, control, log_name)

    monkeypatch.setattr(stages, "supervise", observed)
