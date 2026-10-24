# ruff: noqa: E501
import base64
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from memory_application.ports.repositories import Correction, NewMemory
from memory_domain import (
    AuthorizationError,
    ConcurrentCorrectionError,
    DirectEvidence,
    Memory,
    MemoryKind,
    MemoryNotFoundError,
    MemoryStatus,
    MemoryVersion,
    Operation,
    OperationStatus,
    ProvenanceMode,
    RequestContext,
    Sensitivity,
)
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from memory_postgres.rls import set_trusted_scope


class PostgresMemoryRepository:
    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self._engine = engine or create_async_engine(database_url, pool_pre_ping=True)

    async def authenticate(self, api_key: str) -> RequestContext:
        digest = hashlib.sha256(api_key.encode()).hexdigest()
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT k.id, k.tenant_id, k.project_id, k.principal_id "
                            "FROM api_keys k JOIN project_memberships m "
                            "ON m.project_id = k.project_id AND m.principal_id = k.principal_id "
                            "WHERE k.key_hash = :digest AND k.revoked_at IS NULL"
                        ),
                        {"digest": digest},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AuthorizationError("invalid API key")
        return RequestContext(
            tenant_id=row["tenant_id"],
            project_id=row["project_id"],
            principal_id=row["principal_id"],
            api_key_id=row["id"],
        )

    async def add(
        self, context: RequestContext, command: NewMemory, idempotency_key: str
    ) -> tuple[Memory, Operation]:
        request_hash = _request_hash("add", command)
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            replay = await self._replay(connection, context, idempotency_key, request_hash)
            if replay is not None:
                return await self._get(connection, context, replay.resource_id), replay
            await self._ensure_subject(connection, context, command.subject_id)
            if command.collection_id is not None:
                await self._ensure_collection(connection, context, command.collection_id)

            now = datetime.now(UTC)
            memory_id, version_id, evidence_id, operation_id = uuid4(), uuid4(), uuid4(), uuid4()
            await connection.execute(
                text(
                    "INSERT INTO memories (id, tenant_id, project_id, subject_id, collection_id, kind, "
                    "provenance_mode, status, created_at, updated_at) VALUES "
                    "(:id, :tenant, :project, :subject, :collection, :kind, 'explicit', 'active', :now, :now)"
                ),
                {
                    "id": memory_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                    "subject": command.subject_id,
                    "collection": command.collection_id,
                    "kind": command.kind.value,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO direct_entries (id, tenant_id, project_id, actor_id, recorded_at) "
                    "VALUES (:id, :tenant, :project, :actor, :now)"
                ),
                {
                    "id": evidence_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                    "actor": context.principal_id,
                    "now": now,
                },
            )
            await self._insert_version(
                connection, context, memory_id, version_id, 1, command, now, "explicit_add"
            )
            await connection.execute(
                text(
                    "INSERT INTO memory_evidence (memory_version_id, direct_entry_id, evidence_role) VALUES (:version, :entry, 'assertion')"
                ),
                {"version": version_id, "entry": evidence_id},
            )
            await connection.execute(
                text(
                    "UPDATE memories SET current_version_id = :version WHERE id = :memory AND tenant_id = :tenant AND project_id = :project"
                ),
                {
                    "version": version_id,
                    "memory": memory_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                },
            )
            operation = Operation(
                operation_id, "memory.add", OperationStatus.COMPLETED, now, memory_id, now, now
            )
            await self._store_operation(connection, context, operation)
            await self._store_idempotency(
                connection, context, idempotency_key, request_hash, operation
            )
            await self._audit(connection, context, "memory.add", memory_id, now)
            return await self._get(connection, context, memory_id), operation

    async def list_current(
        self,
        context: RequestContext,
        *,
        subject_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[Memory], str | None]:
        cursor_time, cursor_id = _decode_cursor(cursor)
        conditions = [
            "m.tenant_id = :tenant",
            "m.project_id = :project",
            "m.status = 'active'",
            "s.memory_id IS NULL",
        ]
        parameters: dict[str, Any] = {
            "tenant": context.tenant_id,
            "project": context.project_id,
            "limit": limit + 1,
        }
        if subject_id is not None:
            conditions.append("m.subject_id = :subject")
            parameters["subject"] = subject_id
        if cursor_time is not None and cursor_id is not None:
            conditions.append("(m.created_at, m.id) < (:cursor_time, :cursor_id)")
            parameters.update(cursor_time=cursor_time, cursor_id=cursor_id)
        query = (
            _memory_select()
            + " WHERE "
            + " AND ".join(conditions)
            + " ORDER BY m.created_at DESC, m.id DESC LIMIT :limit"
        )
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            rows = (await connection.execute(text(query), parameters)).mappings().all()
        items = [_memory_from_row(row) for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = _encode_cursor(last.created_at, last.id)
        return items, next_cursor

    async def get(self, context: RequestContext, memory_id: UUID) -> Memory:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            return await self._get(connection, context, memory_id)

    async def history(self, context: RequestContext, memory_id: UUID) -> Sequence[MemoryVersion]:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            await self._get(connection, context, memory_id, current_only=False)
            rows = (
                (
                    await connection.execute(
                        text(
                            _version_select()
                            + " WHERE v.memory_id = :memory ORDER BY v.version DESC"
                        ),
                        {"memory": memory_id},
                    )
                )
                .mappings()
                .all()
            )
            return [_version_from_row(row) for row in rows]

    async def correct(
        self,
        context: RequestContext,
        memory_id: UUID,
        correction: Correction,
        idempotency_key: str,
    ) -> tuple[Memory, Operation]:
        request_hash = _request_hash("correct", correction, str(memory_id))
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            replay = await self._replay(connection, context, idempotency_key, request_hash)
            if replay is not None:
                return await self._get(connection, context, replay.resource_id), replay
            current = await self._get(connection, context, memory_id, lock=True)
            if (
                correction.expected_version is not None
                and correction.expected_version != current.current_version.version
            ):
                raise ConcurrentCorrectionError("the memory has a newer version")
            now = datetime.now(UTC)
            version_id, evidence_id, operation_id = uuid4(), uuid4(), uuid4()
            updated = NewMemory(
                current.subject_id,
                current.kind,
                correction.text,
                correction.structured_value,
                correction.confidence
                if correction.confidence is not None
                else current.current_version.confidence,
                correction.importance
                if correction.importance is not None
                else current.current_version.importance,
                correction.sensitivity or current.current_version.sensitivity,
                correction.valid_from,
                correction.valid_to,
                current.collection_id,
            )
            await connection.execute(
                text(
                    "INSERT INTO direct_entries (id, tenant_id, project_id, actor_id, recorded_at) VALUES (:id, :tenant, :project, :actor, :now)"
                ),
                {
                    "id": evidence_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                    "actor": context.principal_id,
                    "now": now,
                },
            )
            await self._insert_version(
                connection,
                context,
                memory_id,
                version_id,
                current.current_version.version + 1,
                updated,
                now,
                correction.reason,
            )
            await connection.execute(
                text(
                    "INSERT INTO memory_evidence (memory_version_id, direct_entry_id, evidence_role) VALUES (:version, :entry, 'correction')"
                ),
                {"version": version_id, "entry": evidence_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO memory_relations (source_version_id, target_version_id, relation_type) VALUES (:new, :old, 'supersedes')"
                ),
                {"new": version_id, "old": current.current_version.id},
            )
            await connection.execute(
                text(
                    "UPDATE memories SET current_version_id = :version, updated_at = :now WHERE id = :memory AND tenant_id = :tenant AND project_id = :project"
                ),
                {
                    "version": version_id,
                    "now": now,
                    "memory": memory_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                },
            )
            operation = Operation(
                operation_id, "memory.correct", OperationStatus.COMPLETED, now, memory_id, now, now
            )
            await self._store_operation(connection, context, operation)
            await self._store_idempotency(
                connection, context, idempotency_key, request_hash, operation
            )
            await self._audit(connection, context, "memory.correct", memory_id, now)
            return await self._get(connection, context, memory_id), operation

    async def suppress(
        self, context: RequestContext, memory_id: UUID, idempotency_key: str
    ) -> Operation:
        request_hash = _request_hash("suppress", str(memory_id))
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            replay = await self._replay(connection, context, idempotency_key, request_hash)
            if replay is not None:
                return replay
            await self._get(connection, context, memory_id, lock=True)
            now, operation_id = datetime.now(UTC), uuid4()
            await connection.execute(
                text(
                    "INSERT INTO suppression_markers (id, tenant_id, project_id, memory_id, created_at, actor_id) VALUES (:id, :tenant, :project, :memory, :now, :actor) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": uuid4(),
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                    "memory": memory_id,
                    "now": now,
                    "actor": context.principal_id,
                },
            )
            await connection.execute(
                text(
                    "UPDATE memories SET status = 'deleted', updated_at = :now WHERE id = :memory AND tenant_id = :tenant AND project_id = :project"
                ),
                {
                    "now": now,
                    "memory": memory_id,
                    "tenant": context.tenant_id,
                    "project": context.project_id,
                },
            )
            operation = Operation(
                operation_id, "memory.erase", OperationStatus.ACCEPTED, now, memory_id, now
            )
            await self._store_operation(connection, context, operation)
            await self._store_idempotency(
                connection, context, idempotency_key, request_hash, operation
            )
            await self._audit(connection, context, "memory.suppress", memory_id, now)
            return operation

    async def get_operation(self, context: RequestContext, operation_id: UUID) -> Operation:
        async with self._engine.begin() as connection:
            await set_trusted_scope(connection, context)
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM operations WHERE id = :id AND tenant_id = :tenant AND project_id = :project"
                        ),
                        {
                            "id": operation_id,
                            "tenant": context.tenant_id,
                            "project": context.project_id,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise MemoryNotFoundError("operation not found")
        return _operation_from_row(row)

    async def close(self) -> None:
        await self._engine.dispose()

    async def _get(
        self,
        connection: AsyncConnection,
        context: RequestContext,
        memory_id: UUID | None,
        *,
        current_only: bool = True,
        lock: bool = False,
    ) -> Memory:
        if memory_id is None:
            raise MemoryNotFoundError("memory not found")
        conditions = "m.id = :id AND m.tenant_id = :tenant AND m.project_id = :project AND s.memory_id IS NULL"
        if current_only:
            conditions += " AND m.status = 'active'"
        suffix = " FOR UPDATE OF m" if lock else ""
        row = (
            (
                await connection.execute(
                    text(_memory_select() + " WHERE " + conditions + suffix),
                    {"id": memory_id, "tenant": context.tenant_id, "project": context.project_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise MemoryNotFoundError("memory not found")
        return _memory_from_row(row)

    async def _ensure_subject(
        self, connection: AsyncConnection, context: RequestContext, subject_id: UUID
    ) -> None:
        found = await connection.scalar(
            text(
                "SELECT 1 FROM subjects WHERE id = :id AND tenant_id = :tenant AND project_id = :project"
            ),
            {"id": subject_id, "tenant": context.tenant_id, "project": context.project_id},
        )
        if found is None:
            raise MemoryNotFoundError("subject not found")

    async def _ensure_collection(
        self, connection: AsyncConnection, context: RequestContext, collection_id: UUID
    ) -> None:
        found = await connection.scalar(
            text(
                "SELECT 1 FROM collections WHERE id = :id AND tenant_id = :tenant AND project_id = :project"
            ),
            {"id": collection_id, "tenant": context.tenant_id, "project": context.project_id},
        )
        if found is None:
            raise MemoryNotFoundError("collection not found")

    async def _insert_version(
        self,
        connection: AsyncConnection,
        context: RequestContext,
        memory_id: UUID,
        version_id: UUID,
        version: int,
        command: NewMemory,
        now: datetime,
        reason: str,
    ) -> None:
        await connection.execute(
            text(
                "INSERT INTO memory_versions (id, memory_id, version, text, structured_value, confidence, importance, sensitivity, valid_from, valid_to, recorded_at, actor_id, reason) VALUES (:id, :memory, :version, :text, CAST(:value AS jsonb), :confidence, :importance, :sensitivity, :valid_from, :valid_to, :recorded_at, :actor, :reason)"
            ),
            {
                "id": version_id,
                "memory": memory_id,
                "version": version,
                "text": command.text,
                "value": json.dumps(command.structured_value)
                if command.structured_value is not None
                else None,
                "confidence": command.confidence,
                "importance": command.importance,
                "sensitivity": command.sensitivity.value,
                "valid_from": command.valid_from,
                "valid_to": command.valid_to,
                "recorded_at": now,
                "actor": context.principal_id,
                "reason": reason,
            },
        )

    async def _store_operation(
        self, connection: AsyncConnection, context: RequestContext, operation: Operation
    ) -> None:
        await connection.execute(
            text(
                "INSERT INTO operations (id, tenant_id, project_id, operation_type, resource_id, status, accepted_at, committed_at, completed_at, failure_code, retryable) VALUES (:id, :tenant, :project, :type, :resource, :status, :accepted, :committed, :completed, :failure, :retryable)"
            ),
            {
                "id": operation.id,
                "tenant": context.tenant_id,
                "project": context.project_id,
                "type": operation.operation_type,
                "resource": operation.resource_id,
                "status": operation.status.value,
                "accepted": operation.accepted_at,
                "committed": operation.committed_at,
                "completed": operation.completed_at,
                "failure": operation.failure_code,
                "retryable": operation.retryable,
            },
        )

    async def _store_idempotency(
        self,
        connection: AsyncConnection,
        context: RequestContext,
        key: str,
        request_hash: str,
        operation: Operation,
    ) -> None:
        await connection.execute(
            text(
                "INSERT INTO idempotency_records (id, tenant_id, project_id, idempotency_key, operation_type, request_hash, operation_id, resource_id) VALUES (:id, :tenant, :project, :key, :type, :hash, :operation, :resource)"
            ),
            {
                "id": uuid4(),
                "tenant": context.tenant_id,
                "project": context.project_id,
                "key": key,
                "type": operation.operation_type,
                "hash": request_hash,
                "operation": operation.id,
                "resource": operation.resource_id,
            },
        )

    async def _replay(
        self, connection: AsyncConnection, context: RequestContext, key: str, request_hash: str
    ) -> Operation | None:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT i.request_hash, o.* FROM idempotency_records i JOIN operations o ON o.id = i.operation_id WHERE i.tenant_id = :tenant AND i.project_id = :project AND i.idempotency_key = :key"
                    ),
                    {"tenant": context.tenant_id, "project": context.project_id, "key": key},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise ValueError("Idempotency-Key was already used with a different request")
        return _operation_from_row(row)

    async def _audit(
        self,
        connection: AsyncConnection,
        context: RequestContext,
        action: str,
        resource_id: UUID,
        now: datetime,
    ) -> None:
        await connection.execute(
            text(
                "INSERT INTO audit_events (id, tenant_id, project_id, principal_id, action, resource_type, resource_id, occurred_at) VALUES (:id, :tenant, :project, :principal, :action, 'memory', :resource, :now)"
            ),
            {
                "id": uuid4(),
                "tenant": context.tenant_id,
                "project": context.project_id,
                "principal": context.principal_id,
                "action": action,
                "resource": resource_id,
                "now": now,
            },
        )


def _memory_select() -> str:
    return "SELECT m.*, v.version, v.text, v.structured_value, v.confidence, v.importance, v.sensitivity, v.valid_from, v.valid_to, v.recorded_at, v.actor_id, v.reason, d.id AS evidence_id, d.actor_id AS evidence_actor_id, d.recorded_at AS evidence_recorded_at FROM memories m JOIN memory_versions v ON v.id = m.current_version_id JOIN memory_evidence e ON e.memory_version_id = v.id LEFT JOIN direct_entries d ON d.id = e.direct_entry_id LEFT JOIN suppression_markers s ON s.memory_id = m.id AND s.tenant_id = m.tenant_id AND s.project_id = m.project_id"


def _version_select() -> str:
    return "SELECT v.*, d.id AS evidence_id, d.actor_id AS evidence_actor_id, d.recorded_at AS evidence_recorded_at FROM memory_versions v JOIN memory_evidence e ON e.memory_version_id = v.id LEFT JOIN direct_entries d ON d.id = e.direct_entry_id"


def _memory_from_row(row: RowMapping) -> Memory:
    return Memory(
        row["id"],
        row["tenant_id"],
        row["project_id"],
        row["subject_id"],
        MemoryKind(row["kind"]),
        ProvenanceMode(row["provenance_mode"]),
        MemoryStatus(row["status"]),
        _version_from_row(row),
        row["created_at"],
        row["updated_at"],
        row["collection_id"],
    )


def _version_from_row(row: RowMapping) -> MemoryVersion:
    evidence = (
        DirectEvidence(row["evidence_id"], row["evidence_actor_id"], row["evidence_recorded_at"])
        if row["evidence_id"] is not None
        else None
    )
    return MemoryVersion(
        row["current_version_id"] if "current_version_id" in row else row["id"],
        row["id"] if "current_version_id" in row else row["memory_id"],
        row["version"],
        row["text"],
        row["structured_value"],
        row["confidence"],
        row["importance"],
        Sensitivity(row["sensitivity"]),
        row["recorded_at"],
        row["actor_id"],
        row["reason"],
        row["valid_from"],
        row["valid_to"],
        evidence,
    )


def _operation_from_row(row: RowMapping) -> Operation:
    return Operation(
        row["id"],
        row["operation_type"],
        OperationStatus(row["status"]),
        row["accepted_at"],
        row["resource_id"],
        row["committed_at"],
        row["completed_at"],
        row["failure_code"],
        row["retryable"],
    )


def _request_hash(*values: object) -> str:
    return hashlib.sha256(repr(values).encode()).hexdigest()


def _encode_cursor(created_at: datetime, identifier: UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{identifier}".encode()).decode()


def _decode_cursor(cursor: str | None) -> tuple[datetime | None, UUID | None]:
    if cursor is None:
        return None, None
    try:
        value = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp, identifier = value.rsplit("|", 1)
        return datetime.fromisoformat(timestamp), UUID(identifier)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("invalid cursor") from error
