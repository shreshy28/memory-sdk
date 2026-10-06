from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from memory_application.ports import ReadinessProbe
from memory_domain import ComponentStatus, HealthReport
from memory_postgres import PostgresReadinessProbe
from pydantic import BaseModel

from memory_worker.config import get_settings


class WorkerReadinessProbe:
    def __init__(self, database_probe: ReadinessProbe) -> None:
        self._database_probe = database_probe

    async def check(self) -> HealthReport:
        report = await self._database_probe.check()
        checks = dict(report.checks)
        checks["lease"] = checks.get("database", ComponentStatus.NOT_READY)
        status_value = (
            ComponentStatus.READY
            if all(value is ComponentStatus.READY for value in checks.values())
            else ComponentStatus.NOT_READY
        )
        return HealthReport(status=status_value, checks=checks)


class HealthResponse(BaseModel):
    status: str
    worker_id: str
    checks: dict[str, str] | None = None


def create_app(probe: ReadinessProbe | None = None) -> FastAPI:
    settings = get_settings()
    database_probe = probe or PostgresReadinessProbe(
        settings.database_url, settings.migration_revision
    )
    readiness_probe = WorkerReadinessProbe(database_probe)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(database_probe, "close", None)
        if close is not None:
            await close()

    app = FastAPI(title="Memory Worker", version="0.1.0", lifespan=lifespan)

    @app.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse(status="alive", worker_id=settings.worker_id)

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
            worker_id=settings.worker_id,
            checks={name: value.value for name, value in report.checks.items()},
        )

    return app
