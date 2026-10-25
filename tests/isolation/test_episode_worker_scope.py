from datetime import UTC, datetime
from uuid import uuid4

import pytest
from memory_application.ports import NewEpisode
from memory_application.use_cases import EpisodeService
from memory_domain import (
    Episode,
    EpisodeKind,
    EpisodeStatus,
    Operation,
    OperationStatus,
    RequestContext,
    Sensitivity,
)


class ScopedEpisodeRepository:
    def __init__(self) -> None:
        self.context: RequestContext | None = None

    async def append_episode(
        self, context: RequestContext, command: NewEpisode, idempotency_key: str
    ) -> tuple[Episode, Operation]:
        self.context = context
        now, episode_id = datetime.now(UTC), uuid4()
        episode = Episode(
            episode_id,
            context.tenant_id,
            context.project_id,
            command.subject_id,
            command.kind,
            command.content,
            "hash",
            command.occurred_at,
            now,
            command.source,
            command.sensitivity,
            EpisodeStatus.ACCEPTED,
        )
        return episode, Operation(
            uuid4(), "episode.form", OperationStatus.COMMITTED, now, episode_id, now
        )

    async def get_episode(self, context: RequestContext, episode_id: object) -> Episode:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_episode_worker_uses_trusted_scope_not_payload_metadata() -> None:
    trusted = RequestContext(uuid4(), uuid4(), uuid4())
    repository = ScopedEpisodeRepository()
    service = EpisodeService(repository)
    command = NewEpisode(
        uuid4(), EpisodeKind.EVENT, "safe event", datetime.now(UTC), "test", Sensitivity.GENERAL
    )
    episode, _ = await service.append(trusted, command, "key")
    assert repository.context == trusted
    assert episode.tenant_id == trusted.tenant_id
    assert episode.project_id == trusted.project_id
