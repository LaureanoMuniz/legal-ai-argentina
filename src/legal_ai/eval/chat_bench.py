"""Conversation benchmark: each turn is scored with the history of the previous ones."""

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from legal_ai.bench import percentile
from legal_ai.eval.metrics import dedupe_ordered, hit_at_k, ndcg_at_k, recall_at_k
from legal_ai.pipeline import Pipeline


class Turn(BaseModel):
    id: str
    kind: str
    question: str
    expected_articles: list[str]
    as_of: str | None = None


class Conversation(BaseModel):
    id: str
    title: str
    turns: list[Turn]


class TurnResult(BaseModel):
    conversation_id: str
    turn_id: str
    kind: str
    position: int
    question: str
    standalone: str | None
    rewritten: str | None
    subqueries: list[str]
    as_of_expected: str | None
    as_of_used: str | None
    expected_articles: list[str]
    retrieved_articles: list[str]
    scored: bool
    hit_at_k: bool | None
    recall_at_k: float | None
    ndcg_at_k: float | None
    first_hit_rank: int | None
    version_hit: bool | None
    answer: str | None
    insufficient_evidence: bool | None
    total_ms: float


class ChatAggregate(BaseModel):
    n: int
    n_scored: int
    hit_at_k: float | None
    recall_at_k: float | None
    ndcg_at_k: float | None


class ChatReport(BaseModel):
    name: str
    ran_at: datetime
    with_history: bool
    k: int
    retriever: str
    generated: bool
    n_conversations: int
    n_turns: int
    overall: ChatAggregate
    first_turns: ChatAggregate
    follow_ups: ChatAggregate
    by_kind: dict[str, ChatAggregate]
    p50_total_ms: float
    results: list[TurnResult]


def load_conversations(path: Path) -> list[Conversation]:
    return [
        Conversation.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def aggregate(results: list[TurnResult]) -> ChatAggregate:
    scored = [r for r in results if r.scored]
    mean = lambda values: (sum(values) / len(values)) if values else None  # noqa: E731
    return ChatAggregate(
        n=len(results),
        n_scored=len(scored),
        hit_at_k=mean([1.0 if r.hit_at_k else 0.0 for r in scored]),
        recall_at_k=mean([r.recall_at_k or 0.0 for r in scored]),
        ndcg_at_k=mean([r.ndcg_at_k or 0.0 for r in scored]),
    )


def run_chat_benchmark(
    pipeline: Pipeline,
    path: Path,
    k: int,
    name: str,
    with_history: bool = True,
    generate: bool = True,
) -> ChatReport:
    conversations = load_conversations(path)
    results: list[TurnResult] = []
    for conversation in conversations:
        history: list[tuple[str, str]] = []
        for position, turn in enumerate(conversation.turns, start=1):
            response = pipeline.ask(
                turn.question,
                k=k,
                generate=generate,
                history=history if with_history else None,
            )
            articles = dedupe_ordered(c.article_id for c in response.candidates)
            expected = turn.expected_articles
            scored = bool(expected)
            as_of = date.fromisoformat(turn.as_of) if turn.as_of else None
            version_hit = None
            if as_of is not None and expected:
                version_hit = any(
                    c.article_id in expected
                    and c.effective_from is not None
                    and c.effective_from <= as_of
                    and (c.effective_until is None or c.effective_until > as_of)
                    for c in response.candidates[:k]
                )
            answer_text = response.answer.answer if response.answer else None
            results.append(
                TurnResult(
                    conversation_id=conversation.id,
                    turn_id=turn.id,
                    kind=turn.kind,
                    position=position,
                    question=turn.question,
                    standalone=response.plan.query
                    if response.plan.query != turn.question
                    else None,
                    rewritten=response.plan.rewritten,
                    subqueries=response.plan.subqueries,
                    as_of_expected=turn.as_of,
                    as_of_used=response.plan.as_of.isoformat() if response.plan.as_of else None,
                    expected_articles=expected,
                    retrieved_articles=articles,
                    scored=scored,
                    hit_at_k=hit_at_k(articles, expected, k) if scored else None,
                    recall_at_k=recall_at_k(articles, expected, k) if scored else None,
                    ndcg_at_k=ndcg_at_k(articles, expected, k) if scored else None,
                    first_hit_rank=next(
                        (i + 1 for i, a in enumerate(articles[:k]) if a in set(expected)), None
                    ),
                    version_hit=version_hit,
                    answer=answer_text,
                    insufficient_evidence=(
                        response.answer.insufficient_evidence if response.answer else None
                    ),
                    total_ms=response.timing.total_ms,
                )
            )
            if answer_text:
                history.append((turn.question, answer_text))
            elif response.candidates:
                top = response.candidates[0]
                history.append((turn.question, f"{top.context_prefix} {top.text[:300]}"))
    by_kind: dict[str, list[TurnResult]] = defaultdict(list)
    for r in results:
        by_kind[r.kind].append(r)
    return ChatReport(
        name=name,
        ran_at=datetime.now(UTC),
        with_history=with_history,
        k=k,
        retriever=pipeline.retriever.name,
        generated=generate,
        n_conversations=len(conversations),
        n_turns=len(results),
        overall=aggregate(results),
        first_turns=aggregate([r for r in results if r.position == 1]),
        follow_ups=aggregate([r for r in results if r.position > 1]),
        by_kind={kind: aggregate(rs) for kind, rs in sorted(by_kind.items())},
        p50_total_ms=percentile([r.total_ms for r in results], 0.5),
        results=results,
    )


def write_report(report: ChatReport, experiments_dir: Path) -> Path:
    experiments_dir.mkdir(parents=True, exist_ok=True)
    path = experiments_dir / f"{report.ran_at.date().isoformat()}-{report.name}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
