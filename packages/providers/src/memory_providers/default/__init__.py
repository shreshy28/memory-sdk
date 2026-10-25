import hashlib
import re
from collections.abc import Sequence
from typing import Any

from memory_application.ports import EmbeddingBatch, ModelResult


class DeterministicModelProvider:
    provider = "default"
    model = "deterministic-formation-v1"

    async def generate_structured(
        self, *, prompt: str, schema: dict[str, Any], timeout_seconds: float
    ) -> ModelResult:
        del schema, timeout_seconds
        text = prompt.strip()
        if not text:
            return ModelResult({"candidates": []}, self.provider, self.model, 0, 0)
        kind = "preference" if re.search(r"\b(like|prefer|favorite)\b", text, re.I) else "fact"
        candidate = {"kind": kind, "text": text, "confidence": 0.8, "importance": 0.5}
        return ModelResult(
            {"candidates": [candidate]},
            self.provider,
            self.model,
            len(text.split()),
            len(text.split()),
        )


class DeterministicEmbeddingProvider:
    provider = "default"
    model = "hash-embedding-v1"
    dimensions = 16

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append(tuple((byte - 127.5) / 127.5 for byte in digest[: self.dimensions]))
        return EmbeddingBatch(vectors, self.provider, self.model, self.dimensions)
