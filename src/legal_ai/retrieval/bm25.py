"""BM25 retrieval over chunks with ParadeDB pg_search."""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from legal_ai.retrieval.temporal import version_filter
from legal_ai.retrieval.types import Candidate

BM25_SQL = """
SELECT c.id, c.version_id, c.article_id, c.document_id, c.context_prefix, c.text,
       v.status, v.effective_from, v.effective_until,
       paradedb.score(c.id) AS score
FROM chunks c JOIN article_versions v ON v.id = c.version_id
WHERE c.id @@@ paradedb.match('embed_text', :q, conjunction_mode => false) AND {version_filter}
ORDER BY score DESC, c.id
LIMIT :k
"""

INDEX_EXISTS_SQL = "SELECT count(*) FROM pg_indexes WHERE indexname = 'chunks_bm25'"


def bm25_index_exists(conn: Connection) -> bool:
    return int(conn.execute(text(INDEX_EXISTS_SQL)).scalar() or 0) > 0


def retrieve_bm25(
    conn: Connection, query: str, k: int, as_of: date | None = None, historical: bool = False
) -> list[Candidate]:
    clause, params = version_filter(as_of, historical)
    sql = BM25_SQL.format(version_filter=clause)
    rows = conn.execute(text(sql), {"q": query, "k": k, **params}).mappings()
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
            status=row["status"],
            effective_from=row["effective_from"],
            effective_until=row["effective_until"],
        )
        for index, row in enumerate(rows)
    ]
