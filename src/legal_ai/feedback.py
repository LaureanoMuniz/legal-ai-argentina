"""Human labels: read what reviewers marked and turn it into benchmark cases."""

from collections import Counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

LIST_SQL = """
SELECT id, created_at, trace_id, conversation_id, question, answer, label, comment, reviewer,
       sources, expected_articles, retrieved_articles, as_of, historical
FROM feedback
WHERE (CAST(:label AS VARCHAR) IS NULL OR label = :label)
ORDER BY id DESC
LIMIT :limit
"""
STATS_SQL = "SELECT label, count(*) AS n FROM feedback GROUP BY label ORDER BY n DESC"
REVIEWER_SQL = """
SELECT coalesce(reviewer, '(anónimo)') AS reviewer, count(*) AS n
FROM feedback GROUP BY 1 ORDER BY n DESC
"""

GOOD = {"correct", "partially_correct"}


def read_feedback(
    engine: Engine, limit: int = 200, label: str | None = None
) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text(LIST_SQL), {"limit": limit, "label": label}).mappings()
        return [dict(r) for r in rows]


def feedback_summary(engine: Engine) -> dict[str, Any]:
    with engine.connect() as conn:
        by_label = {r["label"]: r["n"] for r in conn.execute(text(STATS_SQL)).mappings()}
        by_reviewer = {r["reviewer"]: r["n"] for r in conn.execute(text(REVIEWER_SQL)).mappings()}
    total = sum(by_label.values())
    good = sum(n for label, n in by_label.items() if label in GOOD)
    return {
        "total": total,
        "by_label": by_label,
        "by_reviewer": by_reviewer,
        "satisfaction": good / total if total else None,
    }


def feedback_to_labels(engine: Engine) -> list[dict[str, Any]]:
    """One JSON line per labelled answer, shaped like eval/benchmark.jsonl plus the verdict."""
    out: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for row in reversed(read_feedback(engine, limit=10_000)):
        question = (row["question"] or "").strip()
        if not question:
            continue
        seen[question] += 1
        suffix = f"-{seen[question]}" if seen[question] > 1 else ""
        out.append(
            {
                "id": f"h{row['id']}{suffix}",
                "category": "human",
                "question": question,
                "expected_articles": row["expected_articles"] or [],
                "as_of": row["as_of"].isoformat() if row["as_of"] else None,
                "label": row["label"],
                "comment": row["comment"],
                "reviewer": row["reviewer"],
                "trace_id": row["trace_id"],
                "cited_sources": row["sources"] or [],
                "retrieved_articles": row["retrieved_articles"] or [],
                "notes": "etiqueta humana; expected_articles marcados en la interfaz",
            }
        )
    return out
