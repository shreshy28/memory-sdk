from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class WorkItem:
    id: UUID
    kind: str
    payload: dict[str, Any]
    available_at: datetime
    operation_id: UUID | None = None
    attempts: int = 0
    lease_expires_at: datetime | None = None


class BackgroundExecutor(Protocol):
    async def submit(self, item: WorkItem) -> None: ...

    async def lease(self, *, owner: str, limit: int) -> list[WorkItem]: ...

    async def complete(self, item_id: UUID, *, owner: str) -> None: ...

    async def heartbeat(self, item_id: UUID, *, owner: str) -> bool: ...

    async def retry(self, item_id: UUID, *, owner: str, delay_seconds: float) -> None: ...

    async def cancel(self, item_id: UUID) -> None: ...
