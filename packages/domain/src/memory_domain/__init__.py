"""Framework-free domain primitives for the memory platform."""

from memory_domain.health import ComponentStatus, HealthReport
from memory_domain.identity import AuthorizationError, RequestContext
from memory_domain.memory import (
    ConcurrentCorrectionError,
    DirectEvidence,
    InvalidMemoryError,
    Memory,
    MemoryKind,
    MemoryNotFoundError,
    MemoryStatus,
    MemoryVersion,
    ProvenanceMode,
    Sensitivity,
)
from memory_domain.operation import Operation, OperationStatus
from memory_domain.policy import is_currently_eligible

__all__ = [
    "AuthorizationError",
    "ComponentStatus",
    "ConcurrentCorrectionError",
    "DirectEvidence",
    "HealthReport",
    "InvalidMemoryError",
    "Memory",
    "MemoryKind",
    "MemoryNotFoundError",
    "MemoryStatus",
    "MemoryVersion",
    "Operation",
    "OperationStatus",
    "ProvenanceMode",
    "RequestContext",
    "Sensitivity",
    "is_currently_eligible",
]
