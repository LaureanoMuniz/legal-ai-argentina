import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from legal_ai.cli import app
from legal_ai.ingest.catalog import CATALOG_RESOURCES
from legal_ai.ingest.fetch import norm_urls
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import read_resolved
from tests.conftest import (
    FIXTURE_NORMS,
    FIXTURE_RELATIONS,
    NORM_COLUMNS,
    RELATION_COLUMNS,
    write_csv_zip,
)

runner = CliRunner()


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGAL_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LEGAL_AI_INFOLEG_MIN_INTERVAL_SECONDS", "0")
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "mini.yaml").write_text(
        "name: mini\ndescription: test\nseeds:\n  - {tipo: Ley, numero: 20744, why: x}\n"
        "expand: {modificatorias_de_seeds: true, max_depth: 1, tipos: [Ley, Decreto]}\n",
        encoding="utf-8",
    )
    return tmp_path


def zip_bytes(tmp_path: Path, name: str, columns: list[str], rows: list[dict[str, str]]) -> bytes:
    return write_csv_zip(tmp_path / name, "inner.csv", columns, rows).read_bytes()


@pytest.fixture
def mocked_catalog(workdir: Path):
    normas = zip_bytes(workdir, "n.zip", NORM_COLUMNS, FIXTURE_NORMS)
    relations = zip_bytes(workdir, "r.zip", RELATION_COLUMNS, FIXTURE_RELATIONS)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(CATALOG_RESOURCES[0].url).mock(return_value=httpx.Response(200, content=normas))
        mock.get(CATALOG_RESOURCES[1].url).mock(return_value=httpx.Response(200, content=relations))
        mock.get(CATALOG_RESOURCES[2].url).mock(return_value=httpx.Response(200, content=relations))
        yield mock


def test_catalog_command_downloads_snapshot(workdir: Path, mocked_catalog):
    result = runner.invoke(app, ["ingest", "catalog", "--date", "2026-09-12"])
    assert result.exit_code == 0, result.output
    manifest = RawLayout(workdir / "data").catalog_dir(date(2026, 9, 12)) / "manifest.json"
    assert manifest.exists()
    assert "manifest.json" in result.output

    again = runner.invoke(app, ["ingest", "catalog", "--date", "2026-09-12"])
    assert again.exit_code == 1
    assert "--force" in again.output


def test_resolve_command_writes_resolved_json(workdir: Path, mocked_catalog):
    runner.invoke(app, ["ingest", "catalog", "--date", "2026-09-12"])
    result = runner.invoke(app, ["ingest", "resolve", "mini"])
    assert result.exit_code == 0, result.output
    resolved = read_resolved(ProcessedLayout(workdir / "data").resolved_path("mini"))
    assert resolved.ids() == [25552, 229909, 401266]
    assert resolved.catalog_date == date(2026, 9, 12)
    assert "3 normas" in result.output


def test_resolve_without_catalog_fails_clearly(workdir: Path):
    result = runner.invoke(app, ["ingest", "resolve", "mini"])
    assert result.exit_code == 1
    assert "ingest catalog" in result.output


def test_fetch_command_downloads_every_norm(workdir: Path, mocked_catalog):
    runner.invoke(app, ["ingest", "catalog", "--date", "2026-09-12"])
    runner.invoke(app, ["ingest", "resolve", "mini"])
    resolved = read_resolved(ProcessedLayout(workdir / "data").resolved_path("mini"))
    for norm in resolved.norms:
        for url in norm_urls(norm).values():
            if url is not None:
                mocked_catalog.get(url).mock(return_value=httpx.Response(200, content=b"<html/>"))

    result = runner.invoke(app, ["ingest", "fetch", "mini"])
    assert result.exit_code == 0, result.output
    layout = RawLayout(workdir / "data")
    assert (layout.norm_dir(25552) / "texact.htm").exists()
    meta = json.loads((layout.norm_dir(401266) / "meta.json").read_text())
    assert meta["missing"] == ["texact.htm"]
    assert "fetched=" in result.output

    limited = runner.invoke(app, ["ingest", "fetch", "mini", "--limit", "1"])
    assert limited.exit_code == 0
    assert "cached=4" in limited.output


def test_fetch_command_exits_1_when_a_file_fails(workdir: Path, mocked_catalog):
    runner.invoke(app, ["ingest", "catalog", "--date", "2026-09-12"])
    runner.invoke(app, ["ingest", "resolve", "mini"])
    resolved = read_resolved(ProcessedLayout(workdir / "data").resolved_path("mini"))
    for norm in resolved.norms:
        for name, url in norm_urls(norm).items():
            if url is None:
                continue
            status = 403 if name == "norma.htm" else 200
            mocked_catalog.get(url).mock(return_value=httpx.Response(status, content=b"x"))

    result = runner.invoke(app, ["ingest", "fetch", "mini"])
    assert result.exit_code == 1
    assert "failed=3" in result.output
