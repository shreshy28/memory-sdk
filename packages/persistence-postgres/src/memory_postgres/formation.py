# ruff: noqa: E501
import hashlib
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from memory_application.workflows.formation import FormationCandidate
from memory_domain import Episode, RequestContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from memory_postgres.repositories import _episode_from_row
from memory_postgres.rls import set_trusted_scope


class PostgresFormationRepository:
    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)

    async def load_episode(self, context: RequestContext, episode_id: UUID) -> Episode:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM episodes WHERE id = :id AND tenant_id = :tenant AND project_id = :project AND status NOT IN ('rejected', 'failed')"
                        ),
                        {
                            "id": episode_id,
                            "tenant": context.tenant_id,
                            "project": context.project_id,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    "UPDATE operations SET status = 'processing' WHERE resource_id = :episode AND tenant_id = :tenant AND project_id = :project"
                ),
                {"episode": episode_id, "tenant": context.tenant_id, "project": context.project_id},
            )
            await connection.execute(
                text("UPDATE episodes SET status = 'processing' WHERE id = :id"), {"id": episode_id}
            )
        return _episode_from_row(row)

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
    ) -> None:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            await connection.execute(
                text(
                    "INSERT INTO formation_runs (id, tenant_id, project_id, operation_id, stage, provider, model, prompt_version, schema_version, usage, safety_outcome, started_at, completed_at) VALUES (:id, :tenant, :project, :operation, :stage, :provider, :model, 'formation-v1', 'candidate-v1', CAST(:usage AS jsonb), :safety, :now, :now) ON CONFLICT (operation_id, stage) DO UPDATE SET provider = COALESCE(EXCLUDED.provider, formation_runs.provider), model = COALESCE(EXCLUDED.model, formation_runs.model), usage = EXCLUDED.usage, safety_outcome = COALESCE(EXCLUDED.safety_outcome, formation_runs.safety_outcome), completed_at = EXCLUDED.completed_at"
                ),
                {
                    "id": uuid4(),
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                    "operation": operation_id,
                    "stage": stage,
                    "provider": provider,
                    "model": model,
                    "usage": json.dumps(usage or {}),
                    "safety": safety_outcome,
                    "now": datetime.now(UTC),
                },
            )

    async def write_candidate(
        self,
        context: RequestContext,
        operation_id: UUID,
        episode: Episode,
        candidate: FormationCandidate,
    ) -> UUID:
        fingerprint = hashlib.sha256(
            f"{candidate.kind.value}\0{candidate.text.strip().casefold()}".encode()
        ).hexdigest()
        memory_id = uuid5(NAMESPACE_URL, f"{operation_id}:memory:{fingerprint}")
        version_id = uuid5(NAMESPACE_URL, f"{operation_id}:version:{fingerprint}")
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            await connection.execute(
                text(
                    "INSERT INTO memories (id, tenant_id, project_id, subject_id, kind, provenance_mode, status, created_at, updated_at) VALUES (:id, :tenant, :project, :subject, :kind, 'observed', 'active', :now, :now) ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": memory_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                    "subject": episode.subject_id,
                    "kind": candidate.kind.value,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO memory_versions (id, memory_id, version, text, confidence, importance, sensitivity, recorded_at, actor_id, reason) VALUES (:id, :memory, 1, :text, :confidence, :importance, :sensitivity, :now, :actor, 'episode_formation') ON CONFLICT (id) DO NOTHING"
                ),
                {
                    "id": version_id,
                    "memory": memory_id,
                    "text": candidate.text,
                    "confidence": candidate.confidence,
                    "importance": candidate.importance,
                    "sensitivity": candidate.sensitivity.value,
                    "now": now,
                    "actor": context.principal_id,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO memory_evidence (memory_version_id, episode_id, evidence_role) VALUES (:version, :episode, 'observation') ON CONFLICT (memory_version_id) DO NOTHING"
                ),
                {"version": version_id, "episode": episode.id},
            )
            await connection.execute(
                text(
                    "UPDATE memories SET current_version_id = :version WHERE id = :memory AND current_version_id IS NULL"
                ),
                {"version": version_id, "memory": memory_id},
            )
        return version_id

    async def store_embedding(
        self,
        context: RequestContext,
        version_id: UUID,
        *,
        provider: str,
        model: str,
        dimensions: int,
        vector: list[float],
    ) -> None:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            await connection.execute(
                text(
                    "INSERT INTO memory_embeddings (memory_version_id, provider, model, version, dimensions, embedding) VALUES (:version_id, :provider, :model, 'v1', :dimensions, :embedding) ON CONFLICT (memory_version_id) DO UPDATE SET provider = EXCLUDED.provider, model = EXCLUDED.model, dimensions = EXCLUDED.dimensions, embedding = EXCLUDED.embedding"
                ),
                {
                    "version_id": version_id,
                    "provider": provider,
                    "model": model,
                    "dimensions": dimensions,
                    "embedding": str(vector),
                },
            )

    async def promote(
        self,
        context: RequestContext,
        version_id: UUID,
        episode: Episode,
        candidate: FormationCandidate,
    ) -> None:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            if candidate.promote_profile:
                await connection.execute(
                    text(
                        "INSERT INTO profile_entries (id, tenant_id, project_id, memory_version_id, subject_id, priority, token_cost, status) VALUES (:id, :tenant, :project, :version, :subject, :priority, :tokens, 'active') ON CONFLICT (memory_version_id) DO NOTHING"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": context.tenant_id,
                        "project": context.project_id,
                        "version": version_id,
                        "subject": episode.subject_id,
                        "priority": candidate.importance,
                        "tokens": max(1, len(candidate.text.split())),
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE profile_entries SET status = 'archived' WHERE id IN (SELECT id FROM profile_entries WHERE tenant_id = :tenant AND project_id = :project AND subject_id = :subject AND status = 'active' ORDER BY priority DESC, id OFFSET 20)"
                    ),
                    {
                        "tenant": context.tenant_id,
                        "project": context.project_id,
                        "subject": episode.subject_id,
                    },
                )
            if candidate.promote_session and episode.session_id is not None:
                await connection.execute(
                    text(
                        "INSERT INTO session_state (id, tenant_id, project_id, memory_version_id, session_id, state_kind, status) VALUES (:id, :tenant, :project, :version, :session, :kind, 'active') ON CONFLICT (memory_version_id) DO NOTHING"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": context.tenant_id,
                        "project": context.project_id,
                        "version": version_id,
                        "session": episode.session_id,
                        "kind": candidate.kind.value,
                    },
                )

    async def finish(
        self,
        context: RequestContext,
        operation_id: UUID,
        episode_id: UUID,
        *,
        rejected: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        operation_status = "rejected" if rejected else "searchable"
        episode_status = "rejected" if rejected else "completed"
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            await connection.execute(
                text(
                    "UPDATE operations SET status = :status, completed_at = :now, retryable = false, failure_code = NULL WHERE id = :id AND tenant_id = :tenant AND project_id = :project"
                ),
                {
                    "status": operation_status,
                    "now": now,
                    "id": operation_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                },
            )
            await connection.execute(
                text("UPDATE episodes SET status = :status WHERE id = :id"),
                {"status": episode_status, "id": episode_id},
            )

    async def fail(
        self, context: RequestContext, operation_id: UUID, code: str, *, retryable: bool
    ) -> None:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            await connection.execute(
                text(
                    "UPDATE operations SET status = :status, failure_code = :code, retryable = :retryable WHERE id = :id AND tenant_id = :tenant AND project_id = :project"
                ),
                {
                    "status": "retryable_failed" if retryable else "terminal_failed",
                    "code": code,
                    "retryable": retryable,
                    "id": operation_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                },
            )

    async def close(self) -> None:
        await self._engine.dispose()
