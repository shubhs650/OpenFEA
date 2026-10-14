"""Launch verified native tools with a minimal environment and no network sockets."""

import hashlib
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[3]
NATIVE = ROOT / ".local/native"
Component = Literal["cad", "mesh", "post"]
Fixture = Literal["box", "bracket", "two", "bonded", "gap-probe", "long-box", "beam", "rotated-box"]


class NativeOperationError(RuntimeError):
    """Retain the actual failed process transcript for diagnostic evidence."""

    def __init__(self, result: subprocess.CompletedProcess[str]) -> None:
        self.result = result
        super().__init__(
            f"Native operation failed ({result.returncode}): "
            f"{result.stdout[-2000:]}{result.stderr[-1000:]}"
        )


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verified_tool(name: Literal["ccx", "netdeny"]) -> Path:
    path = NATIVE / "bin" / name
    if name == "ccx" and os.environ.get("FEA_CCX_PATH"):
        path = Path(os.environ["FEA_CCX_PATH"])
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"Missing executable {name}; run make setup-native")
    manifest = NATIVE / "build.json"
    if not manifest.is_file():
        raise RuntimeError("Missing native build manifest; run make setup-native")
    expected = json.loads(manifest.read_text())["outputs_sha256"][f"bin/{name}"]
    if sha256(path) != expected:
        raise RuntimeError(
            f"Unverified {name} binary: hash does not match the local build manifest"
        )
    if path.resolve() != (NATIVE / "bin" / name).resolve():
        raise RuntimeError(
            "Native executable must use the pinned workspace location and runtime libs"
        )
    for relative, digest in json.loads(manifest.read_text())["outputs_sha256"].items():
        if relative.startswith("lib/") and sha256(NATIVE / relative) != digest:
            raise RuntimeError(f"Unverified native runtime library: {relative}")
    return path.resolve()


def native_environment(directory: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(directory),
        "TMPDIR": str(directory),
        "LC_ALL": "C",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "MPLCONFIGDIR": str(directory / ".matplotlib"),
        "PYTHONNOUSERSITE": "1",
    }


def execute(
    command: list[str], directory: Path, timeout: float = 90
) -> subprocess.CompletedProcess[str]:
    launcher = verified_tool("netdeny")
    process = subprocess.Popen(
        [str(launcher), *command],
        cwd=directory,
        env=native_environment(directory),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError("Native operation exceeded its wall-clock limit") from None
    finally:
        # Native tools may spawn children; retire the whole owned group on completion.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    assert process.returncode is not None
    if process.returncode:
        raise NativeOperationError(
            subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        )
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def probe(component: Component, directory: Path, network_only: bool = False) -> dict[str, object]:
    python = NATIVE / "venvs" / component / "bin/python"
    if not python.is_file():
        raise RuntimeError(f"Missing {component} environment; run make setup-native")
    script = (
        ROOT
        / "services/worker/worker/probes"
        / ("network.py" if network_only else f"{component}.py")
    )
    result = execute([str(python), "-I", str(script)], directory)
    # Native libraries may write diagnostics/footer escapes after the payload.
    payloads = [
        line.removeprefix("OPENFEA_PROBE=")
        for line in result.stdout.splitlines()
        if line.startswith("OPENFEA_PROBE=")
    ]
    if len(payloads) != 1:
        raise RuntimeError("Native probe returned no unambiguous structured result")
    value: dict[str, object] = json.loads(payloads[0])
    return value


def solve_reference(directory: Path) -> subprocess.CompletedProcess[str]:
    binary = verified_tool("ccx")
    return execute([str(binary), "-i", "smoke"], directory)


def synthetic_geometry(directory: Path, fixture: Fixture) -> None:
    if fixture not in (
        "box",
        "bracket",
        "two",
        "bonded",
        "gap-probe",
        "long-box",
        "beam",
        "rotated-box",
    ):
        raise ValueError("Unsupported synthetic fixture")
    execute(
        [
            str(NATIVE / "venvs/cad/bin/python"),
            "-I",
            str(ROOT / "services/worker/worker/geometry_native/build.py"),
            fixture,
        ],
        directory,
    )


def quadratic_mesh(
    directory: Path, size: float, tag_offset: int = 0, body_sizes: tuple[float, ...] | None = None
) -> None:
    if not 0.1 <= size <= 1 or not 0 <= tag_offset <= 10000:
        raise ValueError("Synthetic mesh settings outside validated limits")
    if body_sizes is not None and any(not 0.1 <= v <= 1 for v in body_sizes):
        raise ValueError("Synthetic body mesh size outside validated limits")
    execute(
        [
            str(NATIVE / "venvs/mesh/bin/python"),
            "-I",
            str(ROOT / "services/worker/worker/meshing_native/build.py"),
            str(size),
            str(tag_offset),
            json.dumps(body_sizes),
        ],
        directory,
    )


def solve_generated(directory: Path) -> subprocess.CompletedProcess[str]:
    """Fixed basename for internally generated decks; not an uploaded-input API."""
    return execute([str(verified_tool("ccx")), "-i", "analysis"], directory)
