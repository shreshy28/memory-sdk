# ruff: noqa: E501
from datetime import datetime
from typing import Any
from uuid import UUID

from memory_application.ports import Correction, NewEpisode, NewMemory
from memory_domain import Episode, EpisodeKind, Memory, MemoryKind, Operation, Sensitivity
from pydantic import BaseModel, Field, model_validator


class ErrorDetail(BaseModel):
    code: str
    message: str
    correlation_id: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class AppendEpisodeRequest(BaseModel):
    subject_id: UUID
    kind: EpisodeKind = EpisodeKind.CONVERSATION
    content: str = Field(min_length=1, max_length=1_000_000)
    occurred_at: datetime
    source: str = Field(min_length=1, max_length=200)
    sensitivity: Sensitivity = Sensitivity.GENERAL
    agent_id: UUID | None = None
    session_id: UUID | None = None
    role: str | None = Field(default=None, max_length=50)
    source_ref: str | None = Field(default=None, max_length=500)
    consent_basis: str | None = Field(default=None, max_length=200)

    def to_command(self) -> NewEpisode:
        return NewEpisode(**self.model_dump())


class EpisodeResponse(BaseModel):
    id: UUID
    subject_id: UUID
    agent_id: UUID | None
    session_id: UUID | None
    kind: EpisodeKind
    role: str | None
    content: str
    content_hash: str
    occurred_at: datetime
    ingested_at: datetime
    source: str
    source_ref: str | None
    sensitivity: Sensitivity
    consent_basis: str | None
    status: str


class EpisodeMutationResponse(BaseModel):
    episode: EpisodeResponse
    operation: "OperationResponse"


class AddMemoryRequest(BaseModel):
    subject_id: UUID
    kind: MemoryKind
    text: str = Field(min_length=1, max_length=100_000)
    structured_value: dict[str, Any] | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    sensitivity: Sensitivity = Sensitivity.GENERAL
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    collection_id: UUID | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "AddMemoryRequest":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError("valid_to must be after valid_from")
        return self

    def to_command(self) -> NewMemory:
        return NewMemory(**self.model_dump())


class CorrectMemoryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    structured_value: dict[str, Any] | None = None
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    importance: float | None = Field(default=None, ge=0, le=1)
    sensitivity: Sensitivity | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "CorrectMemoryRequest":
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to <= self.valid_from
        ):
            raise ValueError("valid_to must be after valid_from")
        return self

    def to_command(self) -> Correction:
        return Correction(**self.model_dump())


class EvidenceResponse(BaseModel):
    type: str = "direct_entry"
    id: UUID
    actor_id: UUID | None = None
    recorded_at: datetime | None = None
    evidence_role: str | None = None


class MemoryVersionResponse(BaseModel):
    id: UUID
    version: int
    text: str
    structured_value: dict[str, Any] | None
    confidence: float
    importance: float
    sensitivity: Sensitivity
    valid_from: datetime | None
    valid_to: datetime | None
    recorded_at: datetime
    actor_id: UUID
    reason: str
    evidence: list[EvidenceResponse]


class MemoryResponse(BaseModel):
    id: UUID
    subject_id: UUID
    collection_id: UUID | None
    kind: MemoryKind
    provenance_mode: str
    status: str
    current_version: MemoryVersionResponse
    created_at: datetime
    updated_at: datetime


class OperationResponse(BaseModel):
    operation_id: UUID
    operation_type: str
    resource_id: UUID | None
    status: str
    accepted_at: datetime
    committed_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    retryable: bool


class MutationResponse(BaseModel):
    memory: MemoryResponse | None
    operation: OperationResponse


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
    next_cursor: str | None


class HistoryResponse(BaseModel):
    items: list[MemoryVersionResponse]


def memory_response(memory: Memory) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        subject_id=memory.subject_id,
        collection_id=memory.collection_id,
        kind=memory.kind,
        provenance_mode=memory.provenance_mode.value,
        status=memory.status.value,
        current_version=version_response(memory.current_version),
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


def episode_response(episode: Episode) -> EpisodeResponse:
    return EpisodeResponse(
        id=episode.id,
        subject_id=episode.subject_id,
        agent_id=episode.agent_id,
        session_id=episode.session_id,
        kind=episode.kind,
        role=episode.role,
        content=episode.content,
        content_hash=episode.content_hash,
        occurred_at=episode.occurred_at,
        ingested_at=episode.ingested_at,
        source=episode.source,
        source_ref=episode.source_ref,
        sensitivity=episode.sensitivity,
        consent_basis=episode.consent_basis,
        status=episode.status.value,
    )


def version_response(version: Any) -> MemoryVersionResponse:
    evidence = []
    if version.direct_evidence is not None:
        evidence.append(
            EvidenceResponse(
                id=version.direct_evidence.id,
                actor_id=version.direct_evidence.actor_id,
                recorded_at=version.direct_evidence.recorded_at,
            )
        )
    evidence.extend(
        EvidenceResponse(
            type="episode",
            id=item.episode_id,
            evidence_role=item.evidence_role,
        )
        for item in version.episode_evidence
    )
    return MemoryVersionResponse(
        id=version.id,
        version=version.version,
        text=version.text,
        structured_value=version.structured_value,
        confidence=version.confidence,
        importance=version.importance,
        sensitivity=version.sensitivity,
        valid_from=version.valid_from,
        valid_to=version.valid_to,
        recorded_at=version.recorded_at,
        actor_id=version.actor_id,
        reason=version.reason,
        evidence=evidence,
    )


def operation_response(operation: Operation) -> OperationResponse:
    return OperationResponse(
        operation_id=operation.id,
        operation_type=operation.operation_type,
        resource_id=operation.resource_id,
        status=operation.status.value,
        accepted_at=operation.accepted_at,
        committed_at=operation.committed_at,
        completed_at=operation.completed_at,
        failure_code=operation.failure_code,
        retryable=operation.retryable,
    )
