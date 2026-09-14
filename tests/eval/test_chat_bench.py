import json
from pathlib import Path

from legal_ai.eval.chat_bench import load_conversations, run_chat_benchmark, write_report
from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.observability.tracing import setup_tracing
from legal_ai.pipeline import Pipeline
from legal_ai.retrieval.retriever import Retriever
from tests.test_pipeline_api import fake_generator, indexed

REPO = Path(__file__).resolve().parents[2] / "eval" / "conversations.jsonl"


def test_repo_conversations_are_well_formed():
    convs = load_conversations(REPO)
    assert len(convs) >= 5
    ids = [t.id for c in convs for t in c.turns]
    assert len(ids) == len(set(ids))
    for c in convs:
        assert c.turns and c.turns[0].kind == "apertura"
        for t in c.turns:
            assert (t.kind == "sin_respuesta") == (t.expected_articles == [])


def test_chat_benchmark_scores_turns_and_keeps_history(db, tmp_path: Path):
    indexed(db, tmp_path)
    path = tmp_path / "c.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "c1",
                "title": "t",
                "turns": [
                    {
                        "id": "t1",
                        "kind": "apertura",
                        "question": "período de prueba",
                        "expected_articles": ["25552:92bis"],
                    },
                    {
                        "id": "t2",
                        "kind": "elipsis",
                        "question": "¿y eso?",
                        "expected_articles": ["25552:92bis"],
                    },
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    pipeline = Pipeline(
        Retriever(db, HashingEmbedder()),
        fake_generator(),
        setup_tracing("t", None, tmp_path / "s.jsonl"),
    )
    report = run_chat_benchmark(pipeline, path, k=5, name="t", with_history=True)
    assert report.n_conversations == 1 and report.n_turns == 2
    assert report.first_turns.n == 1 and report.follow_ups.n == 1
    assert report.overall.hit_at_k is not None
    assert set(report.by_kind) == {"apertura", "elipsis"}
    assert report.results[1].answer and report.results[1].position == 2
    assert write_report(report, tmp_path / "exp").exists()
