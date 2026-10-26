from uuid import UUID

from memory_retrieval.candidates import QueryPlan, SearchFilters


def build_query_plan(query: str, subject_id: UUID, filters: SearchFilters, top_k: int) -> QueryPlan:
    normalized = " ".join(query.split())
    if not normalized:
        raise ValueError("query must not be empty")
    if not 1 <= top_k <= 100:
        raise ValueError("top_k must be between 1 and 100")
    return QueryPlan(normalized, subject_id, filters, top_k, min(200, max(top_k * 4, 20)))
