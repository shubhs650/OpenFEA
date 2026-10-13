"""Own and supervise just the local health API and web processes."""

import argparse
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import FrameType

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_HEALTH = {"status": "ok", "service": "openfea-api", "stage": "bootstrap"}


def port(name: str, default: int) -> int:
    result = int(os.environ.get(name, default))
    if not 1024 <= result <= 65535:
        raise ValueError(f"{name} must be between 1024 and 65535")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="check HTTP behavior, then stop")
    args = parser.parse_args()
    settings = Settings.from_environment()
    api_port, web_port = port("FEA_API_PORT", 8000), port("FEA_WEB_PORT", 5173)
    if api_port == web_port:
        raise ValueError("API and web ports must differ")
    # Refuse occupied ports before spawning; never terminate someone else's service.
    for selected_port in (api_port, web_port):
        with socket.socket() as probe:
            # Match the servers' bind policy: TIME_WAIT is safe, active listeners are not.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((settings.bind_host, selected_port))
    settings.data_root.mkdir(parents=True, exist_ok=True)
    logs = ROOT / ".local" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stop = False

    def stop_requested(signum: int, frame: FrameType | None) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, stop_requested)
    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGHUP, stop_requested)
    print(f"SUPERVISOR pid={os.getpid()}", flush=True)
    commands = [
        (
            "api",
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--no-proxy-headers",
                "--host",
                settings.bind_host,
                "--port",
                str(api_port),
                "--reload",
                "--reload-dir",
                str(ROOT / "services/api/app"),
            ],
        ),
        (
            "web",
            [
                "npm",
                "run",
                "dev",
                "--workspace",
                "@openfea/web",
                "--",
                "--host",
                settings.bind_host,
                "--port",
                str(web_port),
                "--strictPort",
            ],
        ),
    ]
    processes: list[subprocess.Popen[bytes]] = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for name, command in commands:
            with (logs / f"{name}.log").open("wb") as output:
                processes.append(
                    subprocess.Popen(
                        command,
                        cwd=ROOT,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                )
                print(f"STARTED {name} pid={processes[-1].pid}", flush=True)
        deadline = time.monotonic() + 45
        ready = False
        while not stop and time.monotonic() < deadline:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("Development process exited before readiness")
            try:
                for selected_port in (api_port, web_port):
                    with opener.open(
                        f"http://127.0.0.1:{selected_port}/api/v1/health", timeout=1
                    ) as r:
                        if r.status != 200 or json.load(r) != EXPECTED_HEALTH:
                            raise RuntimeError("Unexpected health response")
                with opener.open(f"http://127.0.0.1:{web_port}/", timeout=1) as r:
                    if r.status != 200 or '<div id="root"></div>' not in r.read().decode():
                        raise RuntimeError("Web entry point is unavailable")
                ready = True
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(0.2)
        if stop:
            return 0
        if not ready:
            raise RuntimeError("Development services did not become ready within 45 seconds")
        print("READY: API health, web entry point and Vite API proxy verified", flush=True)
        print(f"Web port {web_port}; API port {api_port}; logs in .local/logs", flush=True)
        if args.smoke:
            return 0
        while not stop:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("Development process exited; inspect .local/logs")
            time.sleep(0.2)
        return 0
    except Exception:
        for name, _ in commands:
            log = logs / f"{name}.log"
            if log.exists():
                print(f"{name} log tail:\n" + "\n".join(log.read_text()[-6000:].splitlines()[-20:]))
        raise
    finally:
        # Each child has its own process group, including hot-reload descendants.
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            # Reload resource trackers can ignore TERM even after the parent exits.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
