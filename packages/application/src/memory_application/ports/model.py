from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ModelResult:
    value: dict[str, Any]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


class ModelProvider(Protocol):
    async def generate_structured(
        self, *, prompt: str, schema: dict[str, Any], timeout_seconds: float
    ) -> ModelResult: ...
