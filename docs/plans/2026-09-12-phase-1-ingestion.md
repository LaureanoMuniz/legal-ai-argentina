# Phase 1: Infoleg Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download the Infoleg open dataset and the HTML texts of every norm in the `laboral` corpus into an immutable, hashed `data/raw/` layout, reproducibly, from a CLI.

**Architecture:** Three streaming steps. `catalog` downloads the three ZIPs from datos.jus.gob.ar into a dated snapshot with a manifest. `resolve` streams the 428k-row CSV to turn `corpus/laboral.yaml` (law numbers) into a list of `id_norma`s, expanded with their modifying norms. `fetch` downloads `norma.htm`, `texact.htm` and the two "vínculos" pages per norm with a browser User-Agent, rate limiting, retries and an on-disk cache. No database yet; Postgres enters in Phase 2/3.

**Tech Stack:** Python 3.12, `uv`, `httpx`, `pydantic` v2, `pydantic-settings`, `typer`, `pyyaml`, `pytest`, `respx`, `ruff`, `pyright`. Docker Compose with `paradedb/paradedb:0.25.9-pg17` (scaffolded now, used from Phase 2).

**Spec:** `docs/ARCHITECTURE.md` (sections *Fuente de datos*, *Layout de datos*, *Corpus manifest*), `docs/ROADMAP.md` (*Fase 1 en detalle*), `docs/DECISIONS.md` (ADR-003, ADR-004, ADR-011, ADR-012).

## Global Constraints

- `requires-python = ">=3.12,<3.13"`; run everything with `uv run`.
- Code, identifiers, file names in English. CLI help text, docs in Spanish (ADR-011).
- No comments in code except an optional one-line module header.
- `data/raw/` is never overwritten unless `--force` (ADR-012). Every raw file has `fetched_at` and `sha256` in a sibling `meta.json` or `manifest.json`.
- Infoleg text URLs return 403 without a browser `User-Agent`. Default UA: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36`.
- Minimum interval between Infoleg requests: 0.5 s (configurable).
- Tests never touch the network: `respx` mocks all `httpx` traffic; ZIP fixtures are built in `tmp_path`.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01X9PTzEP62xfYRS8W8iGP9a
  ```

## Verified facts about the source (2026-09-12)

| Fact | Value |
|---|---|
| Catalog ZIP URL | `https://datos.jus.gob.ar/dataset/d9a963ea-8b1d-4ca3-9dd9-07a4773e8c23/resource/bf0ec116-ad4e-4572-a476-e57167a84403/download/base-infoleg-normativa-nacional.zip` (≈50 MB, contains one CSV of 256 MB, 428,380 rows) |
| Modificatorias ZIP URL | `https://datos.jus.gob.ar/dataset/d9a963ea-8b1d-4ca3-9dd9-07a4773e8c23/resource/dea3c247-5a5d-408f-a224-39ae0f8eb371/download/base-complementaria-infoleg-normas-modificatorias.zip` (CSV 60 MB, 377,755 rows) |
| Modificadas ZIP URL | `https://datos.jus.gob.ar/dataset/d9a963ea-8b1d-4ca3-9dd9-07a4773e8c23/resource/0c4fdafe-f4e8-4ac2-bc2e-acf50c27066d/download/base-complementaria-infoleg-normas-modificadas.zip` |
| Catalog CSV columns | `id_norma,tipo_norma,numero_norma,clase_norma,organismo_origen,fecha_sancion,numero_boletin,fecha_boletin,pagina_boletin,titulo_resumido,titulo_sumario,texto_resumido,observaciones,texto_original,texto_actualizado,modificada_por,modifica_a` |
| Relations CSV columns | `id_norma_modificatoria,id_norma_modificada,tipo_norma,nro_norma,clase_norma,organismo_origen,fecha_boletin,titulo_sumario,titulo_resumido` |
| CSV encoding | UTF-8 with BOM, comma-delimited, all fields quoted, dates `YYYY-MM-DD`, empty string for null |
| Seeds → id_norma | 20744→25552 (texact yes), 24013→412 (yes), 25323→64555 (no texact), 25877→93595 (yes), 27742→401266 (no), 27802→423680 (no) |
| Text URL pattern | `http://servicios.infoleg.gob.ar/infolegInternet/anexos/<lo>-<hi>/<id>/norma.htm` and `.../texact.htm` (taken verbatim from the CSV, never constructed) |
| Vínculos URL pattern | `http://servicios.infoleg.gob.ar/infolegInternet/verVinculos.do?modo=1&id=<id>` (modifica a) and `modo=2` (modificada por) |
| LCT modifying norms in relations CSV | 263 rows with `id_norma_modificada = 25552` |

## File Structure

```
pyproject.toml                       project, deps, ruff/pyright/pytest config, `legal-ai` script
.python-version                      3.12
.env.example                         LEGAL_AI_* and API key placeholders
docker-compose.yml                   postgres (ParadeDB) only, for Phase 2+
corpus/laboral.yaml                  the corpus manifest
src/legal_ai/__init__.py
src/legal_ai/settings.py             Settings (pydantic-settings): data_dir, UA, min interval
src/legal_ai/cli.py                  root typer app, mounts `ingest`
src/legal_ai/ingest/__init__.py
src/legal_ai/ingest/layout.py        RawLayout / ProcessedLayout: all paths under data/ in one place
src/legal_ai/ingest/catalog.py       download the 3 ZIPs into a dated snapshot + manifest.json
src/legal_ai/ingest/catalog_reader.py  NormRow / RelationRow models, streaming CSV-in-ZIP readers, Catalog protocol
src/legal_ai/ingest/manifest.py      CorpusManifest (YAML) and resolve_corpus → ResolvedCorpus
src/legal_ai/ingest/fetch.py         InfolegClient (UA, rate limit, retries) and fetch_norm (cache, meta.json)
src/legal_ai/ingest/cli.py           `legal-ai ingest catalog|resolve|fetch`
tests/conftest.py                    shared fixtures: tmp layout, fixture ZIP builder
tests/ingest/test_layout.py
tests/ingest/test_catalog.py
tests/ingest/test_catalog_reader.py
tests/ingest/test_manifest.py
tests/ingest/test_fetch.py
tests/ingest/test_cli.py
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.env.example`, `docker-compose.yml`, `corpus/laboral.yaml`, `src/legal_ai/__init__.py`, `src/legal_ai/settings.py`, `src/legal_ai/cli.py`, `src/legal_ai/ingest/__init__.py`, `tests/__init__.py`, `tests/ingest/__init__.py`, `tests/test_settings.py`
- Modify: `README.md` (nothing yet; leave as is)

**Interfaces:**
- Produces: `legal_ai.settings.Settings` with `data_dir: Path`, `infoleg_user_agent: str`, `infoleg_min_interval_seconds: float`; `legal_ai.settings.get_settings() -> Settings`. `legal_ai.cli.app` (typer.Typer).

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "legal-ai"
version = "0.1.0"
description = "Laboratorio de RAG sobre legislación argentina (Infoleg)"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "pyyaml>=6.0",
    "typer>=0.12",
]

[dependency-groups]
dev = [
    "pyright>=1.1.380",
    "pytest>=8.3",
    "respx>=0.21",
    "ruff>=0.6",
    "types-pyyaml>=6.0",
]

[project.scripts]
legal-ai = "legal_ai.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/legal_ai"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pyright]
pythonVersion = "3.12"
venvPath = "."
venv = ".venv"
include = ["src", "tests"]
typeCheckingMode = "standard"
```

- [ ] **Step 2: Write .python-version, .env.example, docker-compose.yml**

`.python-version`:
```
3.12
```

`.env.example`:
```
LEGAL_AI_DATA_DIR=data
LEGAL_AI_INFOLEG_MIN_INTERVAL_SECONDS=0.5
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
COHERE_API_KEY=
POSTGRES_USER=legal_ai
POSTGRES_PASSWORD=legal_ai
POSTGRES_DB=legal_ai
POSTGRES_PORT=5432
```

`docker-compose.yml`:
```yaml
services:
  postgres:
    image: paradedb/paradedb:0.25.9-pg17
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-legal_ai}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-legal_ai}
      POSTGRES_DB: ${POSTGRES_DB:-legal_ai}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-legal_ai} -d ${POSTGRES_DB:-legal_ai}"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

