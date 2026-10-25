# ruff: noqa: E501
from datetime import UTC, datetime, timedelta
from uuid import UUID

from memory_application.ports import WorkItem
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class PostgresBackgroundExecutor:
    def __init__(
        self, database_url: str, *, lease_seconds: int = 30, engine: AsyncEngine | None = None
    ) -> None:
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)
        self._lease_seconds = lease_seconds

    async def submit(self, item: WorkItem) -> None:
        raise NotImplementedError("jobs must be published in their canonical transaction")

    async def lease(self, *, owner: str, limit: int) -> list[WorkItem]:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self._lease_seconds)
        async with self._engine.begin() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "WITH candidates AS (SELECT id FROM outbox_jobs WHERE (status = 'pending' OR (status = 'leased' AND lease_expires_at < :now)) AND available_at <= :now ORDER BY available_at FOR UPDATE SKIP LOCKED LIMIT :limit) UPDATE outbox_jobs j SET status = 'leased', lease_owner = :owner, lease_expires_at = :expires, attempts = attempts + 1 FROM candidates c WHERE j.id = c.id RETURNING j.*"
                        ),
                        {"now": now, "limit": limit, "owner": owner, "expires": expires},
                    )
                )
                .mappings()
                .all()
            )
        return [
            WorkItem(
                row["id"],
                row["job_type"],
                dict(row["payload"]),
                row["available_at"],
                row["operation_id"],
                row["attempts"],
                row["lease_expires_at"],
            )
            for row in rows
        ]

    async def complete(self, item_id: UUID, *, owner: str) -> None:
        await self._owned_update(
            item_id, owner, "status = 'completed', lease_owner = NULL, lease_expires_at = NULL"
        )

    async def heartbeat(self, item_id: UUID, *, owner: str) -> bool:
        expires = datetime.now(UTC) + timedelta(seconds=self._lease_seconds)
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    "UPDATE outbox_jobs SET lease_expires_at = :expires WHERE id = :id AND lease_owner = :owner AND status = 'leased'"
                ),
                {"expires": expires, "id": item_id, "owner": owner},
            )
        return result.rowcount == 1

    async def retry(self, item_id: UUID, *, owner: str, delay_seconds: float) -> None:
        available = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE outbox_jobs SET status = 'pending', available_at = :available, lease_owner = NULL, lease_expires_at = NULL WHERE id = :id AND lease_owner = :owner"
                ),
                {"available": available, "id": item_id, "owner": owner},
            )

    async def cancel(self, item_id: UUID) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE outbox_jobs SET status = 'cancelled', lease_owner = NULL, lease_expires_at = NULL WHERE id = :id"
                ),
                {"id": item_id},
            )

    async def fail(self, item_id: UUID, *, owner: str, code: str) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE outbox_jobs SET status = 'failed', last_failure_code = :code, lease_owner = NULL, lease_expires_at = NULL WHERE id = :id AND lease_owner = :owner"
                ),
                {"id": item_id, "owner": owner, "code": code},
            )

    async def _owned_update(self, item_id: UUID, owner: str, assignment: str) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    f"UPDATE outbox_jobs SET {assignment} WHERE id = :id AND lease_owner = :owner"
                ),
                {"id": item_id, "owner": owner},
            )

    async def close(self) -> None:
        await self._engine.dispose()
