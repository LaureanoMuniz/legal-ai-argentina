from collections import defaultdict
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine

from legal_ai.db.schema import article_versions, articles, chunks, documents
from legal_ai.index.chunking import build_chunks
from legal_ai.index.embeddings import Embedder, EmbeddingCache, embed_with_cache

BATCH = 64


class ChunkReport(BaseModel):
    corpus: str
    chunks: int
    articles_with_chunks: int
    skipped_articles: int


class EmbedReport(BaseModel):
    corpus: str
    embedded: int
    cached: int
    model: str


def build_corpus_chunks(engine: Engine, corpus: str) -> ChunkReport:
    with engine.begin() as conn:
        docs = {
            r["id_norma"]: dict(r)
            for r in conn.execute(select(documents).where(documents.c.corpus == corpus)).mappings()
        }
        if docs:
            conn.execute(delete(chunks).where(chunks.c.document_id.in_(list(docs))))
        arts = [
            dict(r)
            for r in conn.execute(
                select(articles).where(articles.c.document_id.in_(list(docs)))
            ).mappings()
        ]
        versions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in conn.execute(
            select(article_versions).where(article_versions.c.document_id.in_(list(docs)))
        ).mappings():
            versions[row["article_id"]].append(dict(row))
        rows: list[dict[str, Any]] = []
        with_chunks = 0
        for art in arts:
            records = build_chunks(docs[art["document_id"]], art, versions.get(art["id"], []))
            if records:
                with_chunks += 1
            rows.extend(r.model_dump() for r in records)
        for start in range(0, len(rows), 1000):
            conn.execute(chunks.insert(), rows[start : start + 1000])
    return ChunkReport(
        corpus=corpus,
        chunks=len(rows),
        articles_with_chunks=with_chunks,
        skipped_articles=len(arts) - with_chunks,
    )


def embed_chunks(
    engine: Engine, embedder: Embedder, cache: EmbeddingCache, corpus: str, limit: int | None = None
) -> EmbedReport:
    with engine.connect() as conn:
        query = (
            select(chunks.c.id, chunks.c.embed_text)
            .join(documents, documents.c.id_norma == chunks.c.document_id)
            .where(documents.c.corpus == corpus)
            .where((chunks.c.embedding.is_(None)) | (chunks.c.embedding_model != embedder.name))
            .order_by(chunks.c.id)
        )
        if limit is not None:
            query = query.limit(limit)
        pending = [(r[0], r[1]) for r in conn.execute(query)]
    hits_before = cache.hits
    embedded = 0
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        vectors = embed_with_cache(embedder, cache, [text for _, text in batch])
        with engine.begin() as conn:
            for (chunk_id, _), vector in zip(batch, vectors, strict=True):
                conn.execute(
                    update(chunks)
                    .where(chunks.c.id == chunk_id)
                    .values(embedding=vector.tolist(), embedding_model=embedder.name)
                )
        embedded += len(batch)
        cache.save()
    return EmbedReport(
        corpus=corpus, embedded=embedded, cached=cache.hits - hits_before, model=embedder.name
    )
