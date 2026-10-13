import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.auth.body_limit import MetadataBodyLimit
from app.auth.local import check_boundary
from app.config import Settings
from app.domain.deck_service import DeckService
from app.domain.errors import DomainError
from app.domain.import_service import ImportService
from app.domain.models import ErrorResponse
from app.jobs.runner import LocalWorker
from app.jobs.service import JobService
from app.persistence.database import Database
from app.persistence.imports import ImportRepository
from app.persistence.jobs import JobRepository
from app.persistence.repository import Repository
from app.routes import imports as _imports  # noqa: F401
from app.routes import jobs as _jobs  # noqa: F401
from app.routes import loads as _loads  # noqa: F401
from app.routes import materials as _materials  # noqa: F401
from app.routes.projects import router
from app.storage.geometry import GeometryStorage


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["openfea-api"] = "openfea-api"
    stage: Literal["bootstrap"] = "bootstrap"


def create_app() -> FastAPI:
    settings = Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(settings.data_root / "metadata.sqlite3")
        worker: LocalWorker | None = None
        try:
            database.migrate()
            app.state.repository = Repository(database)
            app.state.owner = app.state.repository.local_owner()
            imports = ImportRepository(app.state.repository)
            imports.interrupt_incomplete()
            app.state.import_service = ImportService(imports, GeometryStorage(settings.data_root))
            app.state.deck_service = DeckService(app.state.repository, app.state.import_service)
            app.state.session_token = secrets.token_urlsafe(32)
            app.state.csrf_token = secrets.token_urlsafe(32)
            app.state.job_service = JobService(
                JobRepository(app.state.repository), app.state.deck_service
            )
            worker = LocalWorker(app.state.job_service)
            app.state.local_worker = worker
            worker.start()
            yield
        finally:
            if worker is not None:
                worker.close()
            database.close()

    app = FastAPI(
        title="OpenFEA local development API",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(MetadataBodyLimit)

    def error(
        request: Request,
        status: int,
        code: str,
        message: str,
        field_errors: dict[str, str] | None = None,
        retryable: bool = False,
    ) -> JSONResponse:
        payload = ErrorResponse(
            code=code,
            message=message,
            field_errors=field_errors or {},
            retryable=retryable,
            request_id=request.state.request_id,
        )
        return JSONResponse(status_code=status, content=payload.model_dump(mode="json"))

    @app.middleware("http")
    async def local_boundary(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = str(uuid4())
        try:
            check_boundary(request)
            response = await call_next(request)
        except DomainError as exception:
            response = error(request, exception.status, exception.code, exception.message)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exception: DomainError) -> JSONResponse:
        return error(
            request,
            exception.status,
            exception.code,
            exception.message,
            retryable=exception.retryable,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exception: RequestValidationError) -> JSONResponse:
        fields = {
            ".".join(str(part) for part in item["loc"]): "Invalid value"
            for item in exception.errors()
        }
        return error(request, 422, "invalid_request", "Check the request fields", fields)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exception: HTTPException) -> JSONResponse:
        message = (
            "The requested object is unavailable"
            if exception.status_code == 404
            else "Request rejected"
        )
        return error(
            request,
            exception.status_code,
            "not_found" if exception.status_code == 404 else "request_rejected",
            message,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exception: SQLAlchemyError) -> JSONResponse:
        return error(
            request, 503, "database_unavailable", "Metadata storage is unavailable", retryable=True
        )

    @app.exception_handler(OSError)
    async def storage_error(request: Request, exception: OSError) -> JSONResponse:
        return error(request, 503, "storage_unavailable", "Geometry storage is unavailable")

    app.include_router(router)

    @app.get("/api/v1/health", response_model=Health)
    def health() -> Health:
        return Health()

    return app
