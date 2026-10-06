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


class BackgroundExecutor(Protocol):
    async def submit(self, item: WorkItem) -> None: ...

    async def lease(self, *, owner: str, limit: int) -> list[WorkItem]: ...

    async def complete(self, item_id: UUID, *, owner: str) -> None: ...

    async def cancel(self, item_id: UUID) -> None: ...
