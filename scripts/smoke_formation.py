import asyncio

from memory_application.ports import EmbeddingProvider, ModelProvider
from memory_providers import DeterministicEmbeddingProvider, DeterministicModelProvider


async def main() -> None:
    model: ModelProvider = DeterministicModelProvider()
    embeddings: EmbeddingProvider = DeterministicEmbeddingProvider()
    result = await model.generate_structured(
        prompt="I prefer tea", schema={"type": "object"}, timeout_seconds=1
    )
    candidates = result.value.get("candidates", [])
    if len(candidates) != 1:
        raise RuntimeError("fake provider did not form one candidate")
    batch = await embeddings.embed([candidates[0]["text"]])
    if len(batch.vectors) != 1 or len(batch.vectors[0]) != batch.dimensions:
        raise RuntimeError("fake provider returned an invalid embedding")


if __name__ == "__main__":
    asyncio.run(main())
