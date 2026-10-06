from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from memory_application.ports import ReadinessProbe
from memory_domain import ComponentStatus
from memory_postgres import PostgresReadinessProbe
from pydantic import BaseModel

from memory_api.config import get_settings


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str] | None = None


def create_app(probe: ReadinessProbe | None = None) -> FastAPI:
    settings = get_settings()
    readiness_probe = probe or PostgresReadinessProbe(
        settings.database_url, settings.migration_revision
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(readiness_probe, "close", None)
        if close is not None:
            await close()

    app = FastAPI(title="Memory API", version="0.1.0", lifespan=lifespan)

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