- [ ] **Step 3: Write corpus/laboral.yaml**

```yaml
name: laboral
description: Ley de Contrato de Trabajo y su entorno normativo
seeds:
  - {tipo: Ley, numero: 20744, why: "Ley de Contrato de Trabajo, núcleo del corpus"}
  - {tipo: Ley, numero: 24013, why: "Ley Nacional de Empleo: registración, multas, despido"}
  - {tipo: Ley, numero: 25323, why: "agravamiento indemnizatorio por falta de registración"}
  - {tipo: Ley, numero: 25877, why: "régimen de ordenamiento laboral 2004: preaviso, período de prueba"}
  - {tipo: Ley, numero: 27742, why: "Ley Bases 2024: reforma laboral"}
  - {tipo: Ley, numero: 27802, why: "reforma laboral 2026"}
expand:
  modificatorias_de_seeds: true
  max_depth: 1
  tipos: [Ley, Decreto]
```

- [ ] **Step 4: Write the failing settings test**

`tests/__init__.py` and `tests/ingest/__init__.py`: empty files.

`tests/test_settings.py`:
```python
from pathlib import Path

from legal_ai.settings import Settings


def test_defaults_point_to_local_data_dir(monkeypatch):
    monkeypatch.delenv("LEGAL_AI_DATA_DIR", raising=False)
    settings = Settings(_env_file=None)
    assert settings.data_dir == Path("data")
    assert settings.infoleg_min_interval_seconds == 0.5
    assert "Mozilla/5.0" in settings.infoleg_user_agent


def test_env_overrides_data_dir(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_DATA_DIR", "/tmp/somewhere")
    settings = Settings(_env_file=None)
    assert settings.data_dir == Path("/tmp/somewhere")
```

- [ ] **Step 5: Install and run the test to verify it fails**

Run: `uv sync && uv run pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'legal_ai.settings'`

- [ ] **Step 6: Write settings and CLI root**

`src/legal_ai/__init__.py`: empty.

`src/legal_ai/settings.py`:
```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGAL_AI_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    infoleg_user_agent: str = DEFAULT_USER_AGENT
    infoleg_min_interval_seconds: float = 0.5
    infoleg_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`src/legal_ai/ingest/__init__.py`: empty.

`src/legal_ai/cli.py`:
```python
import typer

app = typer.Typer(help="Legal AI Argentina: herramientas de ingestion, indexado y evaluación.")


@app.callback()
def main() -> None:
    pass
```

- [ ] **Step 7: Run tests, lint, type-check**

Run: `uv run pytest tests/test_settings.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run legal-ai --help`
Expected: 2 passed; ruff clean; pyright 0 errors; help text printed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock .python-version .env.example docker-compose.yml corpus src tests
git commit -m "Scaffold Python project, settings, CLI root and corpus manifest"
```

---

### Task 2: Raw/processed layout

**Files:**
- Create: `src/legal_ai/ingest/layout.py`, `tests/ingest/test_layout.py`

**Interfaces:**
- Produces:
  ```python
  class RawLayout:
      def __init__(self, data_dir: Path) -> None
      root: Path                      # data_dir / "raw" / "infoleg"
      def catalog_dir(self, date: datetime.date) -> Path   # root/catalog/YYYY-MM-DD
      def catalog_dates(self) -> list[datetime.date]       # sorted ascending, from existing dirs
      def norm_dir(self, id_norma: int) -> Path             # root/normas/<id>
  class ProcessedLayout:
      def __init__(self, data_dir: Path) -> None
      def corpus_dir(self, name: str) -> Path              # data_dir/processed/<name>
      def resolved_path(self, name: str) -> Path           # corpus_dir/resolved.json
  ```

- [ ] **Step 1: Write the failing tests**

`tests/ingest/test_layout.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_layout.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/ingest/layout.py`:
```python
from datetime import date
from pathlib import Path


class RawLayout:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "raw" / "infoleg"

    def catalog_dir(self, snapshot_date: date) -> Path:
        return self.root / "catalog" / snapshot_date.isoformat()

    def catalog_dates(self) -> list[date]:
        catalog_root = self.root / "catalog"
        if not catalog_root.exists():
            return []
        dates: list[date] = []
        for child in catalog_root.iterdir():
            if not child.is_dir():
                continue
            try:
                dates.append(date.fromisoformat(child.name))
            except ValueError:
                continue
        return sorted(dates)

    def norm_dir(self, id_norma: int) -> Path:
        return self.root / "normas" / str(id_norma)


class ProcessedLayout:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "processed"

    def corpus_dir(self, name: str) -> Path:
        return self.root / name

    def resolved_path(self, name: str) -> Path:
        return self.corpus_dir(name) / "resolved.json"
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/ingest/test_layout.py -v && uv run ruff check . && uv run pyright`
Expected: 4 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/ingest/layout.py tests/ingest/test_layout.py
git commit -m "Add raw/processed data layout"
```

---

### Task 3: Catalog snapshot download

**Files:**
- Create: `src/legal_ai/ingest/catalog.py`, `tests/ingest/test_catalog.py`

**Interfaces:**
- Consumes: `RawLayout` from Task 2.
- Produces:
  ```python
  class CatalogResource(BaseModel): name: str; filename: str; url: str
  CATALOG_RESOURCES: tuple[CatalogResource, ...]   # names: "normas", "modificatorias", "modificadas"
  class ResourceRecord(BaseModel): name: str; filename: str; url: str; sha256: str; size_bytes: int
  class CatalogSnapshot(BaseModel):
      snapshot_date: date; fetched_at: datetime; resources: list[ResourceRecord]
      def path_for(self, name: str, layout: RawLayout) -> Path
  def download_catalog(layout: RawLayout, http: httpx.Client, snapshot_date: date, *, force: bool = False) -> CatalogSnapshot
  def load_snapshot(layout: RawLayout, snapshot_date: date) -> CatalogSnapshot
  def latest_snapshot(layout: RawLayout) -> CatalogSnapshot | None
  class SnapshotExistsError(Exception)
  ```
- Manifest file: `<catalog_dir>/manifest.json` = `CatalogSnapshot.model_dump_json(indent=2)`.

- [ ] **Step 1: Write the failing tests**

`tests/ingest/test_catalog.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/ingest/catalog.py`:
```python
import hashlib
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel

from legal_ai.ingest.layout import RawLayout

DATASET_BASE = "https://datos.jus.gob.ar/dataset/d9a963ea-8b1d-4ca3-9dd9-07a4773e8c23/resource"


class CatalogResource(BaseModel):
    name: str
    filename: str
    url: str


CATALOG_RESOURCES: tuple[CatalogResource, ...] = (
    CatalogResource(
        name="normas",
        filename="base-infoleg-normativa-nacional.zip",
        url=f"{DATASET_BASE}/bf0ec116-ad4e-4572-a476-e57167a84403/download/base-infoleg-normativa-nacional.zip",
    ),
    CatalogResource(
        name="modificatorias",
        filename="base-complementaria-infoleg-normas-modificatorias.zip",
        url=f"{DATASET_BASE}/dea3c247-5a5d-408f-a224-39ae0f8eb371/download/base-complementaria-infoleg-normas-modificatorias.zip",
    ),
    CatalogResource(
        name="modificadas",
        filename="base-complementaria-infoleg-normas-modificadas.zip",
        url=f"{DATASET_BASE}/0c4fdafe-f4e8-4ac2-bc2e-acf50c27066d/download/base-complementaria-infoleg-normas-modificadas.zip",
    ),
)

MANIFEST_NAME = "manifest.json"


class SnapshotExistsError(Exception):
    pass


class ResourceRecord(BaseModel):
    name: str
    filename: str
    url: str
    sha256: str
    size_bytes: int


class CatalogSnapshot(BaseModel):
    snapshot_date: date
    fetched_at: datetime
    resources: list[ResourceRecord]

    def path_for(self, name: str, layout: RawLayout) -> Path:
        record = next(r for r in self.resources if r.name == name)
        return layout.catalog_dir(self.snapshot_date) / record.filename


