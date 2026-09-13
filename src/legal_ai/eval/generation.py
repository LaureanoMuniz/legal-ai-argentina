"""Generation benchmark: abstention, claim support (judge), source hits, cost and latency."""

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from legal_ai.bench import percentile
from legal_ai.eval.benchmark import Question, load_questions
from legal_ai.eval.judge import Judgement
from legal_ai.generation.schema import GroundedAnswer
from legal_ai.pipeline import Pipeline
from legal_ai.retrieval.types import Candidate

PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
}


class Judge(Protocol):
    model: str

    def judge(
        self, question: str, answer: GroundedAnswer, candidates: list[Candidate]
    ) -> Judgement: ...


class GenerationResult(BaseModel):
    id: str
    category: str
    question: str
    expected_articles: list[str]
    retrieved_articles: list[str]
    retrieval_hit: bool | None
    answer: str | None
    insufficient_evidence: bool | None
    confidence: str | None
    n_claims: int
    supported: int
    partial: int
    unsupported: int
    answers_question: bool | None
    cited_sources: list[str]
    cited_expected: bool | None
    unsupported_sources: list[str]
    input_tokens: int | None
    output_tokens: int | None
    llm_ms: float | None
    total_ms: float
    trace_id: str
    verdict_reasons: list[str]


class GenerationAggregate(BaseModel):
    n: int
    abstained: int
    answered: int
    abstention_rate: float | None
    claims: int
    claim_support_rate: float | None
    claim_partial_rate: float | None
    cited_expected_rate: float | None
    answers_question_rate: float | None
    p50_total_ms: float
    p95_total_ms: float


class GenerationReport(BaseModel):
    name: str
    ran_at: datetime
    catalog_date: str
    k: int
    retriever: str
    llm_model: str
    judge_model: str
    n: int
    overall: GenerationAggregate
    by_category: dict[str, GenerationAggregate]
    not_in_corpus_abstention: float | None
    answerable_false_abstention: float | None
    unsupported_source_citations: int
    total_input_tokens: int
    total_output_tokens: int
    judge_input_tokens: int
    judge_output_tokens: int
    estimated_cost_usd: float
    results: list[GenerationResult]


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def aggregate(results: list[GenerationResult]) -> GenerationAggregate:
    answered = [r for r in results if r.insufficient_evidence is False]
    abstained = [r for r in results if r.insufficient_evidence is True]
    claims = sum(r.n_claims for r in answered)
    return GenerationAggregate(
        n=len(results),
        abstained=len(abstained),
        answered=len(answered),
        abstention_rate=_rate(len(abstained), len(results)),
        claims=claims,
        claim_support_rate=_rate(sum(r.supported for r in answered), claims),
        claim_partial_rate=_rate(sum(r.partial for r in answered), claims),
        cited_expected_rate=_rate(
            sum(1 for r in answered if r.cited_expected),
            sum(1 for r in answered if r.expected_articles),
        ),
        answers_question_rate=_rate(sum(1 for r in answered if r.answers_question), len(answered)),
        p50_total_ms=percentile([r.total_ms for r in results], 0.5),
        p95_total_ms=percentile([r.total_ms for r in results], 0.95),
    )


def evaluate_question(
    pipeline: Pipeline, judge: Judge | None, question: Question, k: int
) -> GenerationResult:
    response = pipeline.ask(question.question, k=k, generate=True)
    retrieved: list[str] = []
    for c in response.candidates:
        if c.article_id not in retrieved:
            retrieved.append(c.article_id)
    expected = question.expected_articles
    answer = response.answer
    judgement = None
    if judge is not None and answer is not None and not answer.insufficient_evidence:
        judgement = judge.judge(question.question, answer, response.candidates)
    verdicts = judgement.verdicts if judgement else []
    cited = sorted({s for c in (answer.claims if answer else []) for s in c.sources})
    cited_articles = {s.split("@")[0] for s in cited}
    return GenerationResult(
        id=question.id,
        category=question.category,
        question=question.question,
        expected_articles=expected,
        retrieved_articles=retrieved,
        retrieval_hit=any(a in retrieved for a in expected) if expected else None,
        answer=answer.answer if answer else None,
        insufficient_evidence=answer.insufficient_evidence if answer else None,
        confidence=answer.confidence if answer else None,
        n_claims=len(answer.claims) if answer else 0,
        supported=sum(1 for v in verdicts if v.verdict == "supported"),
        partial=sum(1 for v in verdicts if v.verdict == "partial"),
        unsupported=sum(1 for v in verdicts if v.verdict == "unsupported"),
        answers_question=judgement.answers_question if judgement else None,
        cited_sources=cited,
        cited_expected=any(a in cited_articles for a in expected) if expected else None,
        unsupported_sources=response.unsupported_sources,
        input_tokens=response.usage.input_tokens if response.usage else None,
        output_tokens=response.usage.output_tokens if response.usage else None,
        llm_ms=response.timing.llm_ms,
        total_ms=response.timing.total_ms,
        trace_id=response.trace_id,
        verdict_reasons=[f"{v.index}:{v.verdict}: {v.reason}" for v in verdicts],
    )


def run_generation_benchmark(
    pipeline: Pipeline,
    judge: Judge | None,
    questions_path: Path,
    k: int,
    name: str,
    catalog_date: str,
    llm_model: str,
    limit: int | None = None,
) -> GenerationReport:
    questions = load_questions(questions_path)[:limit]
    results = [evaluate_question(pipeline, judge, q, k) for q in questions]
    by_cat: dict[str, list[GenerationResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
    nic = [r for r in results if r.category == "not_in_corpus"]
    answerable_hit = [r for r in results if r.category != "not_in_corpus" and r.retrieval_hit]
    total_in = sum(r.input_tokens or 0 for r in results)
    total_out = sum(r.output_tokens or 0 for r in results)
    j_in = getattr(judge, "input_tokens", 0) if judge else 0
    j_out = getattr(judge, "output_tokens", 0) if judge else 0
    p_in, p_out = PRICES.get(llm_model, (5.0, 25.0))
    jp_in, jp_out = PRICES.get(judge.model, (3.0, 15.0)) if judge else (0.0, 0.0)
    cost = (total_in * p_in + total_out * p_out + j_in * jp_in + j_out * jp_out) / 1e6
    return GenerationReport(
        name=name,
        ran_at=datetime.now(UTC),
        catalog_date=catalog_date,
        k=k,
        retriever=pipeline.retriever.name,
        llm_model=llm_model,
        judge_model=judge.model if judge else "",
        n=len(results),
        overall=aggregate(results),
        by_category={c: aggregate(rs) for c, rs in sorted(by_cat.items())},
        not_in_corpus_abstention=_rate(sum(1 for r in nic if r.insufficient_evidence), len(nic)),
        answerable_false_abstention=_rate(
            sum(1 for r in answerable_hit if r.insufficient_evidence), len(answerable_hit)
        ),
        unsupported_source_citations=sum(len(r.unsupported_sources) for r in results),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        judge_input_tokens=j_in,
        judge_output_tokens=j_out,
        estimated_cost_usd=cost,
        results=results,
    )


def write_report(report: GenerationReport, experiments_dir: Path) -> Path:
    experiments_dir.mkdir(parents=True, exist_ok=True)
    path = experiments_dir / f"{report.ran_at.date().isoformat()}-{report.name}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_report(path: Path) -> GenerationReport:
    return GenerationReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
