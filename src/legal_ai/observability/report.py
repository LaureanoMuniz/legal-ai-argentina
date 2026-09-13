"""Summaries over the local span file: requests, latency by stage, tokens and cost."""

import json
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from legal_ai.bench import percentile

PRICES = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (3.0, 15.0)}


class StageStats(BaseModel):
    name: str
    count: int
    p50_ms: float
    p95_ms: float


class TraceSummary(BaseModel):
    requests: int
    stages: list[StageStats]
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    models: dict[str, int]
    retrievers: dict[str, int]
    abstention_flagged: int


def summarize(traces_path: Path, limit: int | None = None) -> TraceSummary:
    if not traces_path.exists():
        return TraceSummary(
            requests=0,
            stages=[],
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
            models={},
            retrievers={},
            abstention_flagged=0,
        )
    durations: dict[str, list[float]] = defaultdict(list)
    models: dict[str, int] = defaultdict(int)
    retrievers: dict[str, int] = defaultdict(int)
    tokens_in = tokens_out = 0
    cost = 0.0
    requests = 0
    with traces_path.open(encoding="utf-8") as fh:
        for line in fh:
            span = json.loads(line)
            name = span["name"]
            attrs = span.get("attributes", {})
            durations[name].append(float(span.get("duration_ms", 0.0)))
            if name == "ask":
                requests += 1
                retrievers[str(attrs.get("legal_ai.retriever", "?"))] += 1
            if name == "gen_ai.chat":
                model = str(attrs.get("gen_ai.request.model", "?"))
                models[model] += 1
                i = int(attrs.get("gen_ai.usage.input_tokens", 0) or 0)
                o = int(attrs.get("gen_ai.usage.output_tokens", 0) or 0)
                tokens_in += i
                tokens_out += o
                p_in, p_out = PRICES.get(model, (5.0, 25.0))
                cost += (i * p_in + o * p_out) / 1e6
    stages = [
        StageStats(name=n, count=len(v), p50_ms=percentile(v, 0.5), p95_ms=percentile(v, 0.95))
        for n, v in sorted(durations.items())
    ]
    return TraceSummary(
        requests=requests,
        stages=stages,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        estimated_cost_usd=cost,
        models=dict(models),
        retrievers=dict(retrievers),
        abstention_flagged=0,
    )