def _stream_to_file(http: httpx.Client, url: str, dest: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with http.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    return digest.hexdigest(), size


def download_catalog(
    layout: RawLayout, http: httpx.Client, snapshot_date: date, *, force: bool = False
) -> CatalogSnapshot:
    target = layout.catalog_dir(snapshot_date)
    if target.exists():
        if not force:
            raise SnapshotExistsError(f"{target} ya existe; usá --force para reemplazarlo")
        shutil.rmtree(target)
    staging = target.with_name(target.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        records: list[ResourceRecord] = []
        for resource in CATALOG_RESOURCES:
            sha256, size = _stream_to_file(http, resource.url, staging / resource.filename)
            records.append(
                ResourceRecord(
                    name=resource.name,
                    filename=resource.filename,
                    url=resource.url,
                    sha256=sha256,
                    size_bytes=size,
                )
            )
        snapshot = CatalogSnapshot(
            snapshot_date=snapshot_date, fetched_at=datetime.now(UTC), resources=records
        )
        (staging / MANIFEST_NAME).write_text(snapshot.model_dump_json(indent=2))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    staging.rename(target)
    return snapshot


def load_snapshot(layout: RawLayout, snapshot_date: date) -> CatalogSnapshot:
    manifest = layout.catalog_dir(snapshot_date) / MANIFEST_NAME
    return CatalogSnapshot.model_validate_json(manifest.read_text())


def latest_snapshot(layout: RawLayout) -> CatalogSnapshot | None:
    dates = [d for d in layout.catalog_dates() if (layout.catalog_dir(d) / MANIFEST_NAME).exists()]
    if not dates:
        return None
    return load_snapshot(layout, dates[-1])
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/ingest/test_catalog.py -v && uv run ruff check . && uv run pyright`
Expected: 4 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/ingest/catalog.py tests/ingest/test_catalog.py
git commit -m "Download Infoleg catalog ZIPs into dated, hashed snapshots"
```

---

### Task 4: Streaming catalog reader

**Files:**
- Create: `src/legal_ai/ingest/catalog_reader.py`, `tests/conftest.py`, `tests/ingest/test_catalog_reader.py`

**Interfaces:**
- Consumes: `CatalogSnapshot`, `RawLayout`.
- Produces:
  ```python
  class NormRow(BaseModel):
      id_norma: int; tipo_norma: str; numero_norma: str
      clase_norma: str | None; organismo_origen: str | None
      fecha_sancion: date | None; numero_boletin: int | None; fecha_boletin: date | None
      pagina_boletin: int | None; titulo_resumido: str | None; titulo_sumario: str | None
      texto_resumido: str | None; observaciones: str | None
      texto_original: str | None; texto_actualizado: str | None
      modificada_por: int = 0; modifica_a: int = 0
  class RelationRow(BaseModel):
      id_norma_modificatoria: int; id_norma_modificada: int
      tipo_norma: str; nro_norma: str; fecha_boletin: date | None
  def iter_norms(zip_path: Path) -> Iterator[NormRow]
  def iter_relations(zip_path: Path) -> Iterator[RelationRow]
  class Catalog(Protocol):
      def norms(self) -> Iterable[NormRow]: ...
      def relations(self) -> Iterable[RelationRow]: ...
  class ZipCatalog(Catalog):  __init__(self, snapshot: CatalogSnapshot, layout: RawLayout)
  class InMemoryCatalog(Catalog): __init__(self, norms: list[NormRow], relations: list[RelationRow])
  ```
- Empty CSV strings become `None` (or the default for int counters). `S/N` stays as the string `"S/N"` in `numero_norma`.

- [ ] **Step 1: Write conftest with a ZIP fixture builder**

`tests/conftest.py`:
```python
import csv
import io
import zipfile
from pathlib import Path

import pytest

NORM_COLUMNS = [
    "id_norma", "tipo_norma", "numero_norma", "clase_norma", "organismo_origen",
    "fecha_sancion", "numero_boletin", "fecha_boletin", "pagina_boletin",
    "titulo_resumido", "titulo_sumario", "texto_resumido", "observaciones",
    "texto_original", "texto_actualizado", "modificada_por", "modifica_a",
]
RELATION_COLUMNS = [
    "id_norma_modificatoria", "id_norma_modificada", "tipo_norma", "nro_norma",
    "clase_norma", "organismo_origen", "fecha_boletin", "titulo_sumario", "titulo_resumido",
]


def write_csv_zip(path: Path, inner_name: str, columns: list[str], rows: list[dict[str, str]]) -> Path:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_name, ("﻿" + buffer.getvalue()).encode("utf-8"))
    return path


LCT = {
    "id_norma": "25552", "tipo_norma": "Ley", "numero_norma": "20744",
    "organismo_origen": "HONORABLE CONGRESO DE LA NACION ARGENTINA",
    "fecha_sancion": "1974-09-05", "numero_boletin": "23003", "fecha_boletin": "1974-09-27",
    "pagina_boletin": "2", "titulo_resumido": "REGIMEN", "titulo_sumario": "LEY DE CONTRATO DE TRABAJO",
    "texto_resumido": "REGIMEN DEL CONTRATO DE TRABAJO.",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/norma.htm",
    "texto_actualizado": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/texact.htm",
    "modificada_por": "263", "modifica_a": "21",
}
LEY_BASES = {
    "id_norma": "401266", "tipo_norma": "Ley", "numero_norma": "27742",
    "fecha_sancion": "2024-06-27", "fecha_boletin": "2024-07-08",
    "titulo_sumario": "BASES Y PUNTOS DE PARTIDA PARA LA LIBERTAD DE LOS ARGENTINOS",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/400000-404999/401266/norma.htm",
    "modificada_por": "116", "modifica_a": "38",
}
DECRETO_390 = {
    "id_norma": "229909", "tipo_norma": "Decreto", "numero_norma": "390",
    "fecha_sancion": "1976-05-13", "fecha_boletin": "1976-05-21",
    "titulo_sumario": "CONTRATO DE TRABAJO",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/225000-229999/229909/norma.htm",
}
RESOLUCION_X = {
    "id_norma": "999001", "tipo_norma": "Resolución", "numero_norma": "15",
    "fecha_boletin": "2022-11-11", "titulo_sumario": "ALGO",
    "texto_original": "http://servicios.infoleg.gob.ar/infolegInternet/anexos/995000-999999/999001/norma.htm",
}
LEY_SN = {"id_norma": "183290", "tipo_norma": "Ley", "numero_norma": "S/N", "fecha_boletin": "1853-05-25"}
LEY_1_A = {"id_norma": "1001", "tipo_norma": "Ley", "numero_norma": "1", "fecha_sancion": "1862-09-01"}
LEY_1_B = {"id_norma": "1002", "tipo_norma": "Ley", "numero_norma": "1", "fecha_sancion": "1900-01-01"}

FIXTURE_NORMS = [LCT, LEY_BASES, DECRETO_390, RESOLUCION_X, LEY_SN, LEY_1_A, LEY_1_B]
FIXTURE_RELATIONS = [
    {"id_norma_modificatoria": "401266", "id_norma_modificada": "25552", "tipo_norma": "Ley",
     "nro_norma": "20744", "fecha_boletin": "1974-09-27"},
    {"id_norma_modificatoria": "229909", "id_norma_modificada": "25552", "tipo_norma": "Ley",
     "nro_norma": "20744", "fecha_boletin": "1974-09-27"},
    {"id_norma_modificatoria": "999001", "id_norma_modificada": "25552", "tipo_norma": "Ley",
     "nro_norma": "20744", "fecha_boletin": "1974-09-27"},
    {"id_norma_modificatoria": "25552", "id_norma_modificada": "1001", "tipo_norma": "Ley",
     "nro_norma": "1", "fecha_boletin": ""},
]


@pytest.fixture
def norms_zip(tmp_path: Path) -> Path:
    return write_csv_zip(
        tmp_path / "normas.zip", "base-infoleg-normativa-nacional.csv", NORM_COLUMNS, FIXTURE_NORMS
    )


@pytest.fixture
def relations_zip(tmp_path: Path) -> Path:
    return write_csv_zip(
        tmp_path / "modificatorias.zip",
        "base-complementaria-infoleg-normas-modificatorias.csv",
        RELATION_COLUMNS,
        FIXTURE_RELATIONS,
    )
```

- [ ] **Step 2: Write the failing tests**

`tests/ingest/test_catalog_reader.py`:
```python
from datetime import date
from pathlib import Path

from legal_ai.ingest.catalog_reader import (
    InMemoryCatalog,
    NormRow,
    RelationRow,
    iter_norms,
    iter_relations,
)


def test_iter_norms_parses_types_and_nulls(norms_zip: Path):
    rows = list(iter_norms(norms_zip))
    assert len(rows) == 7
    lct = next(r for r in rows if r.id_norma == 25552)
    assert lct.tipo_norma == "Ley"
    assert lct.numero_norma == "20744"
    assert lct.fecha_sancion == date(1974, 9, 5)
    assert lct.fecha_boletin == date(1974, 9, 27)
    assert lct.numero_boletin == 23003
    assert lct.modificada_por == 263
    assert lct.texto_actualizado is not None and lct.texto_actualizado.endswith("/texact.htm")

    bases = next(r for r in rows if r.id_norma == 401266)
    assert bases.texto_actualizado is None
    assert bases.clase_norma is None
    assert bases.pagina_boletin is None

    sn = next(r for r in rows if r.id_norma == 183290)
    assert sn.numero_norma == "S/N"
    assert sn.modificada_por == 0
    assert sn.fecha_sancion is None


def test_iter_relations_parses_ids_and_dates(relations_zip: Path):
    rows = list(iter_relations(relations_zip))
    assert len(rows) == 4
    first = rows[0]
    assert first.id_norma_modificatoria == 401266
    assert first.id_norma_modificada == 25552
    assert first.fecha_boletin == date(1974, 9, 27)
    assert rows[3].fecha_boletin is None


def test_in_memory_catalog_is_re_iterable():
    catalog = InMemoryCatalog(
        norms=[NormRow(id_norma=1, tipo_norma="Ley", numero_norma="1")],
        relations=[RelationRow(id_norma_modificatoria=2, id_norma_modificada=1, tipo_norma="Ley", nro_norma="1")],
    )
    assert len(list(catalog.norms())) == 1
    assert len(list(catalog.norms())) == 1
    assert len(list(catalog.relations())) == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_catalog_reader.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement**

`src/legal_ai/ingest/catalog_reader.py`:
```python
import csv
import io
import zipfile
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, model_validator

from legal_ai.ingest.catalog import CatalogSnapshot
from legal_ai.ingest.layout import RawLayout

csv.field_size_limit(1 << 30)


def _drop_empty(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if v != ""}
    return data


class NormRow(BaseModel):
    id_norma: int
    tipo_norma: str
    numero_norma: str
    clase_norma: str | None = None
    organismo_origen: str | None = None
    fecha_sancion: date | None = None
    numero_boletin: int | None = None
    fecha_boletin: date | None = None
    pagina_boletin: int | None = None
    titulo_resumido: str | None = None
    titulo_sumario: str | None = None
    texto_resumido: str | None = None
    observaciones: str | None = None
    texto_original: str | None = None
    texto_actualizado: str | None = None
    modificada_por: int = 0
    modifica_a: int = 0

    _clean = model_validator(mode="before")(_drop_empty)


class RelationRow(BaseModel):
    id_norma_modificatoria: int
    id_norma_modificada: int
    tipo_norma: str
    nro_norma: str
    fecha_boletin: date | None = None

    _clean = model_validator(mode="before")(_drop_empty)


def _iter_csv_rows(zip_path: Path) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(zip_path) as zf:
        inner = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(inner) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            yield from csv.DictReader(text)


def iter_norms(zip_path: Path) -> Iterator[NormRow]:
    for row in _iter_csv_rows(zip_path):
        yield NormRow.model_validate(row)


def iter_relations(zip_path: Path) -> Iterator[RelationRow]:
    for row in _iter_csv_rows(zip_path):
        yield RelationRow.model_validate(row)


class Catalog(Protocol):
    def norms(self) -> Iterable[NormRow]: ...

    def relations(self) -> Iterable[RelationRow]: ...


class ZipCatalog:
    def __init__(self, snapshot: CatalogSnapshot, layout: RawLayout) -> None:
        self.snapshot = snapshot
        self.layout = layout

    def norms(self) -> Iterable[NormRow]:
        return iter_norms(self.snapshot.path_for("normas", self.layout))

    def relations(self) -> Iterable[RelationRow]:
        return iter_relations(self.snapshot.path_for("modificatorias", self.layout))


class InMemoryCatalog:
    def __init__(self, norms: list[NormRow], relations: list[RelationRow]) -> None:
        self._norms = norms
        self._relations = relations

    def norms(self) -> Iterable[NormRow]:
        return list(self._norms)

    def relations(self) -> Iterable[RelationRow]:
        return list(self._relations)
```

- [ ] **Step 5: Run tests, lint, types**

Run: `uv run pytest tests/ingest/test_catalog_reader.py -v && uv run ruff check . && uv run pyright`
Expected: 3 passed, clean. If pyright complains about `_clean = model_validator(...)(_drop_empty)`, replace with a classmethod inside each model:
```python
    @model_validator(mode="before")
    @classmethod
    def _clean(cls, data: Any) -> Any:
        return _drop_empty(data)
```

- [ ] **Step 6: Commit**

```bash
git add src/legal_ai/ingest/catalog_reader.py tests/conftest.py tests/ingest/test_catalog_reader.py
git commit -m "Stream Infoleg catalog CSVs from ZIP into typed rows"
```

---

### Task 5: Corpus manifest and resolution

**Files:**
- Create: `src/legal_ai/ingest/manifest.py`, `tests/ingest/test_manifest.py`

**Interfaces:**
- Consumes: `Catalog`, `NormRow`, `RelationRow` from Task 4; `ProcessedLayout` from Task 2.
- Produces:
  ```python
  class Seed(BaseModel): tipo: str; numero: int; why: str; sancion_year: int | None = None
  class Expand(BaseModel): modificatorias_de_seeds: bool = True; max_depth: int = 1; tipos: list[str] = ["Ley", "Decreto"]
  class CorpusManifest(BaseModel): name: str; description: str; seeds: list[Seed]; expand: Expand = Expand()
  def load_manifest(path: Path) -> CorpusManifest
  class ResolvedNorm(BaseModel):
      id_norma: int; tipo_norma: str; numero_norma: str; fecha_boletin: date | None
      titulo_sumario: str | None; url_original: str | None; url_actualizado: str | None
      reason: str; depth: int
  class ResolvedCorpus(BaseModel):
      name: str; catalog_date: date; resolved_at: datetime; norms: list[ResolvedNorm]
      def ids(self) -> list[int]
  class SeedNotFoundError(Exception); class AmbiguousSeedError(Exception)
  def resolve_corpus(manifest: CorpusManifest, catalog: Catalog, catalog_date: date) -> ResolvedCorpus
  def write_resolved(corpus: ResolvedCorpus, path: Path) -> None
  def read_resolved(path: Path) -> ResolvedCorpus
  ```
- `reason` is `"seed"` for seeds and `"modifies:<seed id_norma>"` for expanded norms. Expanded norms are filtered by `expand.tipos`. Seeds are never filtered. Output sorted by `depth` then `id_norma`. A norm reached both as seed and as modifier keeps `reason="seed"`, `depth=0`.

- [ ] **Step 1: Write the failing tests**

`tests/ingest/test_manifest.py`:
```python
from datetime import date
from pathlib import Path

import pytest

from legal_ai.ingest.catalog_reader import InMemoryCatalog, NormRow, RelationRow
from legal_ai.ingest.manifest import (
    AmbiguousSeedError,
    CorpusManifest,
    Expand,
    Seed,
    SeedNotFoundError,
    load_manifest,
    read_resolved,
    resolve_corpus,
    write_resolved,
)
from tests.conftest import FIXTURE_NORMS, FIXTURE_RELATIONS


def make_catalog() -> InMemoryCatalog:
    return InMemoryCatalog(
        norms=[NormRow.model_validate(r) for r in FIXTURE_NORMS],
        relations=[RelationRow.model_validate(r) for r in FIXTURE_RELATIONS],
    )


def test_load_manifest_from_repo_yaml():
    manifest = load_manifest(Path("corpus/laboral.yaml"))
    assert manifest.name == "laboral"
    assert [s.numero for s in manifest.seeds] == [20744, 24013, 25323, 25877, 27742, 27802]
    assert manifest.expand.tipos == ["Ley", "Decreto"]


def test_resolve_seeds_and_expand_depth_1_filtered_by_tipo():
    manifest = CorpusManifest(
        name="t", description="", seeds=[Seed(tipo="Ley", numero=20744, why="x")]
    )
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))

    by_id = {n.id_norma: n for n in corpus.norms}
    assert corpus.name == "t"
    assert corpus.catalog_date == date(2026, 9, 12)
    assert by_id[25552].reason == "seed" and by_id[25552].depth == 0
    assert by_id[25552].url_actualizado is not None
    assert by_id[401266].reason == "modifies:25552" and by_id[401266].depth == 1
    assert by_id[229909].tipo_norma == "Decreto"
    assert 999001 not in by_id
    assert corpus.ids() == [25552, 229909, 401266]


