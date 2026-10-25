from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from memory_domain import (
    Episode,
    EpisodeKind,
    Memory,
    MemoryKind,
    MemoryVersion,
    Operation,
    RequestContext,
    Sensitivity,
)


@dataclass(frozen=True, slots=True)
class NewMemory:
    subject_id: UUID
    kind: MemoryKind
    text: str
    structured_value: dict[str, Any] | None
    confidence: float
    importance: float
    sensitivity: Sensitivity
    valid_from: datetime | None
    valid_to: datetime | None
    collection_id: UUID | None


@dataclass(frozen=True, slots=True)
class Correction:
    text: str
    structured_value: dict[str, Any] | None
    reason: str
    expected_version: int | None
    confidence: float | None = None
    importance: float | None = None
    sensitivity: Sensitivity | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class NewEpisode:
    subject_id: UUID
    kind: EpisodeKind
    content: str
    occurred_at: datetime
    source: str
    sensitivity: Sensitivity
    agent_id: UUID | None = None
    session_id: UUID | None = None
    role: str | None = None
    source_ref: str | None = None
    consent_basis: str | None = None


class EpisodeRepository(Protocol):
    async def append_episode(
        self, context: RequestContext, command: NewEpisode, idempotency_key: str
    ) -> tuple[Episode, Operation]: ...

    async def get_episode(self, context: RequestContext, episode_id: UUID) -> Episode: ...


class MemoryRepository(Protocol):
    async def add(
        self, context: RequestContext, command: NewMemory, idempotency_key: str
    ) -> tuple[Memory, Operation]: ...

    async def list_current(
        self,
        context: RequestContext,
        *,
        subject_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[Memory], str | None]: ...

    async def get(self, context: RequestContext, memory_id: UUID) -> Memory: ...

    async def history(
        self, context: RequestContext, memory_id: UUID
    ) -> Sequence[MemoryVersion]: ...

    async def correct(
        self,
        context: RequestContext,
        memory_id: UUID,
        correction: Correction,
        idempotency_key: str,
    ) -> tuple[Memory, Operation]: ...

    async def suppress(
        self, context: RequestContext, memory_id: UUID, idempotency_key: str
    ) -> Operation: ...

    async def get_operation(self, context: RequestContext, operation_id: UUID) -> Operation: ...

    async def close(self) -> None: ...


class IdentityRepository(Protocol):
    async def authenticate(self, api_key: str) -> RequestContext: ...
