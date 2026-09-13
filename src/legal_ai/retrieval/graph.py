"""Graph expansion: follow article cross references from the top candidates."""

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Connection

from legal_ai.retrieval.temporal import version_filter
from legal_ai.retrieval.types import Candidate

NEIGHBOUR_SQL = """
SELECT r.source_article_id, c.id, c.version_id, c.article_id, c.document_id, c.context_prefix,
       c.text, v.status, v.effective_from, v.effective_until
FROM article_references r
JOIN chunks c ON c.article_id = r.target_article_id AND c.chunk_index = 0
JOIN article_versions v ON v.id = c.version_id
WHERE r.source_article_id = ANY(:sources) AND {version_filter}
ORDER BY r.source_article_id, c.version_id
"""


def expand_with_references(
    conn: Connection,
    candidates: list[Candidate],
    k: int,
    seeds: int = 3,
    extra: int = 3,
    as_of: date | None = None,
    historical: bool = False,
) -> list[Candidate]:
    if not candidates or extra <= 0:
        return candidates[:k]
    seed_articles: list[str] = []
    for c in candidates:
        if c.article_id not in seed_articles:
            seed_articles.append(c.article_id)
        if len(seed_articles) == seeds:
            break
    clause, params = version_filter(as_of, historical)
    rows = conn.execute(
        text(NEIGHBOUR_SQL.format(version_filter=clause)), {"sources": seed_articles, **params}
    ).mappings()
    present = {c.article_id for c in candidates}
    neighbours: list[Candidate] = []
    for row in rows:
        if row["article_id"] in present:
            continue
        present.add(row["article_id"])
        neighbours.append(
            Candidate(
                chunk_id=row["id"],
                version_id=row["version_id"],
                article_id=row["article_id"],
                document_id=row["document_id"],
                score=0.0,
                rank=0,
                retriever="graph",
                context_prefix=row["context_prefix"],
                text=row["text"],
                status=row["status"],
                effective_from=row["effective_from"],
                effective_until=row["effective_until"],
            )
        )
        if len(neighbours) == extra:
            break
    if not neighbours:
        return candidates[:k]
    merged = candidates[: max(0, k - len(neighbours))] + neighbours
    return [c.model_copy(update={"rank": i + 1}) for i, c in enumerate(merged[:k])]
