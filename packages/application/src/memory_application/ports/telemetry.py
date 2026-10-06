from contextlib import AbstractContextManager
from typing import Any, Protocol


class TelemetrySink(Protocol):
    def span(self, name: str, attributes: dict[str, Any]) -> AbstractContextManager[None]: ...

    def increment(self, name: str, value: int = 1) -> None: ...
