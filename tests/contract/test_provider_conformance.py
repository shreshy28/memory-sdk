import pytest
from memory_application.ports import EmbeddingProvider, ModelProvider
from memory_providers import DeterministicEmbeddingProvider, DeterministicModelProvider


@pytest.mark.asyncio
async def test_default_providers_satisfy_formation_contract() -> None:
    model: ModelProvider = DeterministicModelProvider()
    embedding: EmbeddingProvider = DeterministicEmbeddingProvider()

    result = await model.generate_structured(
        prompt="I prefer tea",
        schema={"type": "object"},
        timeout_seconds=1,
    )
    assert result.provider and result.model
    assert result.value["candidates"][0]["kind"] == "preference"

    batch = await embedding.embed(["I prefer tea", "Project deadline is Friday"])
    assert len(batch.vectors) == 2
    assert all(len(vector) == batch.dimensions for vector in batch.vectors)
    assert batch.provider and batch.model


@pytest.mark.asyncio
async def test_default_embedding_is_reproducible() -> None:
    provider = DeterministicEmbeddingProvider()
    first = await provider.embed(["same input"])
    second = await provider.embed(["same input"])
    assert first.vectors == second.vectors
