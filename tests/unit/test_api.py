from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(autouse=True)
def local_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEA_ENV", "test")
    monkeypatch.setenv("FEA_AUTH_MODE", "local")
    monkeypatch.setenv("FEA_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("FEA_DATA_ROOT", str(tmp_path))


def test_health_contract() -> None:
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "openfea-api", "stage": "bootstrap"}
        schema = client.get("/api/v1/openapi.json").json()
        assert "/api/v1/projects" in schema["paths"]
        assert "/api/v1/health" in schema["paths"]


def test_solver_submission_requires_owned_revision_and_request_key() -> None:
    with TestClient(
        create_app(), base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
    ) as client:
        assert client.post("/api/v1/analyses/example/runs").status_code == 428
        response = client.post(
            "/api/v1/analyses/11111111-1111-1111-1111-111111111111/runs",
            json={"mesh_job_id": "22222222-2222-2222-2222-222222222222"},
            headers={"If-Match": '"1"', "Idempotency-Key": "33333333-3333-3333-3333-333333333333"},
        )
        assert response.status_code == 401


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
