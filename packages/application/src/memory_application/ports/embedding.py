from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    vectors: Sequence[Sequence[float]]
    provider: str
    model: str
    dimensions: int


class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch: ...
