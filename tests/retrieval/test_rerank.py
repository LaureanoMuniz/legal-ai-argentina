from pathlib import Path

import pytest

from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.retrieval.rerank import OverlapReranker, get_reranker, rerank
from legal_ai.retrieval.retriever import Retriever
from legal_ai.retrieval.types import Candidate
from tests.test_pipeline_api import indexed


def cand(chunk: str, rank: int, text: str) -> Candidate:
    return Candidate(
        chunk_id=chunk,
        version_id=chunk,
        article_id=chunk,
        document_id=1,
        score=1.0 / rank,
        rank=rank,
        retriever="vector",
        context_prefix="",
        text=text,
    )


def test_rerank_reorders_by_score_and_keeps_rank_as_tiebreak():
    pool = [
        cand("a", 1, "nada que ver"),
        cand("b", 2, "renuncia derechos nulidad"),
        cand("c", 3, "derechos"),
    ]
    out = rerank(OverlapReranker(), "renuncia a los derechos del trabajador", pool, k=2)
    assert [c.chunk_id for c in out] == ["b", "c"]
    assert [c.rank for c in out] == [1, 2] and out[0].retriever == "vector+rerank"
    assert out[0].score > out[1].score
    assert rerank(OverlapReranker(), "q", [], 3) == []


def test_get_reranker_rejects_unknown():
    assert get_reranker("overlap").name == "overlap"
    with pytest.raises(ValueError, match="desconocido"):
        get_reranker("nope")


def test_retriever_reranks_over_pool(db, tmp_path: Path):
    indexed(db, tmp_path)
    r = Retriever(db, HashingEmbedder(), mode="vector", reranker=OverlapReranker(), pool=10)
    out = r.search("período de prueba seis meses", 3)
    assert len(out) == 3 and [c.rank for c in out] == [1, 2, 3]
    assert all(c.retriever == "vector+rerank" for c in out)
    assert r.name == "vector(hashing-1024)+rerank(overlap,pool=10)"
