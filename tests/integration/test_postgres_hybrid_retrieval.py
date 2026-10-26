import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from memory_application.ports import NewMemory
from memory_domain import MemoryKind, RequestContext, Sensitivity
from memory_postgres import (
    PostgresEligibilityRepository,
    PostgresFormationRepository,
    PostgresLexicalSearch,
    PostgresMemoryRepository,
    PostgresVectorSearch,
)
from memory_providers import DeterministicEmbeddingProvider
from memory_retrieval import RetrievalService, RetrievalStatus
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv(
    "MEMORY_DATABASE_URL", "postgresql+asyncpg://memory:memory@localhost:55432/memory"
)


async def seed_scope() -> tuple[RequestContext, UUID]:
    tenant_id, project_id, principal_id, subject_id = uuid4(), uuid4(), uuid4(), uuid4()
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO tenants (id, name) VALUES (:id, 'retrieval-test')"),
            {"id": tenant_id},
        )
        await connection.execute(
            text("INSERT INTO projects (id, tenant_id, name) VALUES (:id, :tenant, 'test')"),
            {"id": project_id, "tenant": tenant_id},
        )
        await connection.execute(
            text(
                "INSERT INTO principals (id, tenant_id, display_name) "
                "VALUES (:id, :tenant, 'tester')"
            ),
            {"id": principal_id, "tenant": tenant_id},
        )
        await connection.execute(
            text(
                "INSERT INTO project_memberships (tenant_id, project_id, principal_id) "
                "VALUES (:tenant, :project, :principal)"
            ),
            {"tenant": tenant_id, "project": project_id, "principal": principal_id},
        )
        await connection.execute(
            text(
                "INSERT INTO subjects (id, tenant_id, project_id) VALUES (:id, :tenant, :project)"
            ),
            {"id": subject_id, "tenant": tenant_id, "project": project_id},
        )
    await engine.dispose()
    return RequestContext(tenant_id, project_id, principal_id), subject_id


async def add_searchable_memory(
    repository: PostgresMemoryRepository,
    formation: PostgresFormationRepository,
    embeddings: DeterministicEmbeddingProvider,
    context: RequestContext,
    subject_id: UUID,
    text_value: str,
    *,
    valid_to: datetime | None = None,
) -> UUID:
    memory, _ = await repository.add(
        context,
        NewMemory(
            subject_id,
            MemoryKind.PREFERENCE,
            text_value,
            None,
            0.9,
            0.8,
            Sensitivity.GENERAL,
            None,
            valid_to,
            None,
        ),
        f"add-{uuid4()}",
    )
    batch = await embeddings.embed([text_value])
    await formation.store_embedding(
        context,
        memory.current_version.id,
        provider=batch.provider,
        model=batch.model,
        dimensions=batch.dimensions,
        vector=list(batch.vectors[0]),
    )
    return memory.id


@pytest.mark.asyncio
async def test_postgres_hybrid_search_enforces_current_policy_scoped_results() -> None:
    context, subject_id = await seed_scope()
    other_context, other_subject_id = await seed_scope()
    repository = PostgresMemoryRepository(DATABASE_URL)
    formation = PostgresFormationRepository(DATABASE_URL, engine=repository.engine)
    embeddings = DeterministicEmbeddingProvider()
    service = RetrievalService(
        PostgresLexicalSearch(repository.engine),
        PostgresVectorSearch(repository.engine),
        PostgresEligibilityRepository(repository.engine),
        embeddings,
    )

    expected_id = await add_searchable_memory(
        repository, formation, embeddings, context, subject_id, "prefers jasmine tea"
    )
    suppressed_id = await add_searchable_memory(
        repository, formation, embeddings, context, subject_id, "prefers black tea"
    )
    await add_searchable_memory(
        repository,
        formation,
        embeddings,
        context,
        subject_id,
        "preferred tea in the past",
        valid_to=datetime.now(UTC) - timedelta(days=1),
    )
    await add_searchable_memory(
        repository,
        formation,
        embeddings,
        other_context,
        other_subject_id,
        "prefers jasmine tea",
    )
    await repository.suppress(context, suppressed_id, f"suppress-{uuid4()}")

    result = await service.search(
        context, query="prefers jasmine tea", subject_id=subject_id, top_k=10
    )

    assert result.status is RetrievalStatus.COMPLETE
    assert [item.memory.id for item in result.items] == [expected_id]
    assert result.items[0].lexical_rank is not None
    assert result.items[0].semantic_rank is not None

    cross_scope = await service.search(
        context, query="prefers jasmine tea", subject_id=other_subject_id, top_k=10
    )
    assert cross_scope.items == ()
    await repository.close()


@pytest.mark.asyncio
async def test_hybrid_retrieval_migration_has_expected_vector_shape_and_indexes() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        vector_type = await connection.scalar(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "WHERE a.attrelid = 'memory_embeddings'::regclass "
                "AND a.attname = 'embedding'"
            )
        )
        indexes = set(
            (
                await connection.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE schemaname = current_schema() AND indexname IN "
                        "('ix_memory_versions_text_fts', 'ix_memory_embeddings_cosine', "
                        "'ix_memories_retrieval_scope')"
                    )
                )
            ).scalars()
        )
    await engine.dispose()

    assert vector_type == "vector(16)"
    assert indexes == {
        "ix_memories_retrieval_scope",
        "ix_memory_versions_text_fts",
        "ix_memory_embeddings_cosine",
    }
