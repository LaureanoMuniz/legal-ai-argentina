import json
from pathlib import Path

from legal_ai.eval.benchmark import load_questions, run_benchmark, score_question, write_report
from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.retrieval.retriever import Retriever
from tests.test_pipeline_api import indexed

REPO_BENCHMARK = Path(__file__).resolve().parents[2] / "eval" / "benchmark.jsonl"


def test_repo_benchmark_is_well_formed():
    questions = load_questions(REPO_BENCHMARK)
    assert len(questions) == 50
    assert len({q.id for q in questions}) == 50
    categories = {q.category for q in questions}
    assert categories == {
        "direct",
        "multi_article",
        "negation",
        "confusable",
        "derogated",
        "temporal",
        "not_in_corpus",
        "cross_reference",
    }
    for q in questions:
        assert (q.category == "not_in_corpus") == (q.expected_articles == [])
        assert (q.category == "temporal") == (q.as_of is not None)


def test_score_question_unscored_when_no_expected():
    from legal_ai.eval.benchmark import Question

    q = Question(id="x", category="not_in_corpus", question="?", expected_articles=[])
    s = score_question(q, ["a", "b"], 2)
    assert s.scored is False and s.hit_at_k is None and s.recall_at_k is None


def test_run_benchmark_aggregates_by_category(db, tmp_path: Path):
    indexed(db, tmp_path)
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps(
            {
                "id": "a",
                "category": "direct",
                "question": "período de prueba contrato por tiempo indeterminado seis meses",
                "expected_articles": ["25552:92bis"],
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "b",
                "category": "direct",
                "question": "zzzz qqqq",
                "expected_articles": ["25552:999"],
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "c",
                "category": "not_in_corpus",
                "question": "tope comercio",
                "expected_articles": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report = run_benchmark(
        Retriever(db, HashingEmbedder()),
        questions,
        k=5,
        name="t",
        embedding_model="hashing-1024",
        catalog_date="2026-09-12",
    )
    assert report.overall.n == 3 and report.overall.n_scored == 2
    assert report.overall.hit_at_k == 0.5 and report.overall.recall_at_k == 0.5
    assert report.by_category["not_in_corpus"].n_scored == 0
    assert report.by_category["not_in_corpus"].hit_at_k is None
    by_id = {r.id: r for r in report.results}
    assert by_id["a"].first_hit_rank is not None and by_id["a"].retrieved_chunks == 5
    assert len(by_id["a"].retrieved_articles) <= 5
    assert by_id["b"].reciprocal_rank == 0.0
    path = write_report(report, tmp_path / "experiments")
    assert json.loads(path.read_text())["overall"]["n_scored"] == 2
