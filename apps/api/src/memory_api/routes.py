# ruff: noqa: E501
from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from memory_application import EpisodeService, MemoryService
from memory_domain import RequestContext
from memory_retrieval import RetrievalService, compile_context

from memory_api.schemas import (
    AddMemoryRequest,
    AppendEpisodeRequest,
    CompileContextRequest,
    ContextResponse,
    CorrectMemoryRequest,
    EpisodeMutationResponse,
    EpisodeResponse,
    HistoryResponse,
    MemoryListResponse,
    MemoryResponse,
    MutationResponse,
    OperationResponse,
    SearchRequest,
    SearchResponse,
    context_response,
    episode_response,
    memory_response,
    operation_response,
    search_response,
    version_response,
)


def create_router(
    service: MemoryService,
    authenticate: Callable[[str], Awaitable[RequestContext]],
    episode_service: EpisodeService | None = None,
    retrieval_service: RetrievalService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["memories"])

    async def context(authorization: Annotated[str, Header()]) -> RequestContext:
        scheme, _, credential = authorization.partition(" ")
        if scheme.lower() != "bearer" or not credential:
            from memory_domain import AuthorizationError

            raise AuthorizationError("Bearer authentication is required")
        return await authenticate(credential)

    TrustedContext = Annotated[RequestContext, Depends(context)]
    IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]

    if episode_service is not None:

        @router.post(
            "/episodes",
            response_model=EpisodeMutationResponse,
            status_code=status.HTTP_202_ACCEPTED,
        )
        async def append_episode(
            payload: AppendEpisodeRequest, trusted: TrustedContext, key: IdempotencyKey
        ) -> EpisodeMutationResponse:
            episode, operation = await episode_service.append(trusted, payload.to_command(), key)
            return EpisodeMutationResponse(
                episode=episode_response(episode), operation=operation_response(operation)
            )

        @router.get("/episodes/{episode_id}", response_model=EpisodeResponse)
        async def get_episode(episode_id: UUID, trusted: TrustedContext) -> EpisodeResponse:
            return episode_response(await episode_service.get(trusted, episode_id))

    @router.post("/memories", response_model=MutationResponse, status_code=status.HTTP_201_CREATED)
    async def add_memory(
        payload: AddMemoryRequest, trusted: TrustedContext, key: IdempotencyKey
    ) -> MutationResponse:
        memory, operation = await service.add(trusted, payload.to_command(), key)
        return MutationResponse(
            memory=memory_response(memory), operation=operation_response(operation)
        )

    @router.get("/memories", response_model=MemoryListResponse)
    async def list_memories(
        trusted: TrustedContext,
        subject_id: UUID | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> MemoryListResponse:
        items, next_cursor = await service.list(
            trusted, subject_id=subject_id, cursor=cursor, limit=limit
        )
        return MemoryListResponse(
            items=[memory_response(item) for item in items], next_cursor=next_cursor
        )

    if retrieval_service is not None:

        @router.post("/memories/search", response_model=SearchResponse)
        async def search_memories(
            payload: SearchRequest, trusted: TrustedContext
        ) -> SearchResponse:
            result = await retrieval_service.search(
                trusted,
                query=payload.query,
                subject_id=payload.subject_id,
                filters=payload.filters.to_filters(),
                top_k=payload.top_k,
                deadline_seconds=payload.deadline_seconds,
            )
            return search_response(result)

        @router.post("/context/compile", response_model=ContextResponse)
        async def compile_memory_context(
            payload: CompileContextRequest, trusted: TrustedContext
        ) -> ContextResponse:
            result = await retrieval_service.search(
                trusted,
                query=payload.query,
                subject_id=payload.subject_id,
                filters=payload.filters.to_filters(),
                top_k=payload.top_k,
                deadline_seconds=payload.deadline_seconds,
            )
            package = compile_context(
                result.items,
                payload.total_budget,
                payload.reserved_instruction_tokens + payload.reserved_task_tokens,
                result.status,
                tuple(payload.recent_context),
            )
            return context_response(package)

    @router.get("/memories/{memory_id}", response_model=MemoryResponse)
    async def get_memory(memory_id: UUID, trusted: TrustedContext) -> MemoryResponse:
        return memory_response(await service.get(trusted, memory_id))

    @router.get("/memories/{memory_id}/history", response_model=HistoryResponse)
    async def memory_history(memory_id: UUID, trusted: TrustedContext) -> HistoryResponse:
        return HistoryResponse(
            items=[version_response(item) for item in await service.history(trusted, memory_id)]
        )

    @router.patch("/memories/{memory_id}", response_model=MutationResponse)
    async def correct_memory(
        memory_id: UUID, payload: CorrectMemoryRequest, trusted: TrustedContext, key: IdempotencyKey
    ) -> MutationResponse:
        memory, operation = await service.correct(trusted, memory_id, payload.to_command(), key)
        return MutationResponse(
            memory=memory_response(memory), operation=operation_response(operation)
        )

    @router.delete(
        "/memories/{memory_id}",
        response_model=MutationResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def suppress_memory(
        memory_id: UUID, trusted: TrustedContext, key: IdempotencyKey
    ) -> MutationResponse:
        operation = await service.suppress(trusted, memory_id, key)
        return MutationResponse(memory=None, operation=operation_response(operation))

    @router.get("/operations/{operation_id}", response_model=OperationResponse)
    async def get_operation(operation_id: UUID, trusted: TrustedContext) -> OperationResponse:
        return operation_response(await service.operation(trusted, operation_id))

    return router
