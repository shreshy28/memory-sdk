import os
from uuid import uuid4

import pytest
from memory_application.ports import NewMemory
from memory_domain import MemoryKind, MemoryNotFoundError, RequestContext, Sensitivity
from memory_postgres import PostgresMemoryRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv(
    "MEMORY_DATABASE_URL", "postgresql+asyncpg://memory:memory@localhost:55432/memory"
)


async def seed_scope() -> tuple[RequestContext, object]:
    tenant_id, project_id, principal_id, subject_id = uuid4(), uuid4(), uuid4(), uuid4()
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO tenants (id, name) VALUES (:id, 'isolation')"),
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


@pytest.mark.asyncio
async def test_repository_denies_cross_project_memory_access() -> None:
    owner, subject = await seed_scope()
    repository = PostgresMemoryRepository(DATABASE_URL)
    memory, _ = await repository.add(
        owner,
        NewMemory(
            subject,
            MemoryKind.FACT,
            "private",
            None,
            1.0,
            0.5,
            Sensitivity.GENERAL,
            None,
            None,
            None,
        ),
        "owner-add",
    )
    attacker = RequestContext(uuid4(), uuid4(), uuid4())
    with pytest.raises(MemoryNotFoundError):
        await repository.get(attacker, memory.id)
    items, _ = await repository.list_current(attacker, subject_id=None, cursor=None, limit=50)
    assert items == []
    await repository.close()
