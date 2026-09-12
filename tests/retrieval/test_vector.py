from pathlib import Path

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
