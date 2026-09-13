"""Retrieval benchmark: runs eval/benchmark.jsonl through a retriever and aggregates by category."""

import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from legal_ai.bench import percentile
from legal_ai.eval.metrics import (
    dedupe_ordered,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from legal_ai.retrieval.retriever import Retriever


class Question(BaseModel):
    id: str
    category: str
    question: str
    expected_articles: list[str]
    as_of: str | None = None
    notes: str = ""


class QuestionScore(BaseModel):
    id: str
    category: str
    question: str
    expected_articles: list[str]
    retrieved_articles: list[str]
    retrieved_chunks: int
    scored: bool
    hit_at_k: bool | None
    recall_at_k: float | None
    precision_at_k: float | None
    reciprocal_rank: float | None
    ndcg_at_k: float | None
    first_hit_rank: int | None
    retrieval_ms: float


class Aggregate(BaseModel):
    n: int
    n_scored: int
    hit_at_k: float | None
    recall_at_k: float | None
    precision_at_k: float | None
    mrr: float | None
    ndcg_at_k: float | None
    p50_retrieval_ms: float
    p95_retrieval_ms: float


class BenchmarkReport(BaseModel):
    name: str
    ran_at: datetime
    catalog_date: str
    k: int
    embedding_model: str
    retriever: str = "vector"
    questions_path: str
    overall: Aggregate
    by_category: dict[str, Aggregate]
    results: list[QuestionScore]


def load_questions(path: Path) -> list[Question]:
    return [
        Question.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def score_question(question: Question, retrieved_articles: list[str], k: int) -> QuestionScore:
    expected = question.expected_articles
    scored = bool(expected)
    first_hit = next(
        (i + 1 for i, a in enumerate(retrieved_articles[:k]) if a in set(expected)), None
    )
    return QuestionScore(
        id=question.id,
        category=question.category,
        question=question.question,
        expected_articles=expected,
        retrieved_articles=retrieved_articles,
        retrieved_chunks=0,
        scored=scored,
        hit_at_k=hit_at_k(retrieved_articles, expected, k) if scored else None,
        recall_at_k=recall_at_k(retrieved_articles, expected, k) if scored else None,
        precision_at_k=precision_at_k(retrieved_articles, expected, k) if scored else None,
        reciprocal_rank=reciprocal_rank(retrieved_articles, expected, k) if scored else None,
        ndcg_at_k=ndcg_at_k(retrieved_articles, expected, k) if scored else None,
        first_hit_rank=first_hit,
        retrieval_ms=0.0,
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(results: list[QuestionScore]) -> Aggregate:
    scored = [r for r in results if r.scored]
    return Aggregate(
        n=len(results),
        n_scored=len(scored),
        hit_at_k=_mean([1.0 if r.hit_at_k else 0.0 for r in scored]),
        recall_at_k=_mean([r.recall_at_k or 0.0 for r in scored]),
        precision_at_k=_mean([r.precision_at_k or 0.0 for r in scored]),
        mrr=_mean([r.reciprocal_rank or 0.0 for r in scored]),
        ndcg_at_k=_mean([r.ndcg_at_k or 0.0 for r in scored]),
        p50_retrieval_ms=percentile([r.retrieval_ms for r in results], 0.5),
        p95_retrieval_ms=percentile([r.retrieval_ms for r in results], 0.95),
    )


def run_benchmark(
    retriever: Retriever,
    questions_path: Path,
    k: int,
    name: str,
    embedding_model: str,
    catalog_date: str,
) -> BenchmarkReport:
    results: list[QuestionScore] = []
    for question in load_questions(questions_path):
        start = time.perf_counter()
        candidates = retriever.search(question.question, k)
        elapsed = (time.perf_counter() - start) * 1000
        articles = dedupe_ordered(c.article_id for c in candidates)
        score = score_question(question, articles, k)
        score.retrieved_chunks = len(candidates)
        score.retrieval_ms = elapsed
        results.append(score)
    by_category: dict[str, list[QuestionScore]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)
    return BenchmarkReport(
        name=name,
        ran_at=datetime.now(UTC),
        catalog_date=catalog_date,
        k=k,
        embedding_model=embedding_model,
        retriever=retriever.name,
        questions_path=str(questions_path),
        overall=aggregate(results),
        by_category={c: aggregate(rs) for c, rs in sorted(by_category.items())},
        results=results,
    )


def write_report(report: BenchmarkReport, experiments_dir: Path) -> Path:
    experiments_dir.mkdir(parents=True, exist_ok=True)
    path = experiments_dir / f"{report.ran_at.date().isoformat()}-{report.name}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
