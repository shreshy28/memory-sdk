from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from memory_application.workflows import FormationWorkflow
from memory_application.workflows.formation import FormationCandidate
from memory_domain import (
    Episode,
    EpisodeKind,
    EpisodeStatus,
    OperationStatus,
    RequestContext,
    Sensitivity,
)
from memory_providers import DeterministicEmbeddingProvider, DeterministicModelProvider


class FormationStore:
    def __init__(self, episode: Episode) -> None:
        self.episode = episode
        self.versions: dict[str, UUID] = {}
        self.embeddings: set[UUID] = set()
        self.status = OperationStatus.COMMITTED
        self.stages: set[str] = set()

    async def load_episode(self, context: RequestContext, episode_id: UUID) -> Episode:
        assert context.tenant_id == self.episode.tenant_id
        assert episode_id == self.episode.id
        self.status = OperationStatus.PROCESSING
        return self.episode

    async def begin_stage(
        self, context: RequestContext, operation_id: UUID, stage: str, **kwargs: object
    ) -> None:
        self.stages.add(stage)

    async def write_candidate(
        self,
        context: RequestContext,
        operation_id: UUID,
        episode: Episode,
        candidate: FormationCandidate,
    ) -> UUID:
        return self.versions.setdefault(candidate.text, uuid4())

    async def store_embedding(
        self, context: RequestContext, version_id: UUID, **kwargs: object
    ) -> None:
        self.embeddings.add(version_id)

    async def promote(
        self,
        context: RequestContext,
        version_id: UUID,
        episode: Episode,
        candidate: FormationCandidate,
    ) -> None:
        return None

    async def finish(
        self,
        context: RequestContext,
        operation_id: UUID,
        episode_id: UUID,
        *,
        rejected: bool = False,
    ) -> None:
        self.status = OperationStatus.REJECTED if rejected else OperationStatus.SEARCHABLE

    async def fail(
        self, context: RequestContext, operation_id: UUID, code: str, *, retryable: bool
    ) -> None:
        self.status = (
            OperationStatus.RETRYABLE_FAILED if retryable else OperationStatus.TERMINAL_FAILED
        )


@pytest.mark.asyncio
async def test_episode_forms_one_evidence_backed_searchable_memory_idempotently() -> None:
    context = RequestContext(uuid4(), uuid4(), uuid4())
    episode = Episode(
        uuid4(),
        context.tenant_id,
        context.project_id,
        uuid4(),
        EpisodeKind.CONVERSATION,
        "I prefer tea",
        "hash",
        datetime.now(UTC),
        datetime.now(UTC),
        "test",
        Sensitivity.GENERAL,
        EpisodeStatus.ACCEPTED,
    )
    store = FormationStore(episode)
    workflow = FormationWorkflow(
        store, DeterministicModelProvider(), DeterministicEmbeddingProvider()
    )
    operation_id = uuid4()

    await workflow.run(context, operation_id, episode.id)
    await workflow.run(context, operation_id, episode.id)

    assert store.status is OperationStatus.SEARCHABLE
    assert len(store.versions) == 1
    assert len(store.embeddings) == 1
    assert store.stages == {"extracting", "classifying", "evaluating"}
