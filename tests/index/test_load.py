import shutil
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from legal_ai.db.schema import article_versions, articles, documents, relations
from legal_ai.index.load import load_corpus
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.parse.corpus import parse_corpus
from tests.parse.test_corpus import make_resolved, make_rows

FIXTURES = Path("tests/fixtures/infoleg")


def parsed_corpus(tmp_path: Path) -> ProcessedLayout:
    raw = RawLayout(tmp_path / "data")
    for fixture in FIXTURES.iterdir():
        shutil.copytree(fixture, raw.norm_dir(int(fixture.name)))
    processed = ProcessedLayout(tmp_path / "data")
    parse_corpus(make_resolved(), make_rows(), raw, processed)
    return processed


def test_load_is_idempotent_and_counts_match(db, tmp_path: Path):
    processed = parsed_corpus(tmp_path)
    first = load_corpus(db, processed, "mini")
    second = load_corpus(db, processed, "mini")
    assert first == second
    assert first.documents == 4 and first.articles > 290 and first.versions > first.articles
    with db.connect() as conn:
        assert conn.execute(select(func.count()).select_from(documents)).scalar() == 4
        assert conn.execute(select(func.count()).select_from(articles)).scalar() == first.articles
        doc = conn.execute(select(documents).where(documents.c.id_norma == 95487)).mappings().one()
        assert doc["numeros"] == ["384", "12"] and doc["corpus"] == "mini"
        version = (
            conn.execute(
                select(article_versions).where(article_versions.c.id == "25552:28@current")
            )
            .mappings()
            .one()
        )
        assert version["status"] == "derogado" and version["effective_from"] == date(2026, 3, 6)
        assert conn.execute(select(func.count()).select_from(relations)).scalar() == first.relations
