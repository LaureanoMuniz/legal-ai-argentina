from pathlib import Path

from sqlalchemy import func, select

from legal_ai.db.schema import chunks
from legal_ai.index.embed import build_corpus_chunks, embed_chunks
from legal_ai.index.embeddings import EmbeddingCache, HashingEmbedder
from legal_ai.index.load import load_corpus
from tests.index.test_load import parsed_corpus


def test_chunk_and_embed_corpus(db, tmp_path: Path):
    processed = parsed_corpus(tmp_path)
    load_corpus(db, processed, "mini")
    report = build_corpus_chunks(db, "mini")
    assert report.chunks >= 270 and report.articles_with_chunks >= 270
    again = build_corpus_chunks(db, "mini")
    assert again.chunks == report.chunks

    cache = EmbeddingCache(tmp_path / "emb.npz")
    embedded = embed_chunks(db, HashingEmbedder(), cache, "mini")
    assert embedded.embedded == report.chunks and embedded.cached == 0
    second = embed_chunks(db, HashingEmbedder(), cache, "mini")
    assert second.embedded == 0
    with db.connect() as conn:
        missing = conn.execute(
            select(func.count()).select_from(chunks).where(chunks.c.embedding.is_(None))
        ).scalar()
        assert missing == 0
        row = (
            conn.execute(select(chunks).where(chunks.c.id == "25552:92bis@current#0"))
            .mappings()
            .one()
        )
        assert (
            row["context_prefix"].startswith("Ley 20744")
            and "Art. 92 bis — Período de prueba" in row["context_prefix"]
        )
        assert row["embedding_model"] == "hashing-1024"
        derogated = conn.execute(
            select(func.count())
            .select_from(chunks)
            .where(chunks.c.version_id == "25552:28@current")
        ).scalar()
        assert derogated == 0
