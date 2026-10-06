from typing import assert_type

from memory_application.ports import (
    BackgroundExecutor,
    EmbeddingProvider,
    ModelProvider,
    ObjectStore,
    TelemetrySink,
)


def test_required_port_types_are_public() -> None:
    assert_type(ModelProvider, type[ModelProvider])
    assert_type(EmbeddingProvider, type[EmbeddingProvider])
    assert_type(BackgroundExecutor, type[BackgroundExecutor])
    assert_type(TelemetrySink, type[TelemetrySink])
    assert_type(ObjectStore, type[ObjectStore])
