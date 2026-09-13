import json
from pathlib import Path
from types import SimpleNamespace

from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.retrieval.retriever import Retriever
from legal_ai.retrieval.rewrite import ClaudeRewriter, Rewrite
from tests.test_pipeline_api import indexed


class FakeMessages:
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        assert kwargs["output_format"] is Rewrite
        assert kwargs["messages"][0]["content"].startswith("PREGUNTA: ")
        return SimpleNamespace(
            parsed_output=Rewrite(
                query="Irrenunciabilidad de derechos del trabajador",
                terms=["irrenunciabilidad", "nulidad"],
            ),
            usage=SimpleNamespace(input_tokens=300, output_tokens=40),
        )


def test_rewriter_caches_on_disk_and_counts_usage(tmp_path: Path):
    client = SimpleNamespace(messages=FakeMessages())
    cache = tmp_path / "rw.json"
    rw = ClaudeRewriter(client, "claude-opus-5", cache)
    first = rw.rewrite("¿Puede el trabajador renunciar a sus derechos?")
    assert (
        first.search_text
        == "Irrenunciabilidad de derechos del trabajador irrenunciabilidad nulidad"
    )
    assert rw.calls == 1 and rw.input_tokens == 300 and rw.output_tokens == 40
    rw.rewrite("¿Puede el trabajador renunciar a sus derechos?")
    assert client.messages.calls == 1 and rw.calls == 1
    assert len(json.loads(cache.read_text())) == 1
    again = ClaudeRewriter(SimpleNamespace(messages=FakeMessages()), "claude-opus-5", cache)
    assert again.rewrite("¿Puede el trabajador renunciar a sus derechos?").query == first.query
    assert again.calls == 0


class StaticRewriter:
    name = "rewrite(static)"

    def rewrite(self, question: str) -> Rewrite:
        return Rewrite(
            query="período de prueba contrato por tiempo indeterminado", terms=["prueba"]
        )


def test_retriever_searches_with_rewritten_query(db, tmp_path: Path):
    indexed(db, tmp_path)
    r = Retriever(db, HashingEmbedder(), mode="vector", rewriter=StaticRewriter())
    out = r.search("¿cuánto dura?", 3)
    assert len(out) == 3 and "25552:92bis" in [c.article_id for c in out]
    assert r.name.endswith("+rewrite(static)")
