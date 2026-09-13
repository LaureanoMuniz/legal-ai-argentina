from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from legal_ai.retrieval.temporal import version_filter
from legal_ai.retrieval.types import Candidate

VECTOR_SQL = """
SELECT c.id, c.version_id, c.article_id, c.document_id, c.context_prefix, c.text,
       v.status, v.effective_from, v.effective_until,
       1 - (c.embedding <=> CAST(:q AS vector)) AS score
FROM chunks c JOIN article_versions v ON v.id = c.version_id
WHERE c.embedding IS NOT NULL AND c.embedding_model = :model AND {version_filter}
ORDER BY c.embedding <=> CAST(:q AS vector)
LIMIT :k
"""


COUNT_SQL = "SELECT count(*) FROM chunks WHERE embedding IS NOT NULL AND embedding_model = :model"


def count_embedded(conn: Connection, model: str) -> int:
    return int(conn.execute(text(COUNT_SQL), {"model": model}).scalar() or 0)


def retrieve_vector(
    conn: Connection,
    query_vector: list[float],
    k: int,
    model: str,
    as_of: date | None = None,
    historical: bool = False,
) -> list[Candidate]:
    literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
    clause, params = version_filter(as_of, historical)
    sql = VECTOR_SQL.format(version_filter=clause)
    rows = conn.execute(text(sql), {"q": literal, "k": k, "model": model, **params}).mappings()
    return [
        Candidate(
            chunk_id=row["id"],
            version_id=row["version_id"],
            article_id=row["article_id"],
            document_id=row["document_id"],
            score=float(row["score"]),
            rank=index + 1,
            retriever="vector",
            context_prefix=row["context_prefix"],
            text=row["text"],
            status=row["status"],
            effective_from=row["effective_from"],
            effective_until=row["effective_until"],
        )
        for index, row in enumerate(rows)
    ]
