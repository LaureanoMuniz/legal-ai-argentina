import json
from datetime import date
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
                as_of=date(2020, 6, 30),
                historical=True,
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
    reloaded = again.rewrite("¿Puede el trabajador renunciar a sus derechos?")
    assert (
        reloaded.query == first.query
        and reloaded.as_of == date(2020, 6, 30)
        and reloaded.historical
    )
    assert again.calls == 0


class StaticRewriter:
    name = "rewrite(static)"

    def rewrite(self, question: str, history=None) -> Rewrite:
        return Rewrite(
            query="período de prueba contrato por tiempo indeterminado",
            terms=["prueba"],
            standalone="¿cuánto dura el período de prueba?" if history else None,
            subqueries=["período de prueba casas particulares"],
        )


def test_retriever_searches_with_rewritten_query(db, tmp_path: Path):
    indexed(db, tmp_path)
    r = Retriever(
        db, HashingEmbedder(), mode="vector", rewriter=StaticRewriter(), multi_query=False
    )
    out = r.search("¿cuánto dura?", 3)
    assert len(out) == 3 and "25552:92bis" in [c.article_id for c in out]
    assert r.name.endswith("+rewrite(static)")
    multi = Retriever(db, HashingEmbedder(), mode="vector", rewriter=StaticRewriter())
    fused = multi.search("período de prueba", 3)
    assert len(fused) == 3 and all(c.retriever == "rrf" for c in fused)
    assert multi.name.endswith("+rewrite(static)+multi")
    plan = multi.plan("período de prueba", None, None)
    assert plan.rewritten and plan.historical is False and plan.as_of is None
    assert plan.subqueries == [] and plan.query == "período de prueba"
    with_history = multi.plan("¿y eso?", None, None, [("¿cuánto dura?", "seis meses")])
    assert with_history.query == "¿cuánto dura el período de prueba?"
    dec = Retriever(db, HashingEmbedder(), rewriter=StaticRewriter(), decompose=True)
    assert dec.plan("x", None, None).subqueries == ["período de prueba casas particulares"]
    assert len(dec.search("período de prueba", 3)) == 3 and dec.name.endswith("+decompose")
