from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def local_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEA_ENV", "test")
    monkeypatch.setenv("FEA_AUTH_MODE", "local")
    monkeypatch.setenv("FEA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("FEA_DATA_ROOT", str(tmp_path))


def test_health_contract() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "openfea-api", "stage": "bootstrap"}
        schema = client.get("/api/v1/openapi.json").json()
        assert set(schema["paths"]) == {"/api/v1/health"}


def test_no_solver_routes() -> None:
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/analyses/example/runs").status_code == 404


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("FEA_ENV", "beta"),
        ("FEA_ENV", "production"),
        ("FEA_AUTH_MODE", "google_oidc"),
        ("FEA_BIND_HOST", "0.0.0.0"),
        ("FEA_BIND_HOST", "example.com"),
        ("FEA_DATA_ROOT", "relative-data"),
        ("FEA_DATA_ROOT", str(Path(__file__).resolve().parents[2] / "private-data")),
    ],
)
def test_unsafe_startup_rejected(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        create_app()
