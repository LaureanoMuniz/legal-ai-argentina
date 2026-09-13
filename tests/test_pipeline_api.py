import json
from pathlib import Path

from fastapi.testclient import TestClient

from legal_ai.api.app import create_app
from legal_ai.generation.claude import ClaudeGenerator
from legal_ai.generation.schema import Claim, GroundedAnswer
from legal_ai.index.embed import build_corpus_chunks, embed_chunks
from legal_ai.index.embeddings import EmbeddingCache, HashingEmbedder
from legal_ai.index.load import load_corpus
from legal_ai.observability.tracing import flush, setup_tracing
from legal_ai.pipeline import Pipeline
from legal_ai.retrieval.retriever import Retriever
from tests.generation.test_claude import make_client
from tests.index.test_load import parsed_corpus


def indexed(db, tmp_path: Path):
    load_corpus(db, parsed_corpus(tmp_path), "mini")
    build_corpus_chunks(db, "mini")
    embed_chunks(db, HashingEmbedder(), EmbeddingCache(tmp_path / "emb.npz"), "mini")


def fake_generator():
    parsed = GroundedAnswer(
        answer="Seis meses [25552:92bis@current].",
        claims=[Claim(claim="Dura seis meses.", sources=["25552:92bis@current"])],
        confidence="high",
        insufficient_evidence=False,
    )
    client, _ = make_client(parsed)
    return ClaudeGenerator(client, "claude-opus-5")


def test_pipeline_ask_traces_and_answers(db, tmp_path: Path):
    indexed(db, tmp_path)
    traces = tmp_path / "spans.jsonl"
    tracer = setup_tracing("legal-ai-test", None, traces)
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), fake_generator(), tracer)
    response = pipeline.ask("¿Cuánto dura el período de prueba?", k=5)
    assert response.answer is not None and response.answer.answer.startswith("Seis meses")
    assert response.sources == ["25552:92bis@current"] and response.unsupported_sources == []
    assert len(response.candidates) == 5
    assert response.timing.total_ms > 0 and response.timing.llm_ms is not None
    assert len(response.trace_id) == 32
    flush()
    lines = [json.loads(line) for line in traces.read_text().splitlines()]
    names = {line["name"] for line in lines}
    assert {"ask", "retrieval.vector", "context.build", "gen_ai.chat"} <= names
    chat = next(line for line in lines if line["name"] == "gen_ai.chat")
    assert chat["attributes"]["gen_ai.request.model"] == "claude-opus-5"
    assert chat["trace_id"] == response.trace_id


def test_pipeline_without_generator_returns_candidates_only(db, tmp_path: Path):
    indexed(db, tmp_path)
    tracer = setup_tracing("legal-ai-test", None, tmp_path / "s.jsonl")
    response = Pipeline(Retriever(db, HashingEmbedder()), None, tracer).ask(
        "período de prueba", k=3
    )
    assert response.answer is None and response.timing.llm_ms is None
    assert len(response.candidates) == 3


def test_api_health_and_ask(db, tmp_path: Path):
    indexed(db, tmp_path)
    tracer = setup_tracing("legal-ai-test", None, tmp_path / "s.jsonl")
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), fake_generator(), tracer)
    client = TestClient(create_app(lambda: pipeline))
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["generation"] is True
    body = client.post(
        "/ask", json={"question": "¿Cuánto dura el período de prueba?", "k": 4}
    ).json()
    assert body["answer"]["answer"].startswith("Seis meses") and len(body["candidates"]) == 4
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_api_stream_trace_feedback_and_article(db, tmp_path: Path, monkeypatch):
    indexed(db, tmp_path)
    traces = tmp_path / "s.jsonl"
    tracer = setup_tracing("legal-ai-test", None, traces)
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), fake_generator(), tracer)
    client = TestClient(create_app(lambda: pipeline))
    stages = []
    with client.stream(
        "POST", "/ask/stream", json={"question": "¿Cuánto dura el período de prueba?", "k": 3}
    ) as r:
        body = "".join(r.iter_text())
    for block in body.split("\n\n"):
        if block.startswith("event: "):
            stages.append(block.split("\n")[0].removeprefix("event: "))
    assert stages == ["plan", "retrieval", "context", "generation", "done"]
    done = json.loads(
        [b for b in body.split("\n\n") if b.startswith("event: done")][0].split("\ndata: ", 1)[1]
    )
    assert done["answer"]["answer"].startswith("Seis meses") and len(done["candidates"]) == 3
    flush()
    monkeypatch.setattr(
        "legal_ai.api.app.Settings", lambda: type("S", (), {"traces_path": traces})()
    )
    spans = client.get(f"/trace/{done['trace_id']}").json()
    assert {s["name"] for s in spans} >= {"ask", "retrieval.vector", "gen_ai.chat"}
    fb = client.post(
        "/feedback",
        json={
            "trace_id": done["trace_id"],
            "question": "q",
            "answer": "a",
            "label": "correct",
            "sources": ["25552:92bis@current"],
            "reviewer": "test",
            "expected_articles": ["25552:92bis"],
            "retrieved_articles": ["25552:92bis"],
            "conversation_id": "c1",
        },
    ).json()
    assert fb["label"] == "correct" and client.get("/feedback").json()[0]["reviewer"] == "test"
    assert (
        client.post(
            "/feedback", json={"trace_id": done["trace_id"], "question": "q", "label": "nope"}
        ).status_code
        == 422
    )
    stats = client.get("/feedback/stats").json()
    assert stats["total"] == 1 and stats["satisfaction"] == 1.0
    assert client.get("/review").status_code == 200
    export = client.get("/feedback/export.jsonl")
    assert export.headers["content-type"].startswith("application/x-ndjson")
    first = json.loads(export.text.splitlines()[0])
    assert first["category"] == "human" and first["expected_articles"] == ["25552:92bis"]
    art = client.get("/article/25552:92bis").json()
    assert art["label"] == "92 bis" and client.get("/article/x:1").status_code == 404
    assert client.get("/").status_code == 200 and isinstance(client.get("/questions").json(), list)
