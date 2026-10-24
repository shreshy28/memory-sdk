from memory_domain import RequestContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def set_trusted_scope(connection: AsyncConnection, context: RequestContext) -> None:
    await connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(context.tenant_id)},
    )
    await connection.execute(
        text("SELECT set_config('app.project_id', :project_id, true)"),
        {"project_id": str(context.project_id)},
    )
