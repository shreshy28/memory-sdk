from uuid import UUID

from memory_domain import Memory, RequestContext
from memory_retrieval import EligibilityRepository
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine

from memory_postgres.repositories import _memory_from_row, _memory_select
from memory_postgres.rls import set_trusted_scope


class PostgresEligibilityRepository(EligibilityRepository):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def load_eligible(
        self, context: RequestContext, candidate_versions: tuple[tuple[UUID, UUID], ...]
    ) -> tuple[Memory, ...]:
        if not candidate_versions:
            return ()
        version_ids = [version_id for _, version_id in candidate_versions]
        statement = text(
            _memory_select() + " WHERE m.tenant_id = :tenant AND m.project_id = :project "
            "AND m.status = 'active' AND s.memory_id IS NULL "
            "AND m.current_version_id IN :versions "
            "AND (v.valid_from IS NULL OR v.valid_from <= now()) "
            "AND (v.valid_to IS NULL OR v.valid_to > now())"
        ).bindparams(bindparam("versions", expanding=True))
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            rows = (
                (
                    await connection.execute(
                        statement,
                        {
                            "tenant": context.tenant_id,
                            "project": context.project_id,
                            "versions": version_ids,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return tuple(_memory_from_row(row) for row in rows)
