from pathlib import Path

import pytest

from legal_ai.index.embed import build_corpus_chunks, embed_chunks
from legal_ai.index.embeddings import EmbeddingCache, HashingEmbedder
from legal_ai.index.load import load_corpus
from legal_ai.retrieval.retriever import Retriever
from tests.index.test_load import parsed_corpus


def test_vector_search_returns_ranked_candidates(db, tmp_path: Path):
    load_corpus(db, parsed_corpus(tmp_path), "mini")
    build_corpus_chunks(db, "mini")
    embed_chunks(db, HashingEmbedder(), EmbeddingCache(tmp_path / "emb.npz"), "mini")

    retriever = Retriever(db, HashingEmbedder())
    results = retriever.search(
        "período de prueba del contrato de trabajo por tiempo indeterminado", k=5
    )
    assert [c.rank for c in results] == [1, 2, 3, 4, 5]
    assert results[0].score >= results[-1].score
    assert all(c.retriever == "vector" for c in results)
    assert any(c.article_id == "25552:92bis" for c in results)
    assert results[0].text and results[0].context_prefix


def test_search_only_matches_chunks_embedded_with_the_same_model(db, tmp_path: Path):
    from tests.test_pipeline_api import indexed

    indexed(db, tmp_path)
    same = Retriever(db, HashingEmbedder())
    assert same.embedded_chunks() > 0 and len(same.search("período de prueba", 3)) == 3
    other = HashingEmbedder()
    other.name = "otro-modelo"
    foreign = Retriever(db, other)
    assert foreign.embedded_chunks() == 0 and foreign.search("período de prueba", 3) == []
    with pytest.raises(RuntimeError, match="otro-modelo"):
        foreign.require_index()


def test_temporal_filter_selects_versions_by_date(db, tmp_path: Path):
    from datetime import date

    from tests.test_pipeline_api import indexed

    indexed(db, tmp_path)
    r = Retriever(db, HashingEmbedder())
    current = r.search("período de prueba", 8)
    assert current and all(c.effective_until is None for c in current)
    old = r.search("período de prueba", 8, as_of=date(2000, 1, 1))
    assert old and all(
        c.effective_from is not None and c.effective_from <= date(2000, 1, 1) for c in old
    )
    assert all(c.effective_until is None or c.effective_until > date(2000, 1, 1) for c in old)
    everything = r.search("período de prueba", 8, historical=True)
    assert len(everything) == 8
    plan = r.plan("¿qué decía?", None, True)
    assert plan.historical is True and plan.rewritten is None
