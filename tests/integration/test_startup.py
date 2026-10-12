"""Real process lifecycle checks on the supported Linux/WSL2 development host."""

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RuntimeConfiguration:
    api_port: int
    web_port: int
    environment: dict[str, str] = field(repr=False)


@dataclass(frozen=True)
class RuntimeServer:
    process: subprocess.Popen[str]
    configuration: RuntimeConfiguration
    api_pid: int


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def configuration(tmp_path: Path) -> RuntimeConfiguration:
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    environment = os.environ | {
        "FEA_ENV": "test",
        "FEA_AUTH_MODE": "local",
        "FEA_BIND_HOST": "127.0.0.1",
        "FEA_DATA_ROOT": str(tmp_path),
        "FEA_API_PORT": str(api_port),
        "FEA_WEB_PORT": str(web_port),
    }
    return RuntimeConfiguration(api_port, web_port, environment)


@pytest.fixture
def running_server(
    configuration: RuntimeConfiguration,
) -> Iterator[RuntimeServer]:
    web_port = configuration.web_port
    process = subprocess.Popen(
        ["bash", "scripts/codex/start.sh"],
        cwd=ROOT,
        env=configuration.environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"startup exited early: {process.communicate()[0]}")
            try:
                with opener.open(f"http://127.0.0.1:{web_port}/api/v1/health", timeout=1) as r:
                    if json.load(r) == {
                        "status": "ok",
                        "service": "openfea-api",
                        "stage": "bootstrap",
                    }:
                        break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(0.1)
        else:
            pytest.fail("API proxy readiness timed out")
        assert process.stdout is not None
        started = process.stdout.readline().strip()
        assert started.startswith("SUPERVISOR pid="), started
        started = process.stdout.readline().strip()
        assert started.startswith("STARTED api pid="), started
        api_pid = int(started.split("=", 1)[1])
        yield RuntimeServer(process, configuration, api_pid)
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=15)


def assert_ports_released(*ports: int) -> None:
    for selected_port in ports:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", selected_port))


def test_signal_stops_services_and_allows_restart(
    running_server: RuntimeServer,
    configuration: RuntimeConfiguration,
) -> None:
    process = running_server.process
    api_port, web_port = configuration.api_port, configuration.web_port
    process.terminate()
    output, _ = process.communicate(timeout=15)
    assert process.returncode == 0, output
    assert_ports_released(api_port, web_port)
    result = subprocess.run(
        ["bash", "scripts/codex/start.sh", "--smoke"],
        cwd=ROOT,
        env=configuration.environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "READY: API health" in result.stdout
    assert_ports_released(api_port, web_port)


def test_child_failure_fails_supervisor_and_stops_sibling(
    running_server: RuntimeServer,
) -> None:
    process = running_server.process
    api_port = running_server.configuration.api_port
    web_port = running_server.configuration.web_port
    os.kill(running_server.api_pid, signal.SIGTERM)
    output, _ = process.communicate(timeout=15)
    assert process.returncode != 0, output
    assert "Development process exited" in output
    assert_ports_released(api_port, web_port)


def test_occupied_port_is_not_reused_or_terminated(
    configuration: RuntimeConfiguration,
) -> None:
    api_port, web_port = configuration.api_port, configuration.web_port
    with socket.socket() as existing:
        existing.bind(("127.0.0.1", api_port))
        existing.listen()
        result = subprocess.run(
            ["bash", "scripts/codex/start.sh", "--smoke"],
            cwd=ROOT,
            env=configuration.environment,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0
        assert "Address already in use" in result.stderr
        assert existing.getsockname()[1] == api_port
        assert_ports_released(web_port)


def test_make_terminal_interrupt_stops_services(configuration: RuntimeConfiguration) -> None:
    process = subprocess.Popen(
        ["make", "dev"],
        cwd=ROOT,
        env=configuration.environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"make dev exited early: {process.communicate()[0]}")
            try:
                with opener.open(
                    f"http://127.0.0.1:{configuration.web_port}/api/v1/health",
                    timeout=1,
                ) as response:
                    assert json.load(response)["status"] == "ok"
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(0.1)
        else:
            pytest.fail("make dev readiness timed out")
        # Terminal interrupts reach the whole foreground process group, including Make.
        os.killpg(process.pid, signal.SIGINT)
        process.communicate(timeout=15)
        assert process.returncode is not None
        assert_ports_released(configuration.api_port, configuration.web_port)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=15)
