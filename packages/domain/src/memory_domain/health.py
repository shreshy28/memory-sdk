from dataclasses import dataclass
from enum import StrEnum


class ComponentStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: ComponentStatus
    checks: dict[str, ComponentStatus]

    @property
    def is_ready(self) -> bool:
        return self.status is ComponentStatus.READY
