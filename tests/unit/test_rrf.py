from uuid import uuid4

import pytest
from memory_retrieval import Candidate
from memory_retrieval.fusion import reciprocal_rank_fusion


def test_rrf_combines_incomparable_candidate_scores_by_rank() -> None:
    shared, lexical_only = uuid4(), uuid4()
    shared_version, lexical_version = uuid4(), uuid4()
    lexical = (
        Candidate(lexical_only, lexical_version, 1, 999.0),
        Candidate(shared, shared_version, 2, 0.1),
    )
    semantic = (Candidate(shared, shared_version, 1, -12.0),)

    fused = reciprocal_rank_fusion(lexical, semantic)

    assert fused[0].memory_id == shared
    assert fused[0].lexical_rank == 2
    assert fused[0].semantic_rank == 1


def test_rrf_rejects_non_positive_rank_constant() -> None:
    with pytest.raises(ValueError, match="positive"):
        reciprocal_rank_fusion((), (), rank_constant=0)
