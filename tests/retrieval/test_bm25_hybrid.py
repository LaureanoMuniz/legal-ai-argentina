from pathlib import Path

import pytest

from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.retrieval.fusion import convex, dedupe_by_article, rrf
from legal_ai.retrieval.retriever import Retriever, parse_mode
from legal_ai.retrieval.types import Candidate
from tests.test_pipeline_api import indexed


def cand(chunk: str, article: str, rank: int, retriever: str = "vector") -> Candidate:
    return Candidate(
        chunk_id=chunk,
        version_id=chunk.split("#")[0],
        article_id=article,
        document_id=1,
        score=1.0 / rank,
        rank=rank,
        retriever=retriever,
        context_prefix="",
        text="",
    )


def test_rrf_rewards_chunks_present_in_both_lists():
    dense = [cand("a#0", "a", 1), cand("b#0", "b", 2), cand("c#0", "c", 3)]
    sparse = [cand("c#0", "c", 1, "bm25"), cand("d#0", "d", 2, "bm25"), cand("b#0", "b", 3, "bm25")]
    fused = rrf([dense, sparse], k=3)
    assert [c.chunk_id for c in fused] == ["c#0", "b#0", "a#0"]
    assert fused[0].retriever == "rrf" and fused[0].rank == 1
    assert fused[0].score == pytest.approx(1 / 63 + 1 / 61)


def test_rrf_is_deterministic_on_ties():
    a = [cand("x#0", "x", 1)]
    b = [cand("y#0", "y", 1, "bm25")]
    assert [c.chunk_id for c in rrf([a, b], k=2)] == ["x#0", "y#0"]


def test_convex_weights_normalized_scores():
    dense = [cand("a#0", "a", 1), cand("b#0", "b", 2), cand("c#0", "c", 3)]
    sparse = [cand("c#0", "c", 1, "bm25"), cand("d#0", "d", 2, "bm25")]
    fused = convex(dense, sparse, k=4, alpha=0.8)
    assert fused[0].chunk_id == "a#0" and fused[0].score == pytest.approx(0.8)
    assert {fused[1].chunk_id, fused[2].chunk_id} == {"b#0", "c#0"}
    assert fused[1].score == pytest.approx(0.2) and fused[2].score == pytest.approx(0.2)
    assert fused[3].chunk_id == "d#0" and fused[3].score == pytest.approx(0.0)
    assert all(c.retriever == "hybrid" for c in fused) and [c.rank for c in fused] == [1, 2, 3, 4]
    only_dense = convex(dense, [], k=2, alpha=0.8)
    assert [c.chunk_id for c in only_dense] == ["a#0", "b#0"]
    assert convex([], [], k=2, alpha=0.8) == []


def test_dedupe_by_article_keeps_first_and_cuts_at_k():
    cands = [cand("a#0", "a", 1), cand("a#1", "a", 2), cand("b#0", "b", 3), cand("c#0", "c", 4)]
    out = dedupe_by_article(cands, k=2)
    assert [c.chunk_id for c in out] == ["a#0", "b#0"] and [c.rank for c in out] == [1, 2]


def test_parse_mode_rejects_unknown():
    assert parse_mode("hybrid") == "hybrid"
    with pytest.raises(ValueError, match="desconocido"):
        parse_mode("magic")


def test_bm25_and_hybrid_search_on_mini_corpus(db, tmp_path: Path):
    indexed(db, tmp_path)
    bm25 = Retriever(db, HashingEmbedder(), mode="bm25")
    bm25.require_index()
    hits = bm25.search("período de prueba", 3)
    assert hits and hits[0].retriever == "bm25" and hits[0].score > 0
    assert "25552:92bis" in [h.article_id for h in hits]
    assert bm25.name == "bm25"

    hybrid = Retriever(db, HashingEmbedder(), mode="hybrid")
    fused = hybrid.search("período de prueba", 3)
    assert len(fused) == 3 and all(c.retriever == "hybrid" for c in fused)
    assert [c.rank for c in fused] == [1, 2, 3]
    assert hybrid.name == "hybrid(a=0.8,hashing-1024)"
    ranked = Retriever(db, HashingEmbedder(), mode="rrf").search("período de prueba", 3)
    assert len(ranked) == 3 and all(c.retriever == "rrf" for c in ranked)

    deduped = Retriever(db, HashingEmbedder(), mode="vector", dedupe=True).search("prueba", 3)
    assert len({c.article_id for c in deduped}) == len(deduped)


def test_bm25_returns_empty_when_no_term_matches(db, tmp_path: Path):
    indexed(db, tmp_path)
    assert Retriever(db, HashingEmbedder(), mode="bm25").search("zzzzqqqq", 3) == []


def test_quota_merge_reserves_slots_for_each_subquery():
    from legal_ai.retrieval.fusion import quota_merge

    main = [cand(f"m{i}#0", f"m{i}", i + 1) for i in range(8)]
    subs = [[cand("s1#0", "s1", 1), cand("m0#0", "m0", 2)], [cand("s2#0", "s2", 1)]]
    out = quota_merge(main, subs, k=8, per=2)
    ids = [c.article_id for c in out]
    assert ids[:4] == ["m0", "m1", "m2", "m3"]
    assert ids[4:6] == ["s1", "s2"]
    assert "s1" in ids and "s2" in ids and len(ids) == 8 and len(set(ids)) == 8
    assert [c.rank for c in out] == list(range(1, 9))
    assert quota_merge(main, [], k=3, per=2) == list(main[:3])
