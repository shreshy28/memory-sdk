from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class OperationStatus(StrEnum):
    ACCEPTED = "accepted"
    COMMITTED = "committed"
    PROCESSING = "processing"
    SEARCHABLE = "searchable"
    COMPLETED = "completed"
    REJECTED = "rejected"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"


@dataclass(frozen=True, slots=True)
class Operation:
    id: UUID
    operation_type: str
    status: OperationStatus
    accepted_at: datetime
    resource_id: UUID | None = None
    committed_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    retryable: bool = False
