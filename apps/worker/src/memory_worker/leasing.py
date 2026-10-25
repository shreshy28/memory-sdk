import asyncio
from collections.abc import Awaitable, Callable

from memory_application.ports import BackgroundExecutor, ProviderError, WorkItem


class LeaseWorker:
    def __init__(
        self,
        executor: BackgroundExecutor,
        owner: str,
        handler: Callable[[WorkItem], Awaitable[None]],
        *,
        poll_seconds: float = 0.5,
        max_attempts: int = 5,
    ) -> None:
        self.executor = executor
        self.owner = owner
        self.handler = handler
        self.poll_seconds = poll_seconds
        self.max_attempts = max_attempts
        self._stopping = asyncio.Event()

    async def run(self) -> None:
        while not self._stopping.is_set():
            items = await self.executor.lease(owner=self.owner, limit=10)
            if not items:
                try:
                    await asyncio.wait_for(self._stopping.wait(), self.poll_seconds)
                except TimeoutError:
                    pass
                continue
            for item in items:
                await self.process(item)

    async def process(self, item: WorkItem) -> None:
        try:
            await self.handler(item)
        except ProviderError as error:
            if error.retryable and item.attempts < self.max_attempts:
                await self.executor.retry(
                    item.id, owner=self.owner, delay_seconds=min(60, 2**item.attempts)
                )
            else:
                fail = getattr(self.executor, "fail", None)
                if fail is not None:
                    await fail(item.id, owner=self.owner, code=error.code)
                else:
                    await self.executor.cancel(item.id)
        except Exception:
            if item.attempts < self.max_attempts:
                await self.executor.retry(
                    item.id, owner=self.owner, delay_seconds=min(60, 2**item.attempts)
                )
            else:
                await self.executor.cancel(item.id)
        else:
            await self.executor.complete(item.id, owner=self.owner)

    def stop(self) -> None:
        self._stopping.set()
