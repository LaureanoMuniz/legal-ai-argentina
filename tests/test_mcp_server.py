import asyncio
from pathlib import Path

from legal_ai.mcp_server import build_server
from legal_ai.settings import Settings
from tests.test_pipeline_api import indexed


def test_mcp_server_lists_and_calls_tools(db, tmp_path: Path):
    indexed(db, tmp_path)
    settings = Settings(
        database_url=db.url.render_as_string(hide_password=False),
        embedding_model="hashing",
        retrieval_mode="vector",
        rewrite_model=None,
    )
    server = build_server(settings)
    names = sorted(t.name for t in asyncio.run(server.list_tools()))
    assert names == ["find_related_legislation", "get_article", "get_law_version", "search_laws"]
    result = asyncio.run(server.call_tool("get_article", {"article_id": "25552:92bis"}))
    assert result
