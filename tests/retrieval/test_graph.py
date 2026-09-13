from pathlib import Path

from sqlalchemy import select

from legal_ai.db.schema import article_references
from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.retrieval.retriever import Retriever
from tests.test_pipeline_api import indexed


def test_graph_expansion_appends_cited_articles(db, tmp_path: Path):
    indexed(db, tmp_path)
    plain = Retriever(db, HashingEmbedder()).search("período de prueba", 4)
    seeds = []
    for c in plain:
        if c.article_id not in seeds:
            seeds.append(c.article_id)
    seeds = seeds[:3]
    with db.connect() as conn:
        targets = set(
            conn.execute(
                select(article_references.c.target_article_id).where(
                    article_references.c.source_article_id.in_(seeds)
                )
            ).scalars()
        )
    assert targets, "the mini corpus should carry article references"
    expanded = Retriever(db, HashingEmbedder(), graph_extra=2).search("período de prueba", 4)
    assert len(expanded) == 4 and [c.rank for c in expanded] == [1, 2, 3, 4]
    graph = [c for c in expanded if c.retriever == "graph"]
    assert graph and {c.article_id for c in graph} <= targets
    assert not ({c.article_id for c in graph} & {c.article_id for c in plain[:2]})
    assert Retriever(db, HashingEmbedder(), graph_extra=2).name.endswith("+graph2")
