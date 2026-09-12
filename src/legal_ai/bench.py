"""Smoke benchmark: runs a question set through the pipeline and records hits, latency and cost."""

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from legal_ai.pipeline import Pipeline


class QuestionResult(BaseModel):
    id: str
    question: str
    category: str
    expected_articles: list[str]
    retrieved_articles: list[str]
    hit_at_k: bool
    retrieval_ms: float
    llm_ms: float | None
    total_ms: float
    input_tokens: int | None
    output_tokens: int | None
    insufficient_evidence: bool | None
    unsupported_sources: list[str]
    trace_id: str


class BenchReport(BaseModel):
    name: str
    ran_at: datetime
    catalog_date: str
    k: int
    embedding_model: str
    llm_model: str | None
    n: int
    hit_rate_at_k: float
    p50_retrieval_ms: float
    p95_retrieval_ms: float
    p50_total_ms: float
    p95_total_ms: float
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float | None
    results: list[QuestionResult]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def run_smoke(
    pipeline: Pipeline,
    questions_path: Path,
    k: int,
    generate: bool,
    embedding_model: str,
    llm_model: str | None,
    catalog_date: str,
    price_in_per_mtok: float = 5.0,
    price_out_per_mtok: float = 25.0,
    name: str = "phase3-baseline",
) -> BenchReport:
    results: list[QuestionResult] = []
    for line in questions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        response = pipeline.ask(item["question"], k=k, generate=generate)
        retrieved = [c.article_id for c in response.candidates]
        insufficient = response.answer.insufficient_evidence if response.answer else None
        if item["category"] == "not_in_corpus":
            hit = insufficient is True
        else:
            hit = any(a in retrieved for a in item["expected_articles"])
        results.append(
            QuestionResult(
                id=item["id"],
                question=item["question"],
                category=item["category"],
                expected_articles=item["expected_articles"],
                retrieved_articles=retrieved,
                hit_at_k=hit,
                retrieval_ms=response.timing.retrieval_ms,
                llm_ms=response.timing.llm_ms,
                total_ms=response.timing.total_ms,
                input_tokens=response.usage.input_tokens if response.usage else None,
                output_tokens=response.usage.output_tokens if response.usage else None,
                insufficient_evidence=insufficient,
                unsupported_sources=response.unsupported_sources,
                trace_id=response.trace_id,
            )
        )
    total_in = sum(r.input_tokens or 0 for r in results)
    total_out = sum(r.output_tokens or 0 for r in results)
    generated = any(r.input_tokens is not None for r in results)
    cost = (
        (total_in * price_in_per_mtok + total_out * price_out_per_mtok) / 1_000_000
        if generated
        else None
    )
    return BenchReport(
        name=name,
        ran_at=datetime.now(UTC),
        catalog_date=catalog_date,
        k=k,
        embedding_model=embedding_model,
        llm_model=llm_model if generated else None,
        n=len(results),
        hit_rate_at_k=sum(r.hit_at_k for r in results) / len(results) if results else 0.0,
        p50_retrieval_ms=percentile([r.retrieval_ms for r in results], 0.5),
        p95_retrieval_ms=percentile([r.retrieval_ms for r in results], 0.95),
        p50_total_ms=percentile([r.total_ms for r in results], 0.5),
        p95_total_ms=percentile([r.total_ms for r in results], 0.95),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        estimated_cost_usd=cost,
        results=results,
    )


def write_report(report: BenchReport, experiments_dir: Path) -> Path:
    experiments_dir.mkdir(parents=True, exist_ok=True)
    path = experiments_dir / f"{report.ran_at.date().isoformat()}-{report.name}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
