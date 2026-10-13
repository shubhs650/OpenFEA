from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import Settings


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["openfea-api"] = "openfea-api"
    stage: Literal["bootstrap"] = "bootstrap"


def create_app() -> FastAPI:
    Settings.from_environment()
    app = FastAPI(
        title="OpenFEA local development API",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
    )

    @app.get("/api/v1/health", response_model=Health)
    def health() -> Health:
        return Health()

    return app
