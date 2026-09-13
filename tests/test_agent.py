from pathlib import Path

from pydantic_ai.models.test import TestModel

from legal_ai.agent import build_agent, run_agent
from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.retrieval.retriever import Retriever
from legal_ai.tools import Toolbox
from tests.test_pipeline_api import indexed


def test_agent_calls_tools_and_returns_grounded_answer(db, tmp_path: Path):
    indexed(db, tmp_path)
    toolbox = Toolbox(db, Retriever(db, HashingEmbedder()))
    agent = build_agent(TestModel(call_tools=["search_laws"]))
    run = run_agent(agent, toolbox, "¿Cuánto dura el período de prueba?")
    assert run.answer is not None
    assert [c["tool"] for c in run.tool_calls] == ["search_laws"]
    assert run.input_tokens >= 0
    assert isinstance(run.unsupported_sources, list)
