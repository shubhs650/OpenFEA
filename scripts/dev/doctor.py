"""Check the bootstrap independently of optional, unprovisioned native capabilities."""

import argparse
import importlib.metadata
import os
import platform
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.config import Settings


class ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"openfea-loopback-ok")

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_environment()
    print(f"Platform: {platform.system()} {platform.machine()}; Python {platform.python_version()}")
    for tool in ("node", "npm", "uv"):
        subprocess.run([tool, "--version"], check=True)
    for package in ("fastapi", "pydantic", "uvicorn", "pytest", "ruff", "mypy"):
        print(f"{package}: {importlib.metadata.version(package)}")
    settings.data_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=settings.data_root) as directory:
        probe = Path(directory) / "probe"
        probe.write_text("scratch-ok")
        assert probe.read_text() == "scratch-ok"
    print("PASS: writable non-repository data root")
    server = HTTPServer(("127.0.0.1", 0), ProbeHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{server.server_port}/", timeout=5) as response:
            assert response.status == 200 and response.read() == b"openfea-loopback-ok"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    print("PASS: loopback HTTP round trip")
    missing = []
    for command in ("ccx", "gmsh"):
        configured = os.environ.get("FEA_CCX_PATH") if command == "ccx" else None
        executable = configured or shutil.which(command)
        if executable and Path(executable).is_file() and os.access(executable, os.X_OK):
            print(f"UNVALIDATED: {command} found; native version/hash/solve checks remain T002")
        else:
            missing.append(command)
            print(f"MISSING: {command} (native gate blocked; not required for T001 health)")
    for module in ("cadquery-ocp", "vtk"):
        try:
            print(f"UNVALIDATED: {module} {importlib.metadata.version(module)}")
        except importlib.metadata.PackageNotFoundError:
            missing.append(module)
            print(f"MISSING: {module} (T002)")
    if args.require_native:
        print(
            "BLOCKED: native validation runner is not implemented (T002); presence is insufficient"
        )
        return 2
    print(f"PASS: bootstrap prerequisites; {len(missing)} native capabilities missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
