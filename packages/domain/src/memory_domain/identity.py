from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RequestContext:
    tenant_id: UUID
    project_id: UUID
    principal_id: UUID
    api_key_id: UUID | None = None


class AuthorizationError(Exception):
    pass