def test_seed_that_is_also_modifier_stays_seed():
    manifest = CorpusManifest(
        name="t", description="",
        seeds=[Seed(tipo="Ley", numero=20744, why="x"), Seed(tipo="Ley", numero=27742, why="y")],
    )
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))
    bases = next(n for n in corpus.norms if n.id_norma == 401266)
    assert bases.reason == "seed" and bases.depth == 0


def test_expand_disabled_returns_only_seeds():
    manifest = CorpusManifest(
        name="t", description="", seeds=[Seed(tipo="Ley", numero=20744, why="x")],
        expand=Expand(modificatorias_de_seeds=False),
    )
    assert resolve_corpus(manifest, make_catalog(), date(2026, 9, 12)).ids() == [25552]


def test_missing_seed_raises():
    manifest = CorpusManifest(name="t", description="", seeds=[Seed(tipo="Ley", numero=99999, why="x")])
    with pytest.raises(SeedNotFoundError, match="99999"):
        resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))


def test_ambiguous_seed_raises_unless_year_given():
    ambiguous = CorpusManifest(name="t", description="", seeds=[Seed(tipo="Ley", numero=1, why="x")])
    with pytest.raises(AmbiguousSeedError, match="1001, 1002"):
        resolve_corpus(ambiguous, make_catalog(), date(2026, 9, 12))

    precise = CorpusManifest(
        name="t", description="",
        seeds=[Seed(tipo="Ley", numero=1, why="x", sancion_year=1900)],
        expand=Expand(modificatorias_de_seeds=False),
    )
    assert resolve_corpus(precise, make_catalog(), date(2026, 9, 12)).ids() == [1002]


