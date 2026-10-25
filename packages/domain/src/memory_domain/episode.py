from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from memory_domain.memory import Sensitivity


class EpisodeKind(StrEnum):
    CONVERSATION = "conversation"
    EVENT = "event"
    CORRECTION = "correction"


class EpisodeStatus(StrEnum):
    ACCEPTED = "accepted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Episode:
    id: UUID
    tenant_id: UUID
    project_id: UUID
    subject_id: UUID
    kind: EpisodeKind
    content: str
    content_hash: str
    occurred_at: datetime
    ingested_at: datetime
    source: str
    sensitivity: Sensitivity
    status: EpisodeStatus
    agent_id: UUID | None = None
    session_id: UUID | None = None
    role: str | None = None
    source_ref: str | None = None
    consent_basis: str | None = None


class EpisodeNotFoundError(Exception):
    pass
