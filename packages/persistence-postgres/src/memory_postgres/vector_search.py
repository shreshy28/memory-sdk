from memory_domain import RequestContext
from memory_retrieval import Candidate, QueryPlan
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from memory_postgres.lexical_search import _scope_conditions
from memory_postgres.rls import set_trusted_scope


class PostgresVectorSearch:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def search(
        self,
        context: RequestContext,
        plan: QueryPlan,
        query_vector: tuple[float, ...] | None = None,
    ) -> tuple[Candidate, ...]:
        if query_vector is None:
            return ()
        conditions, parameters = _scope_conditions(context, plan)
        parameters["embedding"] = str(list(query_vector))
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT m.id, v.id AS version_id, "
                            "1 - (e.embedding <=> CAST(:embedding AS vector)) AS score "
                            "FROM memories m JOIN memory_versions v ON v.id = m.current_version_id "
                            "JOIN memory_embeddings e ON e.memory_version_id = v.id "
                            "LEFT JOIN suppression_markers s ON s.memory_id = m.id "
                            f"WHERE {' AND '.join(conditions)} "
                            "ORDER BY e.embedding <=> CAST(:embedding AS vector), m.id LIMIT :limit"
                        ),
                        parameters,
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            Candidate(row["id"], row["version_id"], rank, float(row["score"]))
            for rank, row in enumerate(rows, 1)
        )