def test_write_and_read_resolved_roundtrip(tmp_path: Path):
    manifest = CorpusManifest(name="t", description="", seeds=[Seed(tipo="Ley", numero=20744, why="x")])
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))
    path = tmp_path / "processed" / "t" / "resolved.json"
    write_resolved(corpus, path)
    assert read_resolved(path) == corpus
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/ingest/manifest.py`:
```python
from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from legal_ai.ingest.catalog_reader import Catalog, NormRow


class Seed(BaseModel):
    tipo: str
    numero: int
    why: str
    sancion_year: int | None = None


class Expand(BaseModel):
    modificatorias_de_seeds: bool = True
    max_depth: int = 1
    tipos: list[str] = Field(default_factory=lambda: ["Ley", "Decreto"])


class CorpusManifest(BaseModel):
    name: str
    description: str
    seeds: list[Seed]
    expand: Expand = Field(default_factory=Expand)


def load_manifest(path: Path) -> CorpusManifest:
    with path.open(encoding="utf-8") as fh:
        return CorpusManifest.model_validate(yaml.safe_load(fh))


class ResolvedNorm(BaseModel):
    id_norma: int
    tipo_norma: str
    numero_norma: str
    fecha_boletin: date | None
    titulo_sumario: str | None
    url_original: str | None
    url_actualizado: str | None
    reason: str
    depth: int


class ResolvedCorpus(BaseModel):
    name: str
    catalog_date: date
    resolved_at: datetime
    norms: list[ResolvedNorm]

    def ids(self) -> list[int]:
        return [n.id_norma for n in self.norms]


class SeedNotFoundError(Exception):
    pass


class AmbiguousSeedError(Exception):
    pass


def _matches(seed: Seed, row: NormRow) -> bool:
    if row.tipo_norma != seed.tipo or row.numero_norma != str(seed.numero):
        return False
    if seed.sancion_year is None:
        return True
    return row.fecha_sancion is not None and row.fecha_sancion.year == seed.sancion_year


def _to_resolved(row: NormRow, reason: str, depth: int) -> ResolvedNorm:
    return ResolvedNorm(
        id_norma=row.id_norma,
        tipo_norma=row.tipo_norma,
        numero_norma=row.numero_norma,
        fecha_boletin=row.fecha_boletin,
        titulo_sumario=row.titulo_sumario,
        url_original=row.texto_original,
        url_actualizado=row.texto_actualizado,
        reason=reason,
        depth=depth,
    )


def _find_seeds(manifest: CorpusManifest, catalog: Catalog) -> dict[int, ResolvedNorm]:
    candidates: dict[int, list[NormRow]] = {i: [] for i in range(len(manifest.seeds))}
    for row in catalog.norms():
        for i, seed in enumerate(manifest.seeds):
            if _matches(seed, row):
                candidates[i].append(row)
    resolved: dict[int, ResolvedNorm] = {}
    for i, seed in enumerate(manifest.seeds):
        rows = candidates[i]
        if not rows:
            raise SeedNotFoundError(f"{seed.tipo} {seed.numero} no está en el catálogo")
        if len(rows) > 1:
            ids = ", ".join(str(r.id_norma) for r in sorted(rows, key=lambda r: r.id_norma))
            raise AmbiguousSeedError(
                f"{seed.tipo} {seed.numero} coincide con varias normas ({ids}); agregá sancion_year"
            )
        row = rows[0]
        resolved[row.id_norma] = _to_resolved(row, "seed", 0)
    return resolved


def _expand_once(
    frontier: set[int], known: dict[int, ResolvedNorm], catalog: Catalog, tipos: list[str], depth: int
) -> dict[int, ResolvedNorm]:
    parent_of: dict[int, int] = {}
    for rel in catalog.relations():
        if rel.id_norma_modificada in frontier and rel.id_norma_modificatoria not in known:
            parent_of.setdefault(rel.id_norma_modificatoria, rel.id_norma_modificada)
    if not parent_of:
        return {}
    added: dict[int, ResolvedNorm] = {}
    for row in catalog.norms():
        parent = parent_of.get(row.id_norma)
        if parent is not None and row.tipo_norma in tipos:
            added[row.id_norma] = _to_resolved(row, f"modifies:{parent}", depth)
    return added


def resolve_corpus(manifest: CorpusManifest, catalog: Catalog, catalog_date: date) -> ResolvedCorpus:
    known = _find_seeds(manifest, catalog)
    frontier = set(known)
    if manifest.expand.modificatorias_de_seeds:
        for depth in range(1, manifest.expand.max_depth + 1):
            added = _expand_once(frontier, known, catalog, manifest.expand.tipos, depth)
            if not added:
                break
            known.update(added)
            frontier = set(added)
    norms = sorted(known.values(), key=lambda n: (n.depth, n.id_norma))
    return ResolvedCorpus(
        name=manifest.name, catalog_date=catalog_date, resolved_at=datetime.now(UTC), norms=norms
    )


