from typing import Protocol

from memory_domain import HealthReport


class ReadinessProbe(Protocol):
    async def check(self) -> HealthReport: ...
