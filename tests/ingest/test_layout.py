from datetime import date
from pathlib import Path

from legal_ai.ingest.layout import ProcessedLayout, RawLayout


def test_raw_paths(tmp_path: Path):
    layout = RawLayout(tmp_path)
    assert layout.root == tmp_path / "raw" / "infoleg"
    assert layout.catalog_dir(date(2026, 9, 12)) == layout.root / "catalog" / "2026-09-12"
    assert layout.norm_dir(25552) == layout.root / "normas" / "25552"


def test_catalog_dates_lists_existing_snapshots_sorted(tmp_path: Path):
    layout = RawLayout(tmp_path)
    (layout.root / "catalog" / "2026-09-12").mkdir(parents=True)
    (layout.root / "catalog" / "2026-08-01").mkdir(parents=True)
    (layout.root / "catalog" / "not-a-date").mkdir(parents=True)
    assert layout.catalog_dates() == [date(2026, 8, 1), date(2026, 9, 12)]


def test_catalog_dates_empty_when_missing(tmp_path: Path):
    assert RawLayout(tmp_path).catalog_dates() == []


def test_processed_paths(tmp_path: Path):
    layout = ProcessedLayout(tmp_path)
    assert layout.corpus_dir("laboral") == tmp_path / "processed" / "laboral"
    assert layout.resolved_path("laboral") == tmp_path / "processed" / "laboral" / "resolved.json"
