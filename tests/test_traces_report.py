import json
from pathlib import Path

from legal_ai.observability.report import summarize


def test_summarize_counts_requests_stages_tokens_and_cost(tmp_path: Path):
    path = tmp_path / "spans.jsonl"
    spans = [
        {"name": "ask", "duration_ms": 1000, "attributes": {"legal_ai.retriever": "hybrid"}},
        {"name": "retrieval.hybrid", "duration_ms": 100, "attributes": {}},
        {
            "name": "gen_ai.chat",
            "duration_ms": 800,
            "attributes": {
                "gen_ai.request.model": "claude-opus-5",
                "gen_ai.usage.input_tokens": 1000,
                "gen_ai.usage.output_tokens": 100,
            },
        },
        {"name": "ask", "duration_ms": 500, "attributes": {"legal_ai.retriever": "hybrid"}},
    ]
    path.write_text("\n".join(json.dumps(s) for s in spans) + "\n")
    s = summarize(path)
    assert s.requests == 2 and s.input_tokens == 1000 and s.output_tokens == 100
    assert abs(s.estimated_cost_usd - 0.0075) < 1e-9 and s.models == {"claude-opus-5": 1}
    assert {st.name for st in s.stages} == {"ask", "retrieval.hybrid", "gen_ai.chat"}
    assert summarize(tmp_path / "missing.jsonl").requests == 0
