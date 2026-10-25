import os
from uuid import uuid4

import pytest
from memory_application.ports import Correction, NewMemory
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
            text("INSERT INTO tenants (id, name) VALUES (:id, 'test')"), {"id": tenant_id}
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
async def test_add_replay_correction_and_suppression_are_transactional() -> None:
    context, subject = await seed_scope()
    repository = PostgresMemoryRepository(DATABASE_URL)
    command = NewMemory(
        subject, MemoryKind.FACT, "Original", None, 1.0, 0.5, Sensitivity.GENERAL, None, None, None
    )
    memory, operation = await repository.add(context, command, "add-once")
    replayed, replay_operation = await repository.add(context, command, "add-once")
    assert replayed.id == memory.id
    assert replay_operation.id == operation.id

    corrected, _ = await repository.correct(
        context,
        memory.id,
        Correction("Corrected", None, "user correction", 1),
        "correct-once",
    )
    assert corrected.current_version.version == 2
    assert [item.text for item in await repository.history(context, memory.id)] == [
        "Corrected",
        "Original",
    ]

    await repository.suppress(context, memory.id, "suppress-once")
    with pytest.raises(MemoryNotFoundError):
        await repository.get(context, memory.id)
    assert not (await repository.list_current(context, subject_id=None, cursor=None, limit=50))[0]
    await repository.close()
