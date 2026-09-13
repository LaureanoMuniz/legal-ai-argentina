"""Agent benchmark: the same questions and judge as the generation benchmark, via tool calls."""

import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent

from legal_ai.agent import AgentDeps, run_agent
from legal_ai.bench import percentile
from legal_ai.eval.benchmark import Question, load_questions
from legal_ai.eval.generation import PRICES, GenerationAggregate, GenerationResult, Judge, aggregate
from legal_ai.generation.schema import GroundedAnswer
from legal_ai.retrieval.types import Candidate
from legal_ai.tools import Toolbox


class AgentReport(BaseModel):
    name: str
    ran_at: datetime
    llm_model: str
    judge_model: str
    n: int
    overall: GenerationAggregate
    by_category: dict[str, GenerationAggregate]
    not_in_corpus_abstention: float | None
    unsupported_source_citations: int
    tool_calls_total: int
    tool_calls_p50: float
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    results: list[GenerationResult]
    tool_traces: dict[str, list[dict[str, object]]]


def _candidates_from_toolbox(toolbox: Toolbox, version_ids: set[str]) -> list[Candidate]:
    out: list[Candidate] = []
    for vid in sorted(version_ids):
        article_id = vid.split("@")[0]
        info = toolbox.get_article(article_id)
        if info is None:
            continue
        for v in info.versions:
            if v.version_id == vid:
                out.append(
                    Candidate(
                        chunk_id=vid + "#0",
                        version_id=vid,
                        article_id=article_id,
                        document_id=info.document_id,
                        score=0.0,
                        rank=len(out) + 1,
                        retriever="agent",
                        context_prefix=f"{info.norm} · Art. {info.label}",
                        text=v.text,
                        status=v.status,
                        effective_from=v.effective_from,
                        effective_until=v.effective_until,
                    )
                )
    return out


def run_agent_benchmark(
    agent: Agent[AgentDeps, GroundedAnswer],
    toolbox: Toolbox,
    judge: Judge | None,
    questions_path: Path,
    name: str,
    llm_model: str,
    limit: int | None = None,
) -> AgentReport:
    questions: list[Question] = load_questions(questions_path)[:limit]
    results: list[GenerationResult] = []
    traces: dict[str, list[dict[str, object]]] = {}
    total_in = total_out = 0
    for q in questions:
        start = time.perf_counter()
        run = run_agent(agent, toolbox, q.question)
        elapsed = (time.perf_counter() - start) * 1000
        total_in += run.input_tokens
        total_out += run.output_tokens
        seen = {s for c in run.answer.claims for s in c.sources}
        for call in run.tool_calls:
            for a in call.get("hits", []) if isinstance(call.get("hits"), list) else []:
                seen.add(f"{a}@current")
        candidates = _candidates_from_toolbox(
            toolbox, {s for c in run.answer.claims for s in c.sources}
        )
        judgement = None
        if judge is not None and not run.answer.insufficient_evidence and run.answer.claims:
            judgement = judge.judge(q.question, run.answer, candidates)
        verdicts = judgement.verdicts if judgement else []
        retrieved = []
        for call in run.tool_calls:
            for a in call.get("hits", []) if isinstance(call.get("hits"), list) else []:
                if a not in retrieved:
                    retrieved.append(a)
        cited = sorted({s for c in run.answer.claims for s in c.sources})
        cited_articles = {s.split("@")[0] for s in cited}
        results.append(
            GenerationResult(
                id=q.id,
                category=q.category,
                question=q.question,
                expected_articles=q.expected_articles,
                retrieved_articles=retrieved,
                retrieval_hit=any(a in retrieved for a in q.expected_articles)
                if q.expected_articles
                else None,
                answer=run.answer.answer,
                insufficient_evidence=run.answer.insufficient_evidence,
                confidence=run.answer.confidence,
                n_claims=len(run.answer.claims),
                supported=sum(1 for v in verdicts if v.verdict == "supported"),
                partial=sum(1 for v in verdicts if v.verdict == "partial"),
                unsupported=sum(1 for v in verdicts if v.verdict == "unsupported"),
                answers_question=judgement.answers_question if judgement else None,
                cited_sources=cited,
                cited_expected=any(a in cited_articles for a in q.expected_articles)
                if q.expected_articles
                else None,
                unsupported_sources=run.unsupported_sources,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                llm_ms=elapsed,
                total_ms=elapsed,
                trace_id="",
                verdict_reasons=[f"{v.index}:{v.verdict}: {v.reason}" for v in verdicts],
            )
        )
        traces[q.id] = run.tool_calls
    by_cat: dict[str, list[GenerationResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
    nic = [r for r in results if r.category == "not_in_corpus"]
    p_in, p_out = PRICES.get(llm_model, (3.0, 15.0))
    j_in = getattr(judge, "input_tokens", 0) if judge else 0
    j_out = getattr(judge, "output_tokens", 0) if judge else 0
    jp_in, jp_out = PRICES.get(judge.model, (3.0, 15.0)) if judge else (0.0, 0.0)
    calls = [len(t) for t in traces.values()]
    return AgentReport(
        name=name,
        ran_at=datetime.now(UTC),
        llm_model=llm_model,
        judge_model=judge.model if judge else "",
        n=len(results),
        overall=aggregate(results),
        by_category={c: aggregate(rs) for c, rs in sorted(by_cat.items())},
        not_in_corpus_abstention=(sum(1 for r in nic if r.insufficient_evidence) / len(nic))
        if nic
        else None,
        unsupported_source_citations=sum(len(r.unsupported_sources) for r in results),
        tool_calls_total=sum(calls),
        tool_calls_p50=percentile([float(c) for c in calls], 0.5),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        estimated_cost_usd=(total_in * p_in + total_out * p_out + j_in * jp_in + j_out * jp_out)
        / 1e6,
        results=results,
        tool_traces=traces,
    )


def write_report(report: AgentReport, experiments_dir: Path) -> Path:
    experiments_dir.mkdir(parents=True, exist_ok=True)
    path = experiments_dir / f"{report.ran_at.date().isoformat()}-{report.name}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
