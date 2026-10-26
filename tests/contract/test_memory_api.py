from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from memory_api import create_app
from memory_application.ports import Correction, NewMemory
from memory_domain import (
    ComponentStatus,
    DirectEvidence,
    HealthReport,
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
from memory_retrieval import RankedMemory, RetrievalService, RetrievalStatus, SearchResult


class ReadyProbe:
    async def check(self) -> HealthReport:
        return HealthReport(ComponentStatus.READY, {"database": ComponentStatus.READY})


class FakeIdentity:
    def __init__(self, context: RequestContext) -> None:
        self.context = context

    async def authenticate(self, api_key: str) -> RequestContext:
        if api_key != "valid-key":
            from memory_domain import AuthorizationError

            raise AuthorizationError("invalid API key")
        return self.context


class InMemoryRepository:
    def __init__(self) -> None:
        self.memories: dict[UUID, Memory] = {}
        self.versions: dict[UUID, list[MemoryVersion]] = {}
        self.operations: dict[UUID, Operation] = {}

    async def add(
        self, context: RequestContext, command: NewMemory, idempotency_key: str
    ) -> tuple[Memory, Operation]:
        now, memory_id, version_id = datetime.now(UTC), uuid4(), uuid4()
        version = MemoryVersion(
            version_id,
            memory_id,
            1,
            command.text,
            command.structured_value,
            command.confidence,
            command.importance,
            command.sensitivity,
            now,
            context.principal_id,
            "explicit_add",
            command.valid_from,
            command.valid_to,
            DirectEvidence(uuid4(), context.principal_id, now),
        )
        memory = Memory(
            memory_id,
            context.tenant_id,
            context.project_id,
            command.subject_id,
            command.kind,
            ProvenanceMode.EXPLICIT,
            MemoryStatus.ACTIVE,
            version,
            now,
            now,
            command.collection_id,
        )
        operation = Operation(
            uuid4(), "memory.add", OperationStatus.COMPLETED, now, memory_id, now, now
        )
        self.memories[memory_id] = memory
        self.versions[memory_id] = [version]
        self.operations[operation.id] = operation
        return memory, operation

    async def list_current(
        self,
        context: RequestContext,
        *,
        subject_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[Memory], str | None]:
        items = [
            memory
            for memory in self.memories.values()
            if memory.status is MemoryStatus.ACTIVE
            and memory.tenant_id == context.tenant_id
            and memory.project_id == context.project_id
            and (subject_id is None or memory.subject_id == subject_id)
        ]
        return items[:limit], None

    async def get(self, context: RequestContext, memory_id: UUID) -> Memory:
        memory = self.memories.get(memory_id)
        if memory is None or memory.status is not MemoryStatus.ACTIVE:
            raise MemoryNotFoundError("memory not found")
        return memory

    async def history(self, context: RequestContext, memory_id: UUID) -> Sequence[MemoryVersion]:
        await self.get(context, memory_id)
        return list(reversed(self.versions[memory_id]))

    async def correct(
        self,
        context: RequestContext,
        memory_id: UUID,
        correction: Correction,
        idempotency_key: str,
    ) -> tuple[Memory, Operation]:
        current = await self.get(context, memory_id)
        now = datetime.now(UTC)
        version = MemoryVersion(
            uuid4(),
            memory_id,
            current.current_version.version + 1,
            correction.text,
            correction.structured_value,
            correction.confidence or current.current_version.confidence,
            correction.importance or current.current_version.importance,
            correction.sensitivity or current.current_version.sensitivity,
            now,
            context.principal_id,
            correction.reason,
            correction.valid_from,
            correction.valid_to,
            DirectEvidence(uuid4(), context.principal_id, now),
        )
        memory = Memory(
            current.id,
            current.tenant_id,
            current.project_id,
            current.subject_id,
            current.kind,
            current.provenance_mode,
            current.status,
            version,
            current.created_at,
            now,
            current.collection_id,
        )
        self.memories[memory_id] = memory
        self.versions[memory_id].append(version)
        operation = Operation(
            uuid4(), "memory.correct", OperationStatus.COMPLETED, now, memory_id, now, now
        )
        self.operations[operation.id] = operation
        return memory, operation

    async def suppress(
        self, context: RequestContext, memory_id: UUID, idempotency_key: str
    ) -> Operation:
        current = await self.get(context, memory_id)
        self.memories[memory_id] = Memory(
            current.id,
            current.tenant_id,
            current.project_id,
            current.subject_id,
            current.kind,
            current.provenance_mode,
            MemoryStatus.DELETED,
            current.current_version,
            current.created_at,
            datetime.now(UTC),
            current.collection_id,
        )
        operation = Operation(
            uuid4(),
            "memory.erase",
            OperationStatus.ACCEPTED,
            datetime.now(UTC),
            memory_id,
            datetime.now(UTC),
        )
        self.operations[operation.id] = operation
        return operation

    async def get_operation(self, context: RequestContext, operation_id: UUID) -> Operation:
        return self.operations[operation_id]

    async def close(self) -> None:
        return None


class FakeRetrieval:
    def __init__(self, result: SearchResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def search(self, context: RequestContext, **kwargs: object) -> SearchResult:
        self.calls.append({"context": context, **kwargs})
        return self.result


def retrieval_memory(context: RequestContext, subject_id: UUID, text: str) -> Memory:
    now, memory_id = datetime.now(UTC), uuid4()
    version = MemoryVersion(
        uuid4(),
        memory_id,
        1,
        text,
        None,
        0.9,
        0.8,
        Sensitivity.GENERAL,
        now,
        context.principal_id,
        "test",
    )
    return Memory(
        memory_id,
        context.tenant_id,
        context.project_id,
        subject_id,
        MemoryKind.PREFERENCE,
        ProvenanceMode.EXPLICIT,
        MemoryStatus.ACTIVE,
        version,
        now,
        now,
    )


def test_explicit_memory_contract_preserves_history_and_suppresses() -> None:
    context = RequestContext(uuid4(), uuid4(), uuid4())
    repository = InMemoryRepository()
    app = create_app(ReadyProbe(), repository, FakeIdentity(context))
    headers = {"Authorization": "Bearer valid-key", "Idempotency-Key": "add-1"}
    subject_id = uuid4()

    with TestClient(app) as client:
        added = client.post(
            "/v1/memories",
            headers=headers,
            json={"subject_id": str(subject_id), "kind": "preference", "text": "Tea"},
        )
        assert added.status_code == 201
        body = added.json()
        memory_id = body["memory"]["id"]
        assert body["memory"]["provenance_mode"] == "explicit"
        assert len(body["memory"]["current_version"]["evidence"]) == 1

        corrected = client.patch(
            f"/v1/memories/{memory_id}",
            headers={**headers, "Idempotency-Key": "correct-1"},
            json={"text": "Coffee", "reason": "user correction", "expected_version": 1},
        )
        assert corrected.json()["memory"]["current_version"]["version"] == 2
        history = client.get(
            f"/v1/memories/{memory_id}/history",
            headers={"Authorization": "Bearer valid-key"},
        )
        assert [item["text"] for item in history.json()["items"]] == ["Coffee", "Tea"]

        deleted = client.delete(
            f"/v1/memories/{memory_id}",
            headers={**headers, "Idempotency-Key": "delete-1"},
        )
        assert deleted.status_code == 202
        assert deleted.json()["operation"]["status"] == "accepted"
        assert (
            client.get(
                f"/v1/memories/{memory_id}", headers={"Authorization": "Bearer valid-key"}
            ).status_code
            == 404
        )


def test_memory_routes_require_bearer_authentication() -> None:
    context = RequestContext(uuid4(), uuid4(), uuid4())
    app = create_app(ReadyProbe(), InMemoryRepository(), FakeIdentity(context))
    with TestClient(app) as client:
        response = client.get("/v1/memories")
    assert response.status_code == 422


def test_search_and_context_contracts_expose_ranks_status_and_recent_context() -> None:
    context, subject_id = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    memory = retrieval_memory(context, subject_id, "The user prefers tea")
    result = SearchResult((RankedMemory(memory, 0.75, 1, 2),), RetrievalStatus.COMPLETE)
    retrieval = FakeRetrieval(result)
    app = create_app(
        ReadyProbe(),
        InMemoryRepository(),
        FakeIdentity(context),
        cast(RetrievalService, retrieval),
    )
    headers = {"Authorization": "Bearer valid-key"}

    with TestClient(app) as client:
        searched = client.post(
            "/v1/memories/search",
            headers=headers,
            json={"query": "drink", "subject_id": str(subject_id), "top_k": 5},
        )
        compiled = client.post(
            "/v1/context/compile",
            headers=headers,
            json={
                "query": "drink",
                "subject_id": str(subject_id),
                "top_k": 5,
                "total_budget": 100,
                "reserved_instruction_tokens": 10,
                "recent_context": ["The user asked for a recommendation"],
            },
        )

    assert searched.status_code == 200
    assert searched.json()["status"] == "complete"
    assert searched.json()["items"][0]["rank"] == {
        "lexical_rank": 1,
        "semantic_rank": 2,
        "score": 0.75,
        "rank_policy": "deterministic-v1",
    }
    assert compiled.status_code == 200
    assert compiled.json()["retrieval_status"] == "complete"
    assert compiled.json()["rendered"].startswith(
        "Recent context:\n- The user asked for a recommendation\n\nRelevant memories:"
    )
    assert compiled.json()["used_tokens"] <= 90
    assert len(retrieval.calls) == 2


def test_context_contract_rejects_recent_context_outside_budget() -> None:
    context, subject_id = RequestContext(uuid4(), uuid4(), uuid4()), uuid4()
    retrieval = FakeRetrieval(SearchResult((), RetrievalStatus.COMPLETE))
    app = create_app(
        ReadyProbe(),
        InMemoryRepository(),
        FakeIdentity(context),
        cast(RetrievalService, retrieval),
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/v1/context/compile",
            headers={"Authorization": "Bearer valid-key"},
            json={
                "query": "drink",
                "subject_id": str(subject_id),
                "total_budget": 4,
                "recent_context": ["This cannot fit in four tokens"],
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
