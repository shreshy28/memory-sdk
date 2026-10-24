from collections.abc import Sequence
from uuid import UUID

from memory_domain import Memory, MemoryVersion, Operation, RequestContext

from memory_application.ports.repositories import Correction, MemoryRepository, NewMemory


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def add(
        self, context: RequestContext, command: NewMemory, idempotency_key: str
    ) -> tuple[Memory, Operation]:
        self._require_key(idempotency_key)
        return await self.repository.add(context, command, idempotency_key)

    async def list(
        self,
        context: RequestContext,
        *,
        subject_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[Sequence[Memory], str | None]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return await self.repository.list_current(
            context, subject_id=subject_id, cursor=cursor, limit=limit
        )

    async def get(self, context: RequestContext, memory_id: UUID) -> Memory:
        return await self.repository.get(context, memory_id)

    async def history(self, context: RequestContext, memory_id: UUID) -> Sequence[MemoryVersion]:
        return await self.repository.history(context, memory_id)

    async def correct(
        self,
        context: RequestContext,
        memory_id: UUID,
        correction: Correction,
        idempotency_key: str,
    ) -> tuple[Memory, Operation]:
        self._require_key(idempotency_key)
        return await self.repository.correct(context, memory_id, correction, idempotency_key)

    async def suppress(
        self, context: RequestContext, memory_id: UUID, idempotency_key: str
    ) -> Operation:
        self._require_key(idempotency_key)
        return await self.repository.suppress(context, memory_id, idempotency_key)

    async def operation(self, context: RequestContext, operation_id: UUID) -> Operation:
        return await self.repository.get_operation(context, operation_id)

    @staticmethod
    def _require_key(value: str) -> None:
        if not value or len(value) > 255:
            raise ValueError("a valid Idempotency-Key is required")
