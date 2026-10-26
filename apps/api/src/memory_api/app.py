# ruff: noqa: E501
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from memory_application import EpisodeService, MemoryService
from memory_application.ports import (
    EpisodeRepository,
    IdentityRepository,
    MemoryRepository,
    ReadinessProbe,
)
from memory_domain import (
    AuthorizationError,
    ComponentStatus,
    ConcurrentCorrectionError,
    EpisodeNotFoundError,
    MemoryNotFoundError,
)
from memory_postgres import (
    PostgresEligibilityRepository,
    PostgresLexicalSearch,
    PostgresMemoryRepository,
    PostgresReadinessProbe,
    PostgresVectorSearch,
)
from memory_providers import DeterministicEmbeddingProvider
from memory_retrieval import RetrievalService
from pydantic import BaseModel

from memory_api.config import get_settings
from memory_api.routes import create_router
from memory_api.schemas import ErrorDetail, ErrorEnvelope


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] | None = None


def create_app(
    probe: ReadinessProbe | None = None,
    repository: MemoryRepository | None = None,
    identity_repository: IdentityRepository | None = None,
    retrieval_service: RetrievalService | None = None,
) -> FastAPI:
    settings = get_settings()
    readiness_probe = probe or PostgresReadinessProbe(
        settings.database_url, settings.migration_revision
    )
    postgres_repository = (
        PostgresMemoryRepository(settings.database_url) if repository is None else None
    )
    memory_repository = repository or postgres_repository
    if memory_repository is None:
        raise RuntimeError("memory repository is required")
    identities = identity_repository or postgres_repository
    if identities is None:
        raise RuntimeError("identity repository is required")
    service = MemoryService(memory_repository)
    episode_service = (
        EpisodeService(cast(EpisodeRepository, memory_repository))
        if hasattr(memory_repository, "append_episode")
        else None
    )
    retrieval = retrieval_service
    if retrieval is None and postgres_repository is not None:
        engine = postgres_repository.engine
        retrieval = RetrievalService(
            PostgresLexicalSearch(engine),
            PostgresVectorSearch(engine),
            PostgresEligibilityRepository(engine),
            DeterministicEmbeddingProvider(),
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(readiness_probe, "close", None)
        if close is not None:
            await close()
        if postgres_repository is not None:
            await postgres_repository.close()

    app = FastAPI(title="Memory API", version="0.1.0", lifespan=lifespan)
    app.include_router(create_router(service, identities.authenticate, episode_service, retrieval))

    def error(status_code: int, code: str, message: str, request: Request) -> JSONResponse:
        correlation_id = request.headers.get("X-Correlation-ID", "unavailable")
        envelope = ErrorEnvelope(
            error=ErrorDetail(code=code, message=message, correlation_id=correlation_id)
        )
        return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))

    @app.exception_handler(AuthorizationError)
    async def authorization_error(request: Request, exc: AuthorizationError) -> JSONResponse:
        return error(401, "unauthorized", str(exc), request)

    @app.exception_handler(MemoryNotFoundError)
    async def not_found_error(request: Request, exc: MemoryNotFoundError) -> JSONResponse:
        return error(404, "not_found", str(exc), request)

    @app.exception_handler(EpisodeNotFoundError)
    async def episode_not_found_error(request: Request, exc: EpisodeNotFoundError) -> JSONResponse:
        return error(404, "not_found", str(exc), request)

    @app.exception_handler(ConcurrentCorrectionError)
    async def conflict_error(request: Request, exc: ConcurrentCorrectionError) -> JSONResponse:
        return error(409, "version_conflict", str(exc), request)

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        return error(400, "invalid_request", str(exc), request)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status="alive")

    @app.get(
        "/health/ready",
        response_model=HealthResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
        tags=["health"],
    )
    async def readiness(response: Response) -> HealthResponse:
        report = await readiness_probe.check()
        if report.status is ComponentStatus.NOT_READY:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status=report.status.value,
            checks={name: value.value for name, value in report.checks.items()},
        )

    return app