def write_resolved(corpus: ResolvedCorpus, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")


def read_resolved(path: Path) -> ResolvedCorpus:
    return ResolvedCorpus.model_validate_json(path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/ingest/test_manifest.py -v && uv run ruff check . && uv run pyright`
Expected: 7 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/ingest/manifest.py tests/ingest/test_manifest.py
git commit -m "Resolve corpus manifest to Infoleg ids with modifier expansion"
```

---

### Task 6: Infoleg fetcher with cache, rate limit and retries

**Files:**
- Create: `src/legal_ai/ingest/fetch.py`, `tests/ingest/test_fetch.py`

**Interfaces:**
- Consumes: `RawLayout` (Task 2), `ResolvedNorm` (Task 5), `Settings` (Task 1).
- Produces:
  ```python
  VINCULOS_URL = "http://servicios.infoleg.gob.ar/infolegInternet/verVinculos.do?modo={modo}&id={id_norma}"
  class InfolegClient:
      def __init__(self, http: httpx.Client, *, min_interval: float, max_attempts: int = 3, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None
      def get(self, url: str) -> httpx.Response     # raises httpx.HTTPStatusError after retries on 429/5xx; raises on 4xx immediately
  def norm_urls(norm: ResolvedNorm) -> dict[str, str | None]
      # keys, in order: "norma.htm", "texact.htm", "vinculos_modifica.htm", "vinculos_modificada_por.htm"
  class FileRecord(BaseModel): url: str; status_code: int; sha256: str; size_bytes: int; content_type: str | None; fetched_at: datetime
  class NormMeta(BaseModel): id_norma: int; files: dict[str, FileRecord]; missing: list[str]
  class FetchOutcome(StrEnum): FETCHED = "fetched"; CACHED = "cached"; NO_URL = "no_url"; FAILED = "failed"
  class FetchReport(BaseModel): id_norma: int; outcomes: dict[str, FetchOutcome]; errors: dict[str, str]
  def fetch_norm(client: InfolegClient, layout: RawLayout, norm: ResolvedNorm, *, force: bool = False) -> FetchReport
  ```
- `fetch_norm` writes bytes verbatim (no decoding) to `layout.norm_dir(id)/<name>` and updates `meta.json` (`NormMeta`) after each file so a crash leaves consistent metadata. A file present on disk and listed in `meta.json` is `CACHED` unless `force`. A URL that returns a non-retryable 4xx records `FAILED` with the error in `errors` and continues with the next file.

- [ ] **Step 1: Write the failing tests**

`tests/ingest/test_fetch.py`:
```python
import hashlib
import json
from pathlib import Path

import httpx
import pytest
import respx

from legal_ai.ingest.fetch import (
    VINCULOS_URL,
    FetchOutcome,
    InfolegClient,
    fetch_norm,
    norm_urls,
)
from legal_ai.ingest.layout import RawLayout
from legal_ai.ingest.manifest import ResolvedNorm
from legal_ai.settings import DEFAULT_USER_AGENT

LCT = ResolvedNorm(
    id_norma=25552, tipo_norma="Ley", numero_norma="20744", fecha_boletin=None, titulo_sumario=None,
    url_original="http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/norma.htm",
    url_actualizado="http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/texact.htm",
    reason="seed", depth=0,
)
NO_TEXACT = LCT.model_copy(update={"id_norma": 401266, "url_actualizado": None})


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def make_client(clock: FakeClock, min_interval: float = 0.5) -> InfolegClient:
    http = httpx.Client(headers={"User-Agent": DEFAULT_USER_AGENT})
    return InfolegClient(http, min_interval=min_interval, sleep=clock.sleep, clock=clock.monotonic)


def test_norm_urls_order_and_missing_texact():
    urls = norm_urls(NO_TEXACT)
    assert list(urls) == ["norma.htm", "texact.htm", "vinculos_modifica.htm", "vinculos_modificada_por.htm"]
    assert urls["texact.htm"] is None
    assert urls["vinculos_modifica.htm"] == VINCULOS_URL.format(modo=1, id_norma=401266)
    assert urls["vinculos_modificada_por.htm"] == VINCULOS_URL.format(modo=2, id_norma=401266)


@respx.mock
def test_client_sends_user_agent_and_rate_limits():
    route = respx.get("http://example.test/a").mock(return_value=httpx.Response(200, content=b"x"))
    clock = FakeClock()
    client = make_client(clock, min_interval=0.5)
    client.get("http://example.test/a")
    client.get("http://example.test/a")
    assert route.calls[0].request.headers["User-Agent"] == DEFAULT_USER_AGENT
    assert clock.sleeps == [0.5]


@respx.mock
def test_client_retries_on_5xx_then_succeeds():
    route = respx.get("http://example.test/b").mock(
        side_effect=[httpx.Response(503), httpx.Response(500), httpx.Response(200, content=b"ok")]
    )
    clock = FakeClock()
    response = make_client(clock, min_interval=0).get("http://example.test/b")
    assert response.content == b"ok"
    assert route.call_count == 3
    assert clock.sleeps == [1.0, 2.0]


@respx.mock
def test_client_gives_up_after_max_attempts():
    respx.get("http://example.test/c").mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        make_client(FakeClock(), min_interval=0).get("http://example.test/c")


@respx.mock
def test_client_does_not_retry_403():
    route = respx.get("http://example.test/d").mock(return_value=httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        make_client(FakeClock(), min_interval=0).get("http://example.test/d")
    assert route.call_count == 1


@respx.mock
def test_fetch_norm_writes_files_and_meta(tmp_path: Path):
    urls = norm_urls(LCT)
    for name, url in urls.items():
        assert url is not None
        respx.get(url).mock(
            return_value=httpx.Response(200, content=name.encode(), headers={"content-type": "text/html"})
        )
    layout = RawLayout(tmp_path)
    report = fetch_norm(make_client(FakeClock(), min_interval=0), layout, LCT)

    assert all(o == FetchOutcome.FETCHED for o in report.outcomes.values())
    norm_dir = layout.norm_dir(25552)
    assert (norm_dir / "texact.htm").read_bytes() == b"texact.htm"
    meta = json.loads((norm_dir / "meta.json").read_text())
    assert meta["id_norma"] == 25552
    assert meta["files"]["norma.htm"]["sha256"] == hashlib.sha256(b"norma.htm").hexdigest()
    assert meta["files"]["norma.htm"]["content_type"] == "text/html"
    assert meta["missing"] == []


@respx.mock
def test_fetch_norm_uses_cache_unless_force(tmp_path: Path):
    urls = norm_urls(LCT)
    routes = {
        name: respx.get(url).mock(return_value=httpx.Response(200, content=b"v1"))
        for name, url in urls.items() if url is not None
    }
    layout = RawLayout(tmp_path)
    client = make_client(FakeClock(), min_interval=0)
    fetch_norm(client, layout, LCT)
    second = fetch_norm(client, layout, LCT)
    assert all(o == FetchOutcome.CACHED for o in second.outcomes.values())
    assert all(r.call_count == 1 for r in routes.values())

    third = fetch_norm(client, layout, LCT, force=True)
    assert all(o == FetchOutcome.FETCHED for o in third.outcomes.values())
    assert all(r.call_count == 2 for r in routes.values())


@respx.mock
def test_fetch_norm_records_missing_url_and_failed_file(tmp_path: Path):
    urls = norm_urls(NO_TEXACT)
    respx.get(urls["norma.htm"]).mock(return_value=httpx.Response(404))
    respx.get(urls["vinculos_modifica.htm"]).mock(return_value=httpx.Response(200, content=b"m1"))
    respx.get(urls["vinculos_modificada_por.htm"]).mock(return_value=httpx.Response(200, content=b"m2"))
    layout = RawLayout(tmp_path)
    report = fetch_norm(make_client(FakeClock(), min_interval=0), layout, NO_TEXACT)

    assert report.outcomes["texact.htm"] == FetchOutcome.NO_URL
    assert report.outcomes["norma.htm"] == FetchOutcome.FAILED
    assert "404" in report.errors["norma.htm"]
    assert report.outcomes["vinculos_modifica.htm"] == FetchOutcome.FETCHED
    meta = json.loads((layout.norm_dir(401266) / "meta.json").read_text())
    assert meta["missing"] == ["texact.htm"]
    assert "norma.htm" not in meta["files"]
    assert not (layout.norm_dir(401266) / "norma.htm").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/ingest/fetch.py`:
```python
import hashlib
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

import httpx
from pydantic import BaseModel, Field

from legal_ai.ingest.layout import RawLayout
from legal_ai.ingest.manifest import ResolvedNorm

VINCULOS_URL = "http://servicios.infoleg.gob.ar/infolegInternet/verVinculos.do?modo={modo}&id={id_norma}"
META_NAME = "meta.json"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class InfolegClient:
    def __init__(
        self,
        http: httpx.Client,
        *,
        min_interval: float,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._min_interval = min_interval
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    def _wait_turn(self) -> None:
        if self._last_request is not None:
            elapsed = self._clock() - self._last_request
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last_request = self._clock()

    def get(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            if attempt:
                self._sleep(float(2 ** (attempt - 1)))
            self._wait_turn()
            try:
                response = self._http.get(url, follow_redirects=True)
            except httpx.TransportError as exc:
                last_error = exc
                continue
            if response.status_code in RETRYABLE_STATUS:
                last_error = httpx.HTTPStatusError(
                    f"{response.status_code} en {url}", request=response.request, response=response
                )
                continue
            response.raise_for_status()
            return response
        assert last_error is not None
        raise last_error


def norm_urls(norm: ResolvedNorm) -> dict[str, str | None]:
    return {
        "norma.htm": norm.url_original,
        "texact.htm": norm.url_actualizado,
        "vinculos_modifica.htm": VINCULOS_URL.format(modo=1, id_norma=norm.id_norma),
        "vinculos_modificada_por.htm": VINCULOS_URL.format(modo=2, id_norma=norm.id_norma),
    }


class FileRecord(BaseModel):
    url: str
    status_code: int
    sha256: str
    size_bytes: int
    content_type: str | None
    fetched_at: datetime


class NormMeta(BaseModel):
    id_norma: int
    files: dict[str, FileRecord] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)


class FetchOutcome(StrEnum):
    FETCHED = "fetched"
    CACHED = "cached"
    NO_URL = "no_url"
    FAILED = "failed"


class FetchReport(BaseModel):
    id_norma: int
    outcomes: dict[str, FetchOutcome] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)


def _load_meta(norm_dir, id_norma: int) -> NormMeta:
    path = norm_dir / META_NAME
    if path.exists():
        return NormMeta.model_validate_json(path.read_text(encoding="utf-8"))
    return NormMeta(id_norma=id_norma)


def _save_meta(norm_dir, meta: NormMeta) -> None:
    (norm_dir / META_NAME).write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def fetch_norm(
    client: InfolegClient, layout: RawLayout, norm: ResolvedNorm, *, force: bool = False
) -> FetchReport:
    norm_dir = layout.norm_dir(norm.id_norma)
    norm_dir.mkdir(parents=True, exist_ok=True)
    meta = _load_meta(norm_dir, norm.id_norma)
    report = FetchReport(id_norma=norm.id_norma)

    for name, url in norm_urls(norm).items():
        target = norm_dir / name
        if url is None:
            report.outcomes[name] = FetchOutcome.NO_URL
            if name not in meta.missing:
                meta.missing.append(name)
            continue
        if not force and name in meta.files and target.exists():
            report.outcomes[name] = FetchOutcome.CACHED
            continue
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            report.outcomes[name] = FetchOutcome.FAILED
            report.errors[name] = str(exc)
            continue
        target.write_bytes(response.content)
        meta.files[name] = FileRecord(
            url=url,
            status_code=response.status_code,
            sha256=hashlib.sha256(response.content).hexdigest(),
            size_bytes=len(response.content),
            content_type=response.headers.get("content-type"),
            fetched_at=datetime.now(UTC),
        )
        if name in meta.missing:
            meta.missing.remove(name)
        report.outcomes[name] = FetchOutcome.FETCHED
        _save_meta(norm_dir, meta)

    _save_meta(norm_dir, meta)
    return report
```

Add `from pathlib import Path` and annotate `norm_dir: Path` in `_load_meta` / `_save_meta` if pyright asks.

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/ingest/test_fetch.py -v && uv run ruff check . && uv run pyright`
Expected: 9 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/ingest/fetch.py tests/ingest/test_fetch.py
git commit -m "Fetch Infoleg norm texts with cache, rate limit and retries"
```

---

### Task 7: `legal-ai ingest` CLI

**Files:**
- Create: `src/legal_ai/ingest/cli.py`, `tests/ingest/test_cli.py`
- Modify: `src/legal_ai/cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces the commands:
  - `legal-ai ingest catalog [--date YYYY-MM-DD] [--force]` → downloads snapshot for today (or `--date`), prints the manifest path and each resource's size and sha256.
  - `legal-ai ingest resolve <corpus> [--catalog-date YYYY-MM-DD]` → reads `corpus/<corpus>.yaml`, uses latest snapshot (or the given date), writes `data/processed/<corpus>/resolved.json`, prints count by depth and tipo.
  - `legal-ai ingest fetch <corpus> [--force] [--limit N]` → reads resolved.json, fetches every norm, prints a per-norm line and a final summary of outcomes; exits with code 1 if any file `FAILED`.
- All commands read `Settings` for `data_dir`, UA, interval, timeout. `corpus/` directory is resolved relative to the current working directory.

- [ ] **Step 1: Write the failing tests**

`tests/ingest/test_cli.py`:
```python
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
from tests.conftest import FIXTURE_NORMS, FIXTURE_RELATIONS, NORM_COLUMNS, RELATION_COLUMNS, write_csv_zip

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingest/test_cli.py -v`
Expected: FAIL (no `ingest` command registered).

- [ ] **Step 3: Implement the ingest sub-app**

`src/legal_ai/ingest/cli.py`:
```python
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated

import httpx
import typer

from legal_ai.ingest.catalog import SnapshotExistsError, download_catalog, latest_snapshot, load_snapshot
from legal_ai.ingest.catalog_reader import ZipCatalog
from legal_ai.ingest.fetch import FetchOutcome, InfolegClient, fetch_norm
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import load_manifest, read_resolved, resolve_corpus, write_resolved
from legal_ai.settings import Settings

app = typer.Typer(help="Descarga reproducible de Infoleg a data/raw.")


def _http(settings: Settings) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.infoleg_user_agent}, timeout=settings.infoleg_timeout_seconds
    )


