from memory_domain import ComponentStatus, HealthReport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class PostgresReadinessProbe:
    def __init__(self, database_url: str, expected_revision: str) -> None:
        self._engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self._expected_revision = expected_revision

    async def check(self) -> HealthReport:
        database = ComponentStatus.NOT_READY
        migrations = ComponentStatus.NOT_READY
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                database = ComponentStatus.READY
                revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                if revision == self._expected_revision:
                    migrations = ComponentStatus.READY
        except Exception:
            pass

        checks = {"database": database, "migrations": migrations}
        status = (
            ComponentStatus.READY
            if all(value is ComponentStatus.READY for value in checks.values())
            else ComponentStatus.NOT_READY
        )
        return HealthReport(status=status, checks=checks)

    async def close(self) -> None:
        await self._engine.dispose()
