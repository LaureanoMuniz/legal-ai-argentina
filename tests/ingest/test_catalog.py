import hashlib
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from legal_ai.ingest.catalog import (
    CATALOG_RESOURCES,
    SnapshotExistsError,
    download_catalog,
    latest_snapshot,
    load_snapshot,
)
from legal_ai.ingest.layout import RawLayout


@pytest.fixture
def mocked_resources():
    with respx.mock(assert_all_called=False) as mock:
        for resource in CATALOG_RESOURCES:
            mock.get(resource.url).mock(
                return_value=httpx.Response(200, content=resource.name.encode())
            )
        yield mock


def test_download_writes_files_and_manifest(tmp_path: Path, mocked_resources):
    layout = RawLayout(tmp_path)
    snapshot = download_catalog(layout, httpx.Client(), date(2026, 9, 12))

    assert snapshot.snapshot_date == date(2026, 9, 12)
    assert [r.name for r in snapshot.resources] == ["normas", "modificatorias", "modificadas"]
    for record in snapshot.resources:
        path = layout.catalog_dir(date(2026, 9, 12)) / record.filename
        assert path.read_bytes() == record.name.encode()
        assert record.sha256 == hashlib.sha256(record.name.encode()).hexdigest()
        assert record.size_bytes == len(record.name)

    manifest = json.loads((layout.catalog_dir(date(2026, 9, 12)) / "manifest.json").read_text())
    assert manifest["snapshot_date"] == "2026-09-12"
    assert len(manifest["resources"]) == 3


def test_download_refuses_to_overwrite_without_force(tmp_path: Path, mocked_resources):
    layout = RawLayout(tmp_path)
    download_catalog(layout, httpx.Client(), date(2026, 9, 12))
    with pytest.raises(SnapshotExistsError):
        download_catalog(layout, httpx.Client(), date(2026, 9, 12))
    download_catalog(layout, httpx.Client(), date(2026, 9, 12), force=True)


def test_download_fails_on_http_error(tmp_path: Path):
    layout = RawLayout(tmp_path)
    with respx.mock as mock:
        mock.get(CATALOG_RESOURCES[0].url).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            download_catalog(layout, httpx.Client(), date(2026, 9, 12))
    assert not (layout.catalog_dir(date(2026, 9, 12)) / "manifest.json").exists()


def test_load_and_latest_snapshot(tmp_path: Path, mocked_resources):
    layout = RawLayout(tmp_path)
    assert latest_snapshot(layout) is None
    download_catalog(layout, httpx.Client(), date(2026, 8, 1))
    download_catalog(layout, httpx.Client(), date(2026, 9, 12))
    loaded = load_snapshot(layout, date(2026, 8, 1))
    assert loaded.snapshot_date == date(2026, 8, 1)
    latest = latest_snapshot(layout)
    assert latest is not None
    assert latest.snapshot_date == date(2026, 9, 12)
    assert latest.path_for("normas", layout) == (
        layout.catalog_dir(date(2026, 9, 12)) / "base-infoleg-normativa-nacional.zip"
    )
