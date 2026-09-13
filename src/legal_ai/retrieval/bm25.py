"""BM25 retrieval over chunks with ParadeDB pg_search."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from legal_ai.retrieval.types import Candidate

BM25_SQL = """
SELECT id, version_id, article_id, document_id, context_prefix, text,
       paradedb.score(id) AS score
FROM chunks
WHERE id @@@ paradedb.match('embed_text', :q, conjunction_mode => false)
ORDER BY score DESC, id
LIMIT :k
"""

INDEX_EXISTS_SQL = "SELECT count(*) FROM pg_indexes WHERE indexname = 'chunks_bm25'"


def bm25_index_exists(conn: Connection) -> bool:
    return int(conn.execute(text(INDEX_EXISTS_SQL)).scalar() or 0) > 0


def retrieve_bm25(conn: Connection, query: str, k: int) -> list[Candidate]:
    rows = conn.execute(text(BM25_SQL), {"q": query, "k": k}).mappings()
    return [
        Candidate(
            chunk_id=row["id"],
            version_id=row["version_id"],
            article_id=row["article_id"],
            document_id=row["document_id"],
            score=float(row["score"]),
            rank=index + 1,
            retriever="bm25",
            context_prefix=row["context_prefix"],
            text=row["text"],
        )
        for index, row in enumerate(rows)
    ]
