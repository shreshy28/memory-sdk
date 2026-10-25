from datetime import UTC, datetime
from uuid import uuid4

import pytest
from memory_application.ports import ProviderError, WorkItem
from memory_worker.leasing import LeaseWorker


class Executor:
    def __init__(self) -> None:
        self.retried = False
        self.completed = False

    async def submit(self, item: WorkItem) -> None:
        pass

    async def lease(self, *, owner: str, limit: int) -> list[WorkItem]:
        return []

    async def complete(self, item_id: object, *, owner: str) -> None:
        self.completed = True

    async def heartbeat(self, item_id: object, *, owner: str) -> bool:
        return True

    async def retry(self, item_id: object, *, owner: str, delay_seconds: float) -> None:
        self.retried = True

    async def cancel(self, item_id: object) -> None:
        pass


@pytest.mark.asyncio
async def test_worker_retries_recoverable_provider_failure() -> None:
    executor = Executor()

    async def fail_once(item: WorkItem) -> None:
        raise ProviderError("timeout", retryable=True)

    worker = LeaseWorker(executor, "worker", fail_once)
    await worker.process(WorkItem(uuid4(), "formation", {}, datetime.now(UTC), uuid4(), 1))
    assert executor.retried
    assert not executor.completed


@pytest.mark.asyncio
async def test_recovered_job_completes() -> None:
    executor = Executor()

    async def succeed(item: WorkItem) -> None:
        return None

    worker = LeaseWorker(executor, "worker", succeed)
    await worker.process(WorkItem(uuid4(), "formation", {}, datetime.now(UTC), uuid4(), 2))
    assert executor.completed
