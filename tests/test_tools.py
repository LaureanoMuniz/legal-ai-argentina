from datetime import date
from pathlib import Path

from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.retrieval.retriever import Retriever
from legal_ai.tools import Toolbox
from tests.test_pipeline_api import indexed


def test_toolbox_search_article_version_and_relations(db, tmp_path: Path):
    indexed(db, tmp_path)
    box = Toolbox(db, Retriever(db, HashingEmbedder()))
    hits = box.search_laws("período de prueba", k=3)
    assert len(hits) == 3 and hits[0].rank == 1 and hits[0].norm.startswith("Ley")
    info = box.get_article("25552:92bis")
    assert info is not None and info.norm == "Ley 20744" and info.label == "92 bis"
    assert any(v.version_kind == "current" for v in info.versions)
    assert box.get_article("nope:1") is None
    today = box.get_law_version("25552:92bis", date(2026, 9, 1))
    assert today is not None and today.effective_until is None
    assert box.get_law_version("25552:92bis", date(1900, 1, 1)) is None
    related = box.find_related_legislation(25552, limit=5)
    assert isinstance(related, list)
