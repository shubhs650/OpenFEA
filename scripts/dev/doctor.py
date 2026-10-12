"""Check the bootstrap and real isolated native capabilities."""

import argparse
import importlib.metadata
import platform
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.config import Settings
from worker.runtime import ROOT, Component, verified_tool
from worker.runtime import probe as native_probe


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
    verified_tool("ccx")
    print("PASS: pinned CPU CCX and runtime library hashes verified")
    components: tuple[Component, ...] = ("cad", "mesh", "post")
    for component in components:
        with tempfile.TemporaryDirectory(dir=settings.data_root) as directory:
            result = native_probe(component, Path(directory))
            assert result["component"] == component
            print(f"PASS: isolated {component} native geometry/I/O capability")
    if args.require_native:
        subprocess.run([sys.executable, "-m", "pytest", "tests/native", "-q"], cwd=ROOT, check=True)
    print("PASS: local bootstrap and native toolchain prerequisites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