@app.command()
def catalog(
    snapshot_date: Annotated[
        str | None, typer.Option("--date", help="Fecha del snapshot (YYYY-MM-DD). Default: hoy.")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Reemplaza un snapshot existente.")] = False,
) -> None:
    """Descarga los tres ZIP de la base Infoleg a data/raw/infoleg/catalog/<fecha>/."""
    settings = Settings()
    layout = RawLayout(settings.data_dir)
    when = date.fromisoformat(snapshot_date) if snapshot_date else date.today()
    try:
        with _http(settings) as http:
            snapshot = download_catalog(layout, http, when, force=force)
    except SnapshotExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    for record in snapshot.resources:
        typer.echo(f"{record.filename}  {record.size_bytes} bytes  sha256={record.sha256}")
    typer.echo(f"manifest: {layout.catalog_dir(when) / 'manifest.json'}")


@app.command()
def resolve(
    corpus: Annotated[str, typer.Argument(help="Nombre del manifest en corpus/<nombre>.yaml")],
    catalog_date: Annotated[
        str | None, typer.Option("--catalog-date", help="Snapshot a usar. Default: el último.")
    ] = None,
) -> None:
    """Resuelve el manifest del corpus a id_norma y escribe data/processed/<corpus>/resolved.json."""
    settings = Settings()
    raw = RawLayout(settings.data_dir)
    processed = ProcessedLayout(settings.data_dir)
    snapshot = (
        load_snapshot(raw, date.fromisoformat(catalog_date)) if catalog_date else latest_snapshot(raw)
    )
    if snapshot is None:
        typer.echo("No hay ningún snapshot del catálogo; corré `legal-ai ingest catalog` primero.", err=True)
        raise typer.Exit(1)
    manifest = load_manifest(Path("corpus") / f"{corpus}.yaml")
    resolved = resolve_corpus(manifest, ZipCatalog(snapshot, raw), snapshot.snapshot_date)
    target = processed.resolved_path(corpus)
    write_resolved(resolved, target)
    by_depth = Counter(n.depth for n in resolved.norms)
    by_tipo = Counter(n.tipo_norma for n in resolved.norms)
    typer.echo(f"{len(resolved.norms)} normas (catálogo {snapshot.snapshot_date})")
    typer.echo("por profundidad: " + ", ".join(f"{d}={c}" for d, c in sorted(by_depth.items())))
    typer.echo("por tipo: " + ", ".join(f"{t}={c}" for t, c in by_tipo.most_common()))
    typer.echo(f"escrito: {target}")


@app.command()
def fetch(
    corpus: Annotated[str, typer.Argument(help="Corpus ya resuelto con `ingest resolve`.")],
    force: Annotated[bool, typer.Option("--force", help="Vuelve a bajar aunque esté en caché.")] = False,
    limit: Annotated[int | None, typer.Option("--limit", help="Procesa solo las primeras N normas.")] = None,
) -> None:
    """Descarga norma.htm, texact.htm y las páginas de vínculos de cada norma del corpus."""
    settings = Settings()
    raw = RawLayout(settings.data_dir)
    resolved = read_resolved(ProcessedLayout(settings.data_dir).resolved_path(corpus))
    norms = resolved.norms[:limit] if limit is not None else resolved.norms
    totals: Counter[FetchOutcome] = Counter()
    with _http(settings) as http:
        client = InfolegClient(http, min_interval=settings.infoleg_min_interval_seconds)
        for i, norm in enumerate(norms, 1):
            report = fetch_norm(client, raw, norm, force=force)
            totals.update(report.outcomes.values())
            summary = " ".join(f"{k}={v.value}" for k, v in report.outcomes.items())
            typer.echo(f"[{i}/{len(norms)}] {norm.tipo_norma} {norm.numero_norma} ({norm.id_norma}) {summary}")
            for name, error in report.errors.items():
                typer.echo(f"    {name}: {error}", err=True)
    typer.echo(
        "total: " + " ".join(f"{o.value}={totals.get(o, 0)}" for o in FetchOutcome)
    )
    if totals.get(FetchOutcome.FAILED):
        raise typer.Exit(1)
```

Modify `src/legal_ai/cli.py`:
```python
import typer

from legal_ai.ingest.cli import app as ingest_app

app = typer.Typer(help="Legal AI Argentina: herramientas de ingestion, indexado y evaluación.")
app.add_typer(ingest_app, name="ingest")


@app.callback()
def main() -> None:
    pass
```

- [ ] **Step 4: Run all tests, lint, types**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: all passed, clean. If `ruff format --check` fails, run `uv run ruff format .` and re-run.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/cli.py src/legal_ai/ingest/cli.py tests/ingest/test_cli.py
git commit -m "Add legal-ai ingest catalog/resolve/fetch commands"
```

---

### Task 8: Run the real ingestion and record the result

**Files:**
- Modify: `docs/ROADMAP.md` (Fase 1 status and counts), `README.md` (Estado)
- Create: `data/raw/infoleg/README.md` (this file IS committed: add `!data/raw/infoleg/README.md` to `.gitignore`)

No unit tests: this task's verification is the real run.

- [ ] **Step 1: Download the catalog**

Run: `uv run legal-ai ingest catalog`
Expected: three files listed with sizes around 50 MB, 8 MB and 8 MB, plus the manifest path. Takes about a minute.

- [ ] **Step 2: Resolve the corpus**

Run: `uv run legal-ai ingest resolve laboral`
Expected: a count of norms (the six seeds plus Ley/Decreto modifiers of them), by depth and by tipo, and the resolved.json path. Record the printed numbers.

- [ ] **Step 3: Fetch a sample first**

Run: `uv run legal-ai ingest fetch laboral --limit 3`
Expected: three lines with `fetched` for the URLs that exist, `no_url` for `texact.htm` where the CSV has none, exit code 0. Inspect one file:

Run: `head -c 400 data/raw/infoleg/normas/25552/texact.htm && cat data/raw/infoleg/normas/25552/meta.json`
Expected: HTML starting with `<html>`/`<!DOCTYPE`, meta with four files and `"missing": []`.

- [ ] **Step 4: Fetch everything**

Run: `uv run legal-ai ingest fetch laboral 2>&1 | tee /tmp/fetch-laboral.log; echo "exit=$?"`
Expected: at 0.5 s per request, roughly 4 requests per norm; a few hundred norms take well under an hour. Exit 0. If any `failed`, read the error lines; a persistent 404 on a CSV-listed URL is data to record, not to hide.

- [ ] **Step 5: Verify the raw layout**

Run:
```bash
ls data/raw/infoleg/normas | wc -l
find data/raw/infoleg/normas -name texact.htm | wc -l
find data/raw/infoleg/normas -name norma.htm | wc -l
grep -l '"missing": \[\]' data/raw/infoleg/normas/*/meta.json | wc -l
du -sh data/raw/infoleg
```
Expected: directory count equals the resolve count; texact count ≤ norma count. Record these numbers.

- [ ] **Step 6: Document the run**

`data/raw/infoleg/README.md`:
```markdown
# data/raw/infoleg

Descargas inmutables. Nada acá se edita a mano. Se regenera con:

    uv run legal-ai ingest catalog
    uv run legal-ai ingest resolve laboral
    uv run legal-ai ingest fetch laboral

- `catalog/<fecha>/`: los tres ZIP de datos.jus.gob.ar + `manifest.json` (sha256, tamaño, URL, fecha).
- `normas/<id_norma>/`: `norma.htm` (texto original), `texact.htm` (texto actualizado, si Infoleg lo tiene),
  `vinculos_modifica.htm`, `vinculos_modificada_por.htm`, `meta.json` (URL, status, sha256, fecha por archivo).
```

Add to `.gitignore` after `!data/raw/.gitkeep`:
```
!data/raw/infoleg/
data/raw/infoleg/*
!data/raw/infoleg/README.md
```

In `docs/ROADMAP.md`, set Fase 1 to `hecha` and add under "Fase 1 en detalle" a final line:
```
Resultado (catálogo YYYY-MM-DD): N normas resueltas (S seeds, M modificatorias), T con texto actualizado, F fallos.
```
with the real numbers from Steps 2 and 5. In `README.md`, change "Estado" to: "Fases 0 y 1 completas. Fase 2 (parser) en curso."

- [ ] **Step 7: Full check and commit**

Run: `uv run pytest && uv run ruff check . && uv run pyright && git status --short`
Expected: green; only the three docs and `.gitignore` show as changes (raw data ignored).

```bash
git add .gitignore data/raw/infoleg/README.md docs/ROADMAP.md README.md
git commit -m "Run Phase 1 ingestion for the laboral corpus and record results"
```

---

## Self-review

**Spec coverage.**
- Descarga de los 3 ZIP con hash y manifest → Task 3. ✔
- Resolución del manifest por número, no por id; expansión a profundidad 1 → Task 5. ✔ (`tipos` filter added because 263 LCT modifiers include resolutions that are noise for the corpus.)
- Descarga de `norma.htm`, `texact.htm` y dos páginas de vínculos con UA, reintentos, rate limit y caché → Task 6. ✔
- CLI `ingest catalog|resolve|fetch` → Task 7. ✔
- Tests sin red → respx + fixture ZIPs, Tasks 3–7. ✔
- `raw` inmutable salvo `--force`, `fetched_at` + sha256 en todo → Tasks 3 and 6. ✔
- `resolved.json` lives in `processed/` because it is derived; documented in ARCHITECTURE *Layout de datos*? **Gap:** ARCHITECTURE lists `documents/articles/relations.jsonl` under processed but not `resolved.json`. Add it during Task 8 Step 6 (one line under `data/processed/<corpus>/`).

**Placeholder scan.** None found.

**Type consistency.** `RawLayout.norm_dir(int)`, `CatalogSnapshot.path_for(name, layout)`, `ResolvedNorm.url_original/url_actualizado`, `InfolegClient(http, *, min_interval, ...)`, `fetch_norm(client, layout, norm, *, force)` are used with the same signatures in Tasks 6 and 7. `FetchOutcome` values match the strings asserted in `test_cli.py` (`fetched=`, `cached=4`, `failed=3`). In `test_fetch_command_exits_1_when_a_file_fails`, 3 norms each fail `norma.htm` → `failed=3`. In the `--limit 1` run, LCT has 4 URLs all cached → `cached=4`. ✔
