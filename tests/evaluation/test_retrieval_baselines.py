from uuid import uuid4

from memory_retrieval import Candidate
from memory_retrieval.fusion import reciprocal_rank_fusion


def test_hybrid_fixture_improves_recall_without_losing_single_channel_hits() -> None:
    relevant = [uuid4() for _ in range(3)]
    versions = [uuid4() for _ in relevant]
    lexical = (
        Candidate(relevant[0], versions[0], 1, 0.9),
        Candidate(relevant[1], versions[1], 2, 0.5),
    )
    semantic = (
        Candidate(relevant[2], versions[2], 1, 0.8),
        Candidate(relevant[0], versions[0], 2, 0.7),
    )

    hybrid = reciprocal_rank_fusion(lexical, semantic)

    assert {item.memory_id for item in hybrid} == set(relevant)
    assert hybrid[0].memory_id == relevant[0]
