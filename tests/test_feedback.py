from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert

from legal_ai.db.schema import feedback
from legal_ai.feedback import feedback_summary, feedback_to_labels, read_feedback


def add(engine, **kwargs):
    row = {
        "created_at": datetime.now(UTC),
        "trace_id": "a" * 32,
        "question": "¿Cuántos días de vacaciones?",
        "answer": "14 días.",
        "label": "correct",
        "comment": None,
        "reviewer": "abogada",
        "sources": ["25552:150@current"],
        "expected_articles": ["25552:150"],
        "retrieved_articles": ["25552:150", "210489:29"],
        "as_of": None,
        "historical": False,
        "conversation_id": "c1",
    }
    row.update(kwargs)
    with engine.begin() as conn:
        conn.execute(insert(feedback).values(**row))


def test_summary_and_export_shape(db, tmp_path: Path):
    add(db)
    add(
        db,
        label="wrong_version",
        question="¿Cuánto duraba en 2023?",
        expected_articles=["25552:92bis"],
        comment="me dio el texto de hoy",
        reviewer="abogada",
    )
    add(
        db,
        label="incorrect",
        question="¿Cuántos días de vacaciones?",
        expected_articles=[],
        reviewer=None,
    )

    summary = feedback_summary(db)
    assert summary["total"] == 3 and summary["by_label"]["correct"] == 1
    assert summary["satisfaction"] == 1 / 3
    assert summary["by_reviewer"]["abogada"] == 2 and summary["by_reviewer"]["(anónimo)"] == 1

    assert len(read_feedback(db, label="wrong_version")) == 1
    rows = feedback_to_labels(db)
    assert [r["category"] for r in rows] == ["human", "human", "human"]
    assert rows[0]["expected_articles"] == ["25552:150"] and rows[0]["label"] == "correct"
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 3
    assert rows[-1]["question"] == "¿Cuántos días de vacaciones?" and rows[-1]["id"].endswith("-2")
