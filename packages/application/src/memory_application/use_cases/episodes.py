from uuid import UUID

from memory_domain import Episode, Operation, RequestContext

from memory_application.ports.repositories import EpisodeRepository, NewEpisode


class EpisodeService:
    def __init__(self, repository: EpisodeRepository) -> None:
        self.repository = repository

    async def append(
        self, context: RequestContext, command: NewEpisode, idempotency_key: str
    ) -> tuple[Episode, Operation]:
        if not idempotency_key or len(idempotency_key) > 255:
            raise ValueError("a valid Idempotency-Key is required")
        if not command.content.strip():
            raise ValueError("episode content is required")
        if command.sensitivity.value == "restricted" and command.consent_basis is None:
            raise ValueError("restricted episodes require a consent basis")
        return await self.repository.append_episode(context, command, idempotency_key)

    async def get(self, context: RequestContext, episode_id: UUID) -> Episode:
        return await self.repository.get_episode(context, episode_id)
