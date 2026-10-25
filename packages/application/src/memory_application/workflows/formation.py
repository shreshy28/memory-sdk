from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from memory_domain import Episode, MemoryKind, RequestContext, Sensitivity

from memory_application.ports import EmbeddingProvider, ModelProvider, ProviderError

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": 1,
            "items": {
                "type": "object",
                "required": ["kind", "text", "confidence", "importance"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "fact",
                            "preference",
                            "goal",
                            "constraint",
                            "procedure",
                            "summary",
                        ],
                    },
                    "text": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "importance": {"type": "number", "minimum": 0, "maximum": 1},
                    "sensitivity": {
                        "type": "string",
                        "enum": ["general", "sensitive", "restricted"],
                    },
                    "promote_profile": {"type": "boolean"},
                    "promote_session": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
        }
    },
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class FormationCandidate:
    kind: MemoryKind
    text: str
    confidence: float
    importance: float
    sensitivity: Sensitivity
    promote_profile: bool = False
    promote_session: bool = False


class FormationRepository(Protocol):
    async def load_episode(self, context: RequestContext, episode_id: UUID) -> Episode: ...
    async def begin_stage(
        self,
        context: RequestContext,
        operation_id: UUID,
        stage: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        usage: dict[str, int] | None = None,
        safety_outcome: str | None = None,
    ) -> None: ...
    async def write_candidate(
        self,
        context: RequestContext,
        operation_id: UUID,
        episode: Episode,
        candidate: FormationCandidate,
    ) -> UUID: ...
    async def store_embedding(
        self,
        context: RequestContext,
        version_id: UUID,
        *,
        provider: str,
        model: str,
        dimensions: int,
        vector: list[float],
    ) -> None: ...
    async def promote(
        self,
        context: RequestContext,
        version_id: UUID,
        episode: Episode,
        candidate: FormationCandidate,
    ) -> None: ...
    async def finish(
        self,
        context: RequestContext,
        operation_id: UUID,
        episode_id: UUID,
        *,
        rejected: bool = False,
    ) -> None: ...
    async def fail(
        self, context: RequestContext, operation_id: UUID, code: str, *, retryable: bool
    ) -> None: ...


class FormationWorkflow:
    def __init__(
        self, repository: FormationRepository, model: ModelProvider, embeddings: EmbeddingProvider
    ) -> None:
        self.repository = repository
        self.model = model
        self.embeddings = embeddings

    async def run(self, context: RequestContext, operation_id: UUID, episode_id: UUID) -> None:
        episode = await self.repository.load_episode(context, episode_id)
        try:
            await self.repository.begin_stage(context, operation_id, "extracting")
            result = await self.model.generate_structured(
                prompt=episode.content, schema=EXTRACTION_SCHEMA, timeout_seconds=20
            )
            await self.repository.begin_stage(
                context,
                operation_id,
                "classifying",
                provider=result.provider,
                model=result.model,
                usage={"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
                safety_outcome=result.safety_outcome,
            )
            candidates = self._candidates(result.value, episode.sensitivity)
            await self.repository.begin_stage(context, operation_id, "evaluating")
            accepted = [item for item in candidates if item.confidence >= 0.5 and item.text.strip()]
            if not accepted:
                await self.repository.finish(context, operation_id, episode_id, rejected=True)
                return
            for candidate in accepted:
                version_id = await self.repository.write_candidate(
                    context, operation_id, episode, candidate
                )
                batch = await self.embeddings.embed([candidate.text])
                if len(batch.vectors) != 1 or len(batch.vectors[0]) != batch.dimensions:
                    raise ProviderError("invalid_embedding", retryable=False)
                await self.repository.store_embedding(
                    context,
                    version_id,
                    provider=batch.provider,
                    model=batch.model,
                    dimensions=batch.dimensions,
                    vector=list(batch.vectors[0]),
                )
                await self.repository.promote(context, version_id, episode, candidate)
            await self.repository.finish(context, operation_id, episode_id)
        except ProviderError as error:
            await self.repository.fail(context, operation_id, error.code, retryable=error.retryable)
            raise

    @staticmethod
    def _candidates(
        value: dict[str, Any], default_sensitivity: Sensitivity
    ) -> list[FormationCandidate]:
        raw = value.get("candidates")
        if not isinstance(raw, list):
            raise ProviderError("malformed_output", retryable=False)
        candidates = []
        try:
            for item in raw:
                candidates.append(
                    FormationCandidate(
                        MemoryKind(item["kind"]),
                        str(item["text"]),
                        float(item["confidence"]),
                        float(item["importance"]),
                        Sensitivity(item.get("sensitivity", default_sensitivity.value)),
                        bool(item.get("promote_profile", False)),
                        bool(item.get("promote_session", False)),
                    )
                )
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError("malformed_output", retryable=False) from error
        return candidates
