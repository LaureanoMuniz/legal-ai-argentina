from sqlalchemy import text
from sqlalchemy.engine import Connection

from legal_ai.retrieval.types import Candidate

VECTOR_SQL = """
SELECT id, version_id, article_id, document_id, context_prefix, text,
       1 - (embedding <=> CAST(:q AS vector)) AS score
FROM chunks
WHERE embedding IS NOT NULL AND embedding_model = :model
ORDER BY embedding <=> CAST(:q AS vector)
LIMIT :k
"""


COUNT_SQL = "SELECT count(*) FROM chunks WHERE embedding IS NOT NULL AND embedding_model = :model"


def count_embedded(conn: Connection, model: str) -> int:
    return int(conn.execute(text(COUNT_SQL), {"model": model}).scalar() or 0)


def retrieve_vector(
    conn: Connection, query_vector: list[float], k: int, model: str
) -> list[Candidate]:
    literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
    rows = conn.execute(text(VECTOR_SQL), {"q": literal, "k": k, "model": model}).mappings()
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
        )
        for index, row in enumerate(rows)
    ]
