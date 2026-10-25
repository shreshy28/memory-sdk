import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from memory_application.ports import EmbeddingProvider, ModelProvider, ReadinessProbe
from memory_application.workflows import FormationWorkflow
from memory_domain import ComponentStatus, HealthReport
from memory_postgres import (
    PostgresBackgroundExecutor,
    PostgresFormationRepository,
    PostgresReadinessProbe,
)
from memory_providers import (
    DeterministicEmbeddingProvider,
    DeterministicModelProvider,
    OpenAICompatibleProvider,
)
from pydantic import BaseModel

from memory_worker.config import get_settings
from memory_worker.formation import FormationJobHandler
from memory_worker.leasing import LeaseWorker


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
    executor = PostgresBackgroundExecutor(settings.database_url)
    formation_repository = PostgresFormationRepository(settings.database_url)
    model: ModelProvider
    embeddings: EmbeddingProvider
    if settings.provider == "fake":
        model = DeterministicModelProvider()
        embeddings = DeterministicEmbeddingProvider()
    else:
        provider = OpenAICompatibleProvider(
            base_url=settings.provider_base_url,
            model=settings.provider_model,
            embedding_model=settings.embedding_model,
            api_key=settings.provider_api_key,
        )
        model = provider
        embeddings = provider
    worker = LeaseWorker(
        executor,
        settings.worker_id,
        FormationJobHandler(FormationWorkflow(formation_repository, model, embeddings)),
    )
    run_jobs = probe is None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(worker.run()) if run_jobs else None
        yield
        if task is not None:
            worker.stop()
            await task
        await executor.close()
        await formation_repository.close()
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
