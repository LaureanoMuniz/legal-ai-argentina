import json
from pathlib import Path

from legal_ai.bench import percentile, run_smoke, write_report
from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.observability.tracing import setup_tracing
from legal_ai.pipeline import Pipeline
from legal_ai.retrieval.retriever import Retriever
from tests.test_pipeline_api import fake_generator, indexed


def test_percentile_picks_nearest_rank():
    assert percentile([], 0.5) == 0.0
    assert percentile([3.0, 1.0, 2.0], 0.5) == 2.0
    assert percentile([3.0, 1.0, 2.0], 0.95) == 3.0


def test_run_smoke_computes_hits_and_percentiles(db, tmp_path: Path):
    indexed(db, tmp_path)
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps(
            {
                "id": "a",
                "question": "período de prueba contrato por tiempo indeterminado seis meses",
                "expected_articles": ["25552:92bis"],
                "category": "direct",
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "b",
                "question": "tope indemnizatorio comercio",
                "expected_articles": [],
                "category": "not_in_corpus",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    tracer = setup_tracing("t", None, tmp_path / "s.jsonl")
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), fake_generator(), tracer)
    report = run_smoke(
        pipeline,
        questions,
        k=5,
        generate=True,
        embedding_model="hashing-1024",
        llm_model="claude-opus-5",
        catalog_date="2026-09-12",
    )
    assert report.n == 2 and report.k == 5
    by_id = {r.id: r for r in report.results}
    assert by_id["a"].hit_at_k is True and "25552:92bis" in by_id["a"].retrieved_articles
    assert by_id["b"].hit_at_k is False
    assert report.hit_rate_at_k == 0.5
    assert report.p95_retrieval_ms >= report.p50_retrieval_ms > 0
    assert report.total_input_tokens == 2400 and report.estimated_cost_usd is not None
    path = write_report(report, tmp_path / "experiments")
    assert path.exists() and json.loads(path.read_text())["hit_rate_at_k"] == 0.5


def test_run_smoke_without_generation_has_no_cost(db, tmp_path: Path):
    indexed(db, tmp_path)
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps(
            {
                "id": "a",
                "question": "período de prueba",
                "expected_articles": ["25552:92bis"],
                "category": "direct",
            }
        )
        + "\n"
    )
    tracer = setup_tracing("t", None, tmp_path / "s.jsonl")
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), None, tracer)
    report = run_smoke(
        pipeline,
        questions,
        k=3,
        generate=False,
        embedding_model="hashing-1024",
        llm_model="claude-opus-5",
        catalog_date="2026-09-12",
    )
    assert report.llm_model is None and report.estimated_cost_usd is None
    assert report.results[0].llm_ms is None
