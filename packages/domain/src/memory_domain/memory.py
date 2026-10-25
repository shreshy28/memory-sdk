from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class MemoryKind(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    CONSTRAINT = "constraint"
    PROCEDURE = "procedure"
    SUMMARY = "summary"


class ProvenanceMode(StrEnum):
    EXPLICIT = "explicit"
    OBSERVED = "observed"
    DERIVED = "derived"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Sensitivity(StrEnum):
    GENERAL = "general"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class DirectEvidence:
    id: UUID
    actor_id: UUID
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class EpisodeEvidence:
    episode_id: UUID
    evidence_role: str


@dataclass(frozen=True, slots=True)
class MemoryVersion:
    id: UUID
    memory_id: UUID
    version: int
    text: str
    structured_value: dict[str, Any] | None
    confidence: float
    importance: float
    sensitivity: Sensitivity
    recorded_at: datetime
    actor_id: UUID
    reason: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    direct_evidence: DirectEvidence | None = None
    episode_evidence: tuple[EpisodeEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class Memory:
    id: UUID
    tenant_id: UUID
    project_id: UUID
    subject_id: UUID
    kind: MemoryKind
    provenance_mode: ProvenanceMode
    status: MemoryStatus
    current_version: MemoryVersion
    created_at: datetime
    updated_at: datetime
    collection_id: UUID | None = None


class MemoryNotFoundError(Exception):
    pass


class ConcurrentCorrectionError(Exception):
    pass


class InvalidMemoryError(ValueError):
    pass
