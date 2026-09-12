# Phase 3: Postgres Index and Baseline RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the Phase 2 JSONL into PostgreSQL, build article-level chunks with a context prefix, embed them with bge-m3, and answer a question end to end: question → vector search → context → Claude with structured output → answer with `article@version` citations, traced with OpenTelemetry and measured on 20 smoke questions.

**Architecture:** PostgreSQL 17 (ParadeDB image: pgvector + pg_search) is the single store. SQLAlchemy 2.0 Core + Alembic own the schema; retrieval is one visible SQL statement. Chunks are one per vigente article version (annexes and derogated versions excluded from the baseline), each prefixed with its legal context before embedding. Embeddings come from a pluggable `Embedder` (bge-m3 locally; a deterministic feature-hashing embedder for tests and as a no-download fallback), cached on disk by text hash. Generation uses `client.messages.parse` with a Pydantic schema; sources are validated against the context. Every stage is an OTel span with GenAI attributes, exported over OTLP when configured and to a local JSONL file always. FastAPI exposes `/ask`; the CLI exposes `search`, `ask`, `bench`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 Core, Alembic, psycopg 3, pgvector (Python), sentence-transformers (BAAI/bge-m3), anthropic SDK 1.x, FastAPI + uvicorn, opentelemetry-sdk + otlp-proto-http exporter, numpy, pytest. Docker via Colima with `paradedb/paradedb:0.25.9-pg17`.

**Spec:** `docs/ARCHITECTURE.md` (*Modelo de datos → chunks*, *Retrieval*, *Generación*, *Observabilidad*, *Infra local*), `docs/ROADMAP.md` (Fase 3), `docs/DECISIONS.md` (ADR-002, ADR-005, ADR-007, ADR-008, ADR-009), plus the Phase 3 design approved in conversation.

## Global Constraints

- `requires-python = ">=3.12,<3.13"`; run everything with `uv run`.
- Code in English; CLI help, prompts and docs in Spanish (ADR-011). No comments except an optional one-line module header.
- Retrieval SQL lives in one place and is plain SQL text, not ORM query builders (ADR-002 "el SQL queda visible").
- Claude model id is exactly `claude-opus-5`; never append a date suffix. Use `client.messages.parse(...)` for structured output. Check `response.stop_reason` before reading content. Do not guess SDK names: the shapes used here come from the `claude-api` skill's Python README (`messages.parse`, `output_format=`, `parsed_output`, top-level `cache_control={"type": "ephemeral"}`).
- Tests never call Anthropic or download models: generation tests use a fake client; embedding tests use `HashingEmbedder`. Database tests use a dedicated `legal_ai_test` database and are skipped with a clear reason when Postgres is unreachable.
- Baseline chunk selection: `current` version if the article has one, else `original`; `status == "vigente"`; non-empty text; `annex is None`. Everything else is an experiment for Phase 5, not a silent inclusion.
- No invented numbers: latency, tokens and cost in `experiments/` come from the run.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01X9PTzEP62xfYRS8W8iGP9a
  ```

## File Structure

```
pyproject.toml                          (modify) new deps
.env.example                            (modify) DATABASE_URL, OTLP, model names
docker-compose.yml                      (modify) healthcheck stays; nothing else
alembic.ini
migrations/env.py, migrations/script.py.mako, migrations/versions/0001_initial.py
src/legal_ai/settings.py                (modify) database_url, test_database_url, anthropic_api_key, embedding_model, llm_model, otlp_endpoint, traces_path
src/legal_ai/db/__init__.py
src/legal_ai/db/schema.py               SQLAlchemy MetaData: documents, articles, article_versions, relations, history, chunks
src/legal_ai/db/engine.py               make_engine(url); upgrade_database(url) runs alembic programmatically
src/legal_ai/index/__init__.py
src/legal_ai/index/load.py              load_corpus(engine, processed_dir, corpus) -> LoadReport
src/legal_ai/index/chunking.py          ChunkRecord, context_prefix(), split_text(), build_chunks()
src/legal_ai/index/embeddings.py        Embedder protocol, HashingEmbedder, BgeM3Embedder, EmbeddingCache, get_embedder()
src/legal_ai/index/embed.py             embed_chunks(engine, embedder, cache, corpus, limit) -> EmbedReport
src/legal_ai/index/cli.py               `legal-ai db upgrade`, `legal-ai index load|chunk|embed`
src/legal_ai/retrieval/__init__.py
src/legal_ai/retrieval/types.py         Candidate
src/legal_ai/retrieval/vector.py        VECTOR_SQL, retrieve_vector(conn, query_vector, k)
src/legal_ai/retrieval/retriever.py     Retriever(engine, embedder).search(query, k) -> list[Candidate]
src/legal_ai/generation/__init__.py
src/legal_ai/generation/schema.py       Claim, GroundedAnswer
src/legal_ai/generation/prompt.py       SYSTEM_PROMPT, build_context(), build_user_message()
src/legal_ai/generation/claude.py       ClaudeGenerator(client, model).generate(question, blocks) -> Generation
src/legal_ai/observability/__init__.py
src/legal_ai/observability/tracing.py   setup_tracing(settings) -> tracer; JsonlSpanExporter
src/legal_ai/pipeline.py                ask(question, k) -> AskResponse (spans: retrieval, context, llm)
src/legal_ai/api/__init__.py
src/legal_ai/api/app.py                 FastAPI: GET /health, POST /ask
src/legal_ai/cli.py                     (modify) mount db, index, search, ask, serve, bench
src/legal_ai/bench.py                   run_smoke(questions_path, k, with_generation) -> writes experiments/<date>-phase3-baseline.json
eval/smoke_questions.jsonl              20 questions with expected article ids
tests/conftest.py                       (modify) db fixtures: test engine, migrated schema, truncate per test
tests/db/test_schema.py
tests/index/test_load.py, test_chunking.py, test_embeddings.py, test_embed.py
tests/retrieval/test_vector.py
tests/generation/test_prompt.py, test_claude.py
tests/test_pipeline_api.py
tests/test_bench.py
```

---

### Task 1: Dependencies, settings, schema and first migration

**Files:**
- Modify: `pyproject.toml`, `.env.example`, `src/legal_ai/settings.py`, `tests/conftest.py`
- Create: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial.py`, `src/legal_ai/db/__init__.py`, `src/legal_ai/db/schema.py`, `src/legal_ai/db/engine.py`, `tests/db/__init__.py`, `tests/db/test_schema.py`

**Interfaces:**
- Produces:
  ```python
  # settings.py additions (env prefix LEGAL_AI_ except the Anthropic key)
  database_url: str = "postgresql+psycopg://legal_ai:legal_ai@localhost:5432/legal_ai"
  test_database_url: str = "postgresql+psycopg://legal_ai:legal_ai@localhost:5432/legal_ai_test"
  anthropic_api_key: str | None   # validation_alias="ANTHROPIC_API_KEY"
  embedding_model: str = "BAAI/bge-m3"
  embedding_dim: int = 1024
  llm_model: str = "claude-opus-5"
  otlp_endpoint: str | None = None
  traces_path: Path = Path("data/traces/spans.jsonl")
  # db/schema.py
  metadata: MetaData; documents, articles, article_versions, relations, history, chunks: Table
  # db/engine.py
  def make_engine(url: str) -> Engine
  def upgrade_database(url: str) -> None      # alembic upgrade head, programmatic
  def ensure_database(url: str) -> None       # CREATE DATABASE if missing (connects to the maintenance db "postgres")
  ```
- `chunks.embedding` is `Vector(1024)` from `pgvector.sqlalchemy`; the migration creates `CREATE EXTENSION IF NOT EXISTS vector` and `CREATE EXTENSION IF NOT EXISTS pg_search`, then an HNSW index `chunks_embedding_hnsw` with `vector_cosine_ops`.
- Test fixtures in `tests/conftest.py`: `db_engine` (session scope; skips the test module when the test database is unreachable), `db` (function scope; truncates all tables after each test).

- [ ] **Step 1: Add dependencies**

In `pyproject.toml` replace the `dependencies` list with:
```toml
dependencies = [
    "alembic>=1.13",
    "anthropic>=1.0",
    "fastapi>=0.115",
    "httpx>=0.27",
    "numpy>=2.0",
    "opentelemetry-api>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
    "opentelemetry-sdk>=1.27",
    "pgvector>=0.3",
    "psycopg[binary]>=3.2",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "pyyaml>=6.0",
    "sqlalchemy>=2.0",
    "typer>=0.12",
    "uvicorn[standard]>=0.30",
]

[project.optional-dependencies]
embeddings = ["sentence-transformers>=3.0", "torch>=2.3"]
```
Run: `uv sync --extra embeddings` (torch is large; it runs once).

- [ ] **Step 2: Settings**

Replace `src/legal_ai/settings.py` with:
```python
from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    database_url: str = "postgresql+psycopg://legal_ai:legal_ai@localhost:5432/legal_ai"
    test_database_url: str = "postgresql+psycopg://legal_ai:legal_ai@localhost:5432/legal_ai_test"
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    llm_model: str = "claude-opus-5"
    otlp_endpoint: str | None = None
    traces_path: Path = Path("data/traces/spans.jsonl")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```
Append to `.env.example`:
```
LEGAL_AI_DATABASE_URL=postgresql+psycopg://legal_ai:legal_ai@localhost:5432/legal_ai
LEGAL_AI_EMBEDDING_MODEL=BAAI/bge-m3
LEGAL_AI_LLM_MODEL=claude-opus-5
LEGAL_AI_OTLP_ENDPOINT=
```

- [ ] **Step 3: Write the failing schema test**

`tests/db/__init__.py`: empty. `tests/db/test_schema.py`:
```python
from sqlalchemy import inspect, text

from legal_ai.db.schema import metadata


def test_migration_creates_tables_and_extensions(db_engine):
    names = set(inspect(db_engine).get_table_names())
    assert {"documents", "articles", "article_versions", "relations", "history", "chunks"} <= names
    assert set(metadata.tables) <= names
    with db_engine.connect() as conn:
        extensions = {r[0] for r in conn.execute(text("SELECT extname FROM pg_extension"))}
        assert {"vector", "pg_search"} <= extensions
        indexes = {r[0] for r in conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'chunks'"))}
        assert "chunks_embedding_hnsw" in indexes
```

Add to `tests/conftest.py` (top-level imports and fixtures):
```python
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from legal_ai.settings import Settings


@pytest.fixture(scope="session")
def db_engine():
    from legal_ai.db.engine import ensure_database, make_engine, upgrade_database

    url = Settings().test_database_url
    try:
        ensure_database(url)
        upgrade_database(url)
    except OperationalError as exc:
        pytest.skip(f"Postgres de test no disponible en {url}: {exc}")
    engine = make_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    yield db_engine
    from legal_ai.db.schema import metadata

    with db_engine.begin() as conn:
        for table in reversed(metadata.sorted_tables):
            conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/db -v`
Expected: FAIL with `ModuleNotFoundError: legal_ai.db` (or SKIP if Postgres is down: then start it with `docker compose up -d postgres` and wait for `docker compose ps` to show healthy).

- [ ] **Step 5: Schema**

`src/legal_ai/db/__init__.py`: empty.

`src/legal_ai/db/schema.py`:
```python
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

EMBEDDING_DIM = 1024

metadata = MetaData()

documents = Table(
    "documents",
    metadata,
    Column("id_norma", Integer, primary_key=True),
    Column("corpus", String(64), nullable=False, index=True),
    Column("tipo_norma", String(64), nullable=False),
    Column("numeros", JSONB, nullable=False),
    Column("organismos", JSONB, nullable=False),
    Column("clase_norma", String(64)),
    Column("fecha_sancion", Date),
    Column("fecha_boletin", Date),
    Column("numero_boletin", Integer),
    Column("titulo_resumido", Text),
    Column("titulo_sumario", Text),
    Column("texto_resumido", Text),
    Column("url_original", Text),
    Column("url_actualizado", Text),
    Column("reason", String(64), nullable=False),
    Column("depth", Integer, nullable=False),
    Column("has_original_text", Boolean, nullable=False),
    Column("has_current_text", Boolean, nullable=False),
    Column("original_source_document_id", Integer),
    Column("front_matter", Text, nullable=False),
    Column("n_articles_original", Integer, nullable=False),
    Column("n_articles_current", Integer, nullable=False),
    Column("n_history_events", Integer, nullable=False),
)

articles = Table(
    "articles",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("document_id", Integer, ForeignKey("documents.id_norma", ondelete="CASCADE"), nullable=False, index=True),
    Column("key", String(32), nullable=False),
    Column("label", String(32), nullable=False),
    Column("number", Integer, nullable=False),
    Column("suffix", String(16)),
    Column("ordinal", Integer, nullable=False),
    Column("heading", Text),
    Column("sections", JSONB, nullable=False),
    Column("annex", String(32)),
)

article_versions = Table(
    "article_versions",
    metadata,
    Column("id", String(80), primary_key=True),
    Column("article_id", String(64), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("document_id", Integer, ForeignKey("documents.id_norma", ondelete="CASCADE"), nullable=False, index=True),
    Column("version_kind", String(16), nullable=False),
    Column("text", Text, nullable=False),
    Column("text_with_notes", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("effective_from", Date),
    Column("effective_until", Date),
    Column("modification_kind", String(32)),
    Column("modified_by_tipo", String(64)),
    Column("modified_by_numero", String(32)),
    Column("modified_by_article", String(32)),
    Column("source_document_id", Integer, nullable=False),
    Column("source_url", Text),
    Column("text_sha256", String(64), nullable=False),
    Column("unchanged_from_original", Boolean),
    Column("similarity_to_original", Float),
    Index("article_versions_status_from", "status", "effective_from"),
)

relations = Table(
    "relations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("corpus", String(64), nullable=False, index=True),
    Column("source_id", Integer, nullable=False, index=True),
    Column("target_id", Integer, nullable=False, index=True),
    Column("kind", String(32), nullable=False),
    Column("evidence", String(32), nullable=False),
    Column("tipo", String(64)),
    Column("numero", String(32)),
    Column("organismo", Text),
    Column("fecha_boletin", Date),
    Column("tema", Text),
    Column("descripcion", Text),
    UniqueConstraint("source_id", "target_id", "kind", "evidence", name="relations_unique_edge"),
)

history = Table(
    "history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("document_id", Integer, ForeignKey("documents.id_norma", ondelete="CASCADE"), nullable=False, index=True),
    Column("article_key", String(32)),
    Column("article_label", String(32)),
    Column("kind", String(32), nullable=False),
    Column("by_tipo", String(64)),
    Column("by_numero", String(32)),
    Column("by_article", String(32)),
    Column("bo_date", Date),
    Column("vigencia", Text),
    Column("raw", Text, nullable=False),
)

chunks = Table(
    "chunks",
    metadata,
    Column("id", String(96), primary_key=True),
    Column("version_id", String(80), ForeignKey("article_versions.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("article_id", String(64), nullable=False, index=True),
    Column("document_id", Integer, ForeignKey("documents.id_norma", ondelete="CASCADE"), nullable=False, index=True),
    Column("chunk_index", Integer, nullable=False),
    Column("context_prefix", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("embed_text", Text, nullable=False),
    Column("token_estimate", Integer, nullable=False),
    Column("embedding", Vector(EMBEDDING_DIM)),
    Column("embedding_model", String(128)),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)
```

`src/legal_ai/db/engine.py`:
```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

ROOT = Path(__file__).resolve().parents[3]


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def _alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade_database(url: str) -> None:
    command.upgrade(_alembic_config(url), "head")


def ensure_database(url: str) -> None:
    target = make_url(url)
    maintenance = target.set(database="postgres")
    engine = create_engine(maintenance, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    engine.dispose()
```

`alembic.ini`:
```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql+psycopg://legal_ai:legal_ai@localhost:5432/legal_ai

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`migrations/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

`migrations/env.py`:
```python
from alembic import context
from sqlalchemy import engine_from_config, pool

from legal_ai.db.schema import metadata

config = context.config
target_metadata = metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`migrations/versions/0001_initial.py`:
```python
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-12
"""
from alembic import op

from legal_ai.db.schema import metadata

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
    metadata.create_all(op.get_bind())
    op.execute(
        "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_embedding_hnsw")
    metadata.drop_all(op.get_bind())
```

- [ ] **Step 6: Start Postgres and run**

Run: `docker compose up -d postgres && sleep 5 && docker compose ps && uv run pytest tests/db -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: postgres `healthy`; 1 passed; clean. If pyright flags `pgvector.sqlalchemy` as untyped, add `# pyright: ignore[reportMissingTypeStubs]` on that import line only.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .env.example alembic.ini migrations src/legal_ai/settings.py src/legal_ai/db tests/conftest.py tests/db
git commit -m "Add Postgres schema (pgvector, pg_search) with Alembic and test database fixtures"
```

---

### Task 2: Load the processed JSONL into Postgres

**Files:**
- Create: `src/legal_ai/index/__init__.py`, `src/legal_ai/index/load.py`, `tests/index/__init__.py`, `tests/index/test_load.py`

**Interfaces:**
- Consumes: `metadata` tables; Phase 2 JSONL files in `ProcessedLayout.corpus_dir(name)`.
- Produces:
  ```python
  class LoadReport(BaseModel): corpus: str; documents: int; articles: int; versions: int; relations: int; history: int
  def load_corpus(engine: Engine, processed: ProcessedLayout, corpus: str) -> LoadReport
  ```
- Idempotent: deletes `documents` rows of that corpus (cascading to articles, versions, history, chunks) and `relations` of that corpus, then inserts in batches of 1000 with `conn.execute(table.insert(), rows)`.

- [ ] **Step 1: Write the failing test**

`tests/index/__init__.py`: empty. `tests/index/test_load.py`:
```python
import shutil
from datetime import UTC, date, datetime
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
        version = conn.execute(select(article_versions).where(article_versions.c.id == "25552:28@current")).mappings().one()
        assert version["status"] == "derogado" and version["effective_from"] == date(2026, 3, 6)
        assert conn.execute(select(func.count()).select_from(relations)).scalar() == first.relations
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/index/test_load.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/index/__init__.py`: empty. `src/legal_ai/index/load.py`:
```python
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Table, delete, select
from sqlalchemy.engine import Connection, Engine

from legal_ai.db.schema import article_versions, articles, documents, history, relations
from legal_ai.ingest.layout import ProcessedLayout

BATCH = 1000


class LoadReport(BaseModel):
    corpus: str
    documents: int
    articles: int
    versions: int
    relations: int
    history: int


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _insert(conn: Connection, table: Table, rows: Iterator[dict[str, Any]]) -> int:
    batch: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH:
            conn.execute(table.insert(), batch)
            total += len(batch)
            batch = []
    if batch:
        conn.execute(table.insert(), batch)
        total += len(batch)
    return total


def _document_rows(path: Path, corpus: str) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        yield {**row, "corpus": corpus}


def _version_rows(path: Path) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        yield row


def _relation_rows(path: Path, corpus: str) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        yield {**row, "corpus": corpus}


def _history_rows(path: Path) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        by = row.pop("by")
        yield {
            **row,
            "by_tipo": by["tipo"],
            "by_numero": by["numero"],
            "by_article": by["article"],
            "bo_date": by["bo_date"],
            "vigencia": by["vigencia"],
        }


def load_corpus(engine: Engine, processed: ProcessedLayout, corpus: str) -> LoadReport:
    folder = processed.corpus_dir(corpus)
    with engine.begin() as conn:
        ids = [r[0] for r in conn.execute(select(documents.c.id_norma).where(documents.c.corpus == corpus))]
        if ids:
            conn.execute(delete(documents).where(documents.c.id_norma.in_(ids)))
        conn.execute(delete(relations).where(relations.c.corpus == corpus))
        n_docs = _insert(conn, documents, _document_rows(folder / "documents.jsonl", corpus))
        n_articles = _insert(conn, articles, _rows(folder / "articles.jsonl"))
        n_versions = _insert(conn, article_versions, _version_rows(folder / "article_versions.jsonl"))
        n_relations = _insert(conn, relations, _relation_rows(folder / "relations.jsonl", corpus))
        n_history = _insert(conn, history, _history_rows(folder / "history.jsonl"))
    return LoadReport(
        corpus=corpus,
        documents=n_docs,
        articles=n_articles,
        versions=n_versions,
        relations=n_relations,
        history=n_history,
    )
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/index/test_load.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 1 passed, clean. If insert fails on `sections` (list of dicts) or `numeros`, the JSONB columns accept Python lists directly with psycopg 3; if it fails on `effective_from` strings, convert with `date.fromisoformat` in `_version_rows` for `effective_from`/`effective_until` (psycopg accepts ISO strings for date columns, so this is only needed if the driver complains).

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/index tests/index
git commit -m "Load parsed corpus JSONL into Postgres idempotently"
```

---

### Task 3: Chunking with context prefix

**Files:**
- Create: `src/legal_ai/index/chunking.py`, `tests/index/test_chunking.py`

**Interfaces:**
- Produces:
  ```python
  MAX_CHUNK_CHARS = 2500
  class ChunkRecord(BaseModel):
      id: str; version_id: str; article_id: str; document_id: int; chunk_index: int
      context_prefix: str; text: str; embed_text: str; token_estimate: int
  def context_prefix(doc: Mapping, article: Mapping, version: Mapping) -> str
  def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]
  def choose_version(versions: list[Mapping]) -> Mapping | None     # current if any, else original; None if not vigente or empty
  def build_chunks(doc: Mapping, article: Mapping, versions: list[Mapping]) -> list[ChunkRecord]
  ```
- `embed_text = f"{context_prefix}\n{text}"`. `token_estimate = max(1, len(embed_text) // 4)`.
- Context prefix format: `"{tipo_norma} {numero} — {titulo_sumario} · {TITULO n nombre} › {CAPITULO n nombre} · Art. {label}{ — heading}. Vigente desde {effective_from}."` Omitted parts are skipped cleanly (no dangling separators). `titulo_sumario` is title-cased from Infoleg's uppercase.
- Splitting: never inside a line; cut at inciso boundaries (lines starting with `[a-z]) ` or `\d+\. ` or `\d+) `) or at sentence ends when a line itself exceeds the limit; each piece ≤ `max_chars` except a single indivisible line.

- [ ] **Step 1: Write the failing tests**

`tests/index/test_chunking.py`:
```python
from legal_ai.index.chunking import build_chunks, choose_version, context_prefix, split_text

DOC = {"id_norma": 25552, "tipo_norma": "Ley", "numeros": ["20744"], "titulo_sumario": "LEY DE CONTRATO DE TRABAJO"}
ART = {
    "id": "25552:245", "label": "245", "heading": "Indemnización por antigüedad o despido", "annex": None,
    "sections": [
        {"kind": "TITULO", "number": "XII", "name": "De la extinción del contrato de trabajo"},
        {"kind": "CAPITULO", "number": "IV", "name": "De la extinción del contrato por despido"},
    ],
}
CUR = {"id": "25552:245@current", "version_kind": "current", "status": "vigente", "text": "En los casos de despido dispuesto por el empleador sin justa causa.", "effective_from": "2026-03-06"}
ORIG = {"id": "25552:245@original", "version_kind": "original", "status": "vigente", "text": "Texto original.", "effective_from": "1976-05-21"}


def test_context_prefix_reads_like_a_citation():
    assert context_prefix(DOC, ART, CUR) == (
        "Ley 20744 — Ley De Contrato De Trabajo · TITULO XII De la extinción del contrato de trabajo "
        "› CAPITULO IV De la extinción del contrato por despido · Art. 245 — Indemnización por antigüedad o despido. "
        "Vigente desde 2026-03-06."
    )


def test_context_prefix_without_sections_or_heading_or_date():
    art = {**ART, "heading": None, "sections": []}
    assert context_prefix(DOC, art, {**CUR, "effective_from": None}) == "Ley 20744 — Ley De Contrato De Trabajo · Art. 245."


def test_choose_version_prefers_current_then_original_and_skips_derogated():
    assert choose_version([ORIG, CUR])["id"] == "25552:245@current"
    assert choose_version([ORIG])["id"] == "25552:245@original"
    assert choose_version([ORIG, {**CUR, "status": "derogado", "text": ""}]) is None
    assert choose_version([{**ORIG, "text": ""}]) is None


def test_build_chunks_single_chunk_with_embed_text():
    [chunk] = build_chunks(DOC, ART, [ORIG, CUR])
    assert chunk.id == "25552:245@current#0" and chunk.chunk_index == 0
    assert chunk.version_id == "25552:245@current" and chunk.article_id == "25552:245" and chunk.document_id == 25552
    assert chunk.embed_text == chunk.context_prefix + "\n" + CUR["text"]
    assert chunk.token_estimate == max(1, len(chunk.embed_text) // 4)


def test_build_chunks_skips_annex_articles():
    assert build_chunks(DOC, {**ART, "annex": "ANEXO I"}, [CUR]) == []


def test_split_text_cuts_at_incisos_and_respects_limit():
    lines = ["Encabezado del artículo:"] + [f"{chr(97 + i)}) inciso número {i} " + "x" * 400 for i in range(8)]
    text = "\n".join(lines)
    pieces = split_text(text, max_chars=1000)
    assert len(pieces) >= 4
    assert all(len(p) <= 1000 for p in pieces)
    assert "".join(p.replace("\n", "") for p in pieces) == text.replace("\n", "")
    assert all(p.startswith(("Encabezado", "a)", "b)", "c)", "d)", "e)", "f)", "g)", "h)")) for p in pieces)


def test_split_text_long_single_line_falls_back_to_sentences():
    text = " ".join(f"Oración número {i} termina acá." for i in range(60))
    pieces = split_text(text, max_chars=300)
    assert len(pieces) > 1 and all(len(p) <= 300 for p in pieces)
    assert " ".join(pieces) == text


def test_build_chunks_long_article_yields_indexed_chunks():
    long_cur = {**CUR, "text": "\n".join(f"{chr(97 + i)}) " + "palabra " * 200 for i in range(6))}
    chunks = build_chunks(DOC, ART, [long_cur])
    assert [c.chunk_index for c in chunks] == list(range(len(chunks))) and len(chunks) >= 3
    assert all(c.context_prefix == chunks[0].context_prefix for c in chunks)
    assert chunks[1].id == "25552:245@current#1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/index/test_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/index/chunking.py`:
```python
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

MAX_CHUNK_CHARS = 2500
_INCISO_RE = re.compile(r"^(?:[a-z]\)|\d{1,2}[.)])\s")
_SENTENCE_RE = re.compile(r"(?<=[.;:])\s+")


class ChunkRecord(BaseModel):
    id: str
    version_id: str
    article_id: str
    document_id: int
    chunk_index: int
    context_prefix: str
    text: str
    embed_text: str
    token_estimate: int


def _title(value: str | None) -> str | None:
    return value.title() if value else None


def context_prefix(doc: Mapping[str, Any], article: Mapping[str, Any], version: Mapping[str, Any]) -> str:
    numero = doc["numeros"][0] if doc.get("numeros") else ""
    head = f"{doc['tipo_norma']} {numero}".strip()
    title = _title(doc.get("titulo_sumario"))
    parts = [f"{head} — {title}" if title else head]
    sections = " › ".join(
        " ".join(p for p in (s.get("kind"), s.get("number"), s.get("name")) if p) for s in article.get("sections", [])
    )
    if sections:
        parts.append(sections)
    art = f"Art. {article['label']}"
    if article.get("heading"):
        art += f" — {article['heading']}"
    parts.append(art)
    prefix = " · ".join(parts) + "."
    if version.get("effective_from"):
        prefix += f" Vigente desde {version['effective_from']}."
    return prefix


def _pack(units: list[str], max_chars: int, joiner: str) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for unit in units:
        extra = len(unit) + (len(joiner) if current else 0)
        if current and size + extra > max_chars:
            pieces.append(joiner.join(current))
            current, size = [], 0
            extra = len(unit)
        current.append(unit)
        size += extra
    if current:
        pieces.append(joiner.join(current))
    return pieces


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    lines = text.split("\n")
    blocks: list[str] = []
    for line in lines:
        if blocks and not _INCISO_RE.match(line):
            blocks[-1] = blocks[-1] + "\n" + line
        else:
            blocks.append(line)
    expanded: list[str] = []
    for block in blocks:
        if len(block) <= max_chars:
            expanded.append(block)
        else:
            expanded.extend(_pack(_SENTENCE_RE.split(block), max_chars, " "))
    return _pack(expanded, max_chars, "\n")


def choose_version(versions: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    by_kind = {v["version_kind"]: v for v in versions}
    chosen = by_kind.get("current") or by_kind.get("original")
    if chosen is None or chosen.get("status") != "vigente" or not (chosen.get("text") or "").strip():
        return None
    return chosen


def build_chunks(
    doc: Mapping[str, Any], article: Mapping[str, Any], versions: list[Mapping[str, Any]]
) -> list[ChunkRecord]:
    if article.get("annex"):
        return []
    version = choose_version(versions)
    if version is None:
        return []
    prefix = context_prefix(doc, article, version)
    records: list[ChunkRecord] = []
    for index, piece in enumerate(split_text(version["text"])):
        embed_text = f"{prefix}\n{piece}"
        records.append(
            ChunkRecord(
                id=f"{version['id']}#{index}",
                version_id=version["id"],
                article_id=article["id"],
                document_id=doc["id_norma"],
                chunk_index=index,
                context_prefix=prefix,
                text=piece,
                embed_text=embed_text,
                token_estimate=max(1, len(embed_text) // 4),
            )
        )
    return records
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/index/test_chunking.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 8 passed, clean. `test_split_text_cuts_at_incisos_and_respects_limit` joins pieces without newlines; if it fails on the equality, check that `_pack` never drops a unit and that `split_text` returns the whole text when short.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/index/chunking.py tests/index/test_chunking.py
git commit -m "Build article chunks with a legal context prefix"
```

---

### Task 4: Embedders and cache

**Files:**
- Create: `src/legal_ai/index/embeddings.py`, `tests/index/test_embeddings.py`

**Interfaces:**
- Produces:
  ```python
  class Embedder(Protocol):
      name: str; dim: int
      def embed(self, texts: list[str]) -> np.ndarray      # shape (n, dim), float32, L2-normalized
  class HashingEmbedder:   # name "hashing-1024"; feature hashing of lowercase word unigrams+bigrams, L2 normalized; deterministic, no downloads
  class BgeM3Embedder:     # name "BAAI/bge-m3"; lazy import of sentence_transformers; normalize_embeddings=True; batch_size=16
  class EmbeddingCache:    # __init__(path: Path); get(key) -> np.ndarray | None; put(key, vec); save(); keyed by sha256 of embed_text + model name
  def get_embedder(name: str) -> Embedder   # "hashing" | "BAAI/bge-m3"
  def embed_with_cache(embedder, cache, texts: list[str]) -> np.ndarray
  ```

- [ ] **Step 1: Write the failing tests**

`tests/index/test_embeddings.py`:
```python
from pathlib import Path

import numpy as np

from legal_ai.index.embeddings import EmbeddingCache, HashingEmbedder, embed_with_cache, get_embedder


def test_hashing_embedder_is_deterministic_normalized_and_semantic_ish():
    emb = HashingEmbedder()
    a = emb.embed(["período de prueba del contrato de trabajo", "período de prueba del contrato"])
    b = emb.embed(["período de prueba del contrato de trabajo"])
    assert a.shape == (2, 1024) and a.dtype == np.float32
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-5)
    assert np.allclose(a[0], b[0])
    far = emb.embed(["tope indemnizatorio promedio de remuneraciones"])[0]
    assert float(a[0] @ a[1]) > float(a[0] @ far)


def test_cache_roundtrip_and_hits(tmp_path: Path):
    emb = HashingEmbedder()
    cache = EmbeddingCache(tmp_path / "cache.npz")
    texts = ["uno", "dos", "tres"]
    first = embed_with_cache(emb, cache, texts)
    cache.save()
    reloaded = EmbeddingCache(tmp_path / "cache.npz")
    assert reloaded.get(cache.key(emb.name, "dos")) is not None
    second = embed_with_cache(emb, reloaded, texts + ["cuatro"])
    assert np.allclose(first, second[:3]) and second.shape == (4, 1024)
    assert reloaded.hits == 3 and reloaded.misses == 1


def test_get_embedder_names():
    assert get_embedder("hashing").name == "hashing-1024"
    assert get_embedder("BAAI/bge-m3").name == "BAAI/bge-m3"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/index/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/index/embeddings.py`:
```python
import hashlib
import re
from pathlib import Path
from typing import Protocol

import numpy as np

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _features(self, text: str) -> list[str]:
        tokens = _TOKEN_RE.findall(text.lower())
        return tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature in self._features(text):
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                value = int.from_bytes(digest, "big")
                out[row, value % self.dim] += 1.0 if (value >> 63) else -1.0
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out


class BgeM3Embedder:
    name = "BAAI/bge-m3"
    dim = 1024

    def __init__(self, batch_size: int = 16) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.name)
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts, batch_size=self._batch_size, normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(vectors, dtype=np.float32)


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.hits = 0
        self.misses = 0
        self._data: dict[str, np.ndarray] = {}
        if path.exists():
            with np.load(path) as stored:
                self._data = {key: stored[key] for key in stored.files}

    @staticmethod
    def key(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()

    def get(self, key: str) -> np.ndarray | None:
        return self._data.get(key)

    def put(self, key: str, vector: np.ndarray) -> None:
        self._data[key] = vector.astype(np.float32)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, **self._data)


def get_embedder(name: str) -> Embedder:
    if name == "hashing":
        return HashingEmbedder()
    if name == BgeM3Embedder.name:
        return BgeM3Embedder()
    raise ValueError(f"embedder desconocido: {name}")


def embed_with_cache(embedder: Embedder, cache: EmbeddingCache, texts: list[str]) -> np.ndarray:
    out = np.zeros((len(texts), embedder.dim), dtype=np.float32)
    missing: list[int] = []
    for i, text in enumerate(texts):
        cached = cache.get(cache.key(embedder.name, text))
        if cached is None:
            missing.append(i)
            cache.misses += 1
        else:
            out[i] = cached
            cache.hits += 1
    if missing:
        fresh = embedder.embed([texts[i] for i in missing])
        for row, i in enumerate(missing):
            out[i] = fresh[row]
            cache.put(cache.key(embedder.name, texts[i]), fresh[row])
    return out
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/index/test_embeddings.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 3 passed, clean. Note `test_get_embedder_names` constructs `BgeM3Embedder`, which downloads the model: change that assertion to `assert BgeM3Embedder.name == "BAAI/bge-m3"` (class attribute, no instantiation) so tests never download.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/index/embeddings.py tests/index/test_embeddings.py
git commit -m "Add hashing and bge-m3 embedders with an on-disk cache"
```

---

### Task 5: Chunk + embed commands and vector retrieval

**Files:**
- Create: `src/legal_ai/index/embed.py`, `src/legal_ai/index/cli.py`, `src/legal_ai/retrieval/__init__.py`, `src/legal_ai/retrieval/types.py`, `src/legal_ai/retrieval/vector.py`, `src/legal_ai/retrieval/retriever.py`, `tests/index/test_embed.py`, `tests/retrieval/__init__.py`, `tests/retrieval/test_vector.py`
- Modify: `src/legal_ai/cli.py`

**Interfaces:**
- Produces:
  ```python
  # index/embed.py
  class ChunkReport(BaseModel): corpus: str; chunks: int; articles_with_chunks: int; skipped_articles: int
  def build_corpus_chunks(engine, corpus) -> ChunkReport      # deletes chunks of the corpus, rebuilds from DB rows
  class EmbedReport(BaseModel): corpus: str; embedded: int; cached: int; model: str
  def embed_chunks(engine, embedder, cache, corpus, limit: int | None = None) -> EmbedReport   # fills embedding where NULL or model differs
  # retrieval/types.py
  class Candidate(BaseModel): chunk_id: str; version_id: str; article_id: str; document_id: int; score: float; rank: int; retriever: str; context_prefix: str; text: str
  # retrieval/vector.py
  VECTOR_SQL: str
  def retrieve_vector(conn, query_vector: list[float], k: int) -> list[Candidate]
  # retrieval/retriever.py
  class Retriever: __init__(engine, embedder); search(query: str, k: int = 8) -> list[Candidate]
  ```
- `VECTOR_SQL` (verbatim):
  ```sql
  SELECT id, version_id, article_id, document_id, context_prefix, text,
         1 - (embedding <=> CAST(:q AS vector)) AS score
  FROM chunks
  WHERE embedding IS NOT NULL
  ORDER BY embedding <=> CAST(:q AS vector)
  LIMIT :k
  ```
- CLI: `legal-ai db upgrade`, `legal-ai index load <corpus>`, `legal-ai index chunk <corpus>`, `legal-ai index embed <corpus> [--model hashing|BAAI/bge-m3] [--limit N]`, `legal-ai search "<pregunta>" [--k 8] [--model ...]`.

- [ ] **Step 1: Write the failing tests**

`tests/index/test_embed.py`:
```python
from pathlib import Path

from sqlalchemy import func, select

from legal_ai.db.schema import chunks
from legal_ai.index.embed import build_corpus_chunks, embed_chunks
from legal_ai.index.embeddings import EmbeddingCache, HashingEmbedder
from legal_ai.index.load import load_corpus
from tests.index.test_load import parsed_corpus


def test_chunk_and_embed_corpus(db, tmp_path: Path):
    processed = parsed_corpus(tmp_path)
    load_corpus(db, processed, "mini")
    report = build_corpus_chunks(db, "mini")
    assert report.chunks >= 270 and report.articles_with_chunks >= 270
    again = build_corpus_chunks(db, "mini")
    assert again.chunks == report.chunks

    cache = EmbeddingCache(tmp_path / "emb.npz")
    embedded = embed_chunks(db, HashingEmbedder(), cache, "mini")
    assert embedded.embedded == report.chunks and embedded.cached == 0
    second = embed_chunks(db, HashingEmbedder(), cache, "mini")
    assert second.embedded == 0
    with db.connect() as conn:
        missing = conn.execute(select(func.count()).select_from(chunks).where(chunks.c.embedding.is_(None))).scalar()
        assert missing == 0
        row = conn.execute(select(chunks).where(chunks.c.id == "25552:92bis@current#0")).mappings().one()
        assert row["context_prefix"].startswith("Ley 20744") and "Art. 92 bis — Período de prueba" in row["context_prefix"]
        assert row["embedding_model"] == "hashing-1024"
        derogated = conn.execute(select(func.count()).select_from(chunks).where(chunks.c.version_id == "25552:28@current")).scalar()
        assert derogated == 0
```

`tests/retrieval/__init__.py`: empty. `tests/retrieval/test_vector.py`:
```python
from pathlib import Path

from legal_ai.index.embed import build_corpus_chunks, embed_chunks
from legal_ai.index.embeddings import EmbeddingCache, HashingEmbedder
from legal_ai.index.load import load_corpus
from legal_ai.retrieval.retriever import Retriever
from tests.index.test_load import parsed_corpus


def test_vector_search_returns_ranked_candidates(db, tmp_path: Path):
    load_corpus(db, parsed_corpus(tmp_path), "mini")
    build_corpus_chunks(db, "mini")
    embed_chunks(db, HashingEmbedder(), EmbeddingCache(tmp_path / "emb.npz"), "mini")

    retriever = Retriever(db, HashingEmbedder())
    results = retriever.search("período de prueba del contrato de trabajo por tiempo indeterminado", k=5)
    assert [c.rank for c in results] == [1, 2, 3, 4, 5]
    assert results[0].score >= results[-1].score
    assert all(c.retriever == "vector" for c in results)
    assert any(c.article_id == "25552:92bis" for c in results)
    assert results[0].text and results[0].context_prefix
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/index/test_embed.py tests/retrieval -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement embed.py**

`src/legal_ai/index/embed.py`:
```python
from collections import defaultdict
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine

from legal_ai.db.schema import article_versions, articles, chunks, documents
from legal_ai.index.chunking import build_chunks
from legal_ai.index.embeddings import Embedder, EmbeddingCache, embed_with_cache

BATCH = 64


class ChunkReport(BaseModel):
    corpus: str
    chunks: int
    articles_with_chunks: int
    skipped_articles: int


class EmbedReport(BaseModel):
    corpus: str
    embedded: int
    cached: int
    model: str


def build_corpus_chunks(engine: Engine, corpus: str) -> ChunkReport:
    with engine.begin() as conn:
        docs = {r["id_norma"]: dict(r) for r in conn.execute(select(documents).where(documents.c.corpus == corpus)).mappings()}
        if docs:
            conn.execute(delete(chunks).where(chunks.c.document_id.in_(list(docs))))
        arts = [dict(r) for r in conn.execute(select(articles).where(articles.c.document_id.in_(list(docs)))).mappings()]
        versions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in conn.execute(select(article_versions).where(article_versions.c.document_id.in_(list(docs)))).mappings():
            versions[row["article_id"]].append(dict(row))
        rows: list[dict[str, Any]] = []
        with_chunks = 0
        for art in arts:
            records = build_chunks(docs[art["document_id"]], art, versions.get(art["id"], []))
            if records:
                with_chunks += 1
            rows.extend(r.model_dump() for r in records)
        for start in range(0, len(rows), 1000):
            conn.execute(chunks.insert(), rows[start : start + 1000])
    return ChunkReport(corpus=corpus, chunks=len(rows), articles_with_chunks=with_chunks, skipped_articles=len(arts) - with_chunks)


def embed_chunks(
    engine: Engine, embedder: Embedder, cache: EmbeddingCache, corpus: str, limit: int | None = None
) -> EmbedReport:
    with engine.connect() as conn:
        query = (
            select(chunks.c.id, chunks.c.embed_text)
            .join(documents, documents.c.id_norma == chunks.c.document_id)
            .where(documents.c.corpus == corpus)
            .where((chunks.c.embedding.is_(None)) | (chunks.c.embedding_model != embedder.name))
            .order_by(chunks.c.id)
        )
        if limit is not None:
            query = query.limit(limit)
        pending = [(r[0], r[1]) for r in conn.execute(query)]
    hits_before = cache.hits
    embedded = 0
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        vectors = embed_with_cache(embedder, cache, [text for _, text in batch])
        with engine.begin() as conn:
            for (chunk_id, _), vector in zip(batch, vectors, strict=True):
                conn.execute(
                    update(chunks)
                    .where(chunks.c.id == chunk_id)
                    .values(embedding=vector.tolist(), embedding_model=embedder.name)
                )
        embedded += len(batch)
        cache.save()
    return EmbedReport(corpus=corpus, embedded=embedded, cached=cache.hits - hits_before, model=embedder.name)
```

- [ ] **Step 4: Implement retrieval**

`src/legal_ai/retrieval/__init__.py`: empty. `src/legal_ai/retrieval/types.py`:
```python
from pydantic import BaseModel


class Candidate(BaseModel):
    chunk_id: str
    version_id: str
    article_id: str
    document_id: int
    score: float
    rank: int
    retriever: str
    context_prefix: str
    text: str
```

`src/legal_ai/retrieval/vector.py`:
```python
from sqlalchemy import text
from sqlalchemy.engine import Connection

from legal_ai.retrieval.types import Candidate

VECTOR_SQL = """
SELECT id, version_id, article_id, document_id, context_prefix, text,
       1 - (embedding <=> CAST(:q AS vector)) AS score
FROM chunks
WHERE embedding IS NOT NULL
ORDER BY embedding <=> CAST(:q AS vector)
LIMIT :k
"""


def retrieve_vector(conn: Connection, query_vector: list[float], k: int) -> list[Candidate]:
    literal = "[" + ",".join(f"{v:.8f}" for v in query_vector) + "]"
    rows = conn.execute(text(VECTOR_SQL), {"q": literal, "k": k}).mappings()
    return [
        Candidate(
            chunk_id=row["id"],
            version_id=row["version_id"],
            article_id=row["article_id"],
            document_id=row["document_id"],
            score=float(row["score"]),
            rank=index + 1,
            retriever="vector",
            context_prefix=row["context_prefix"],
            text=row["text"],
        )
        for index, row in enumerate(rows)
    ]
```

`src/legal_ai/retrieval/retriever.py`:
```python
from sqlalchemy.engine import Engine

from legal_ai.index.embeddings import Embedder
from legal_ai.retrieval.types import Candidate
from legal_ai.retrieval.vector import retrieve_vector


class Retriever:
    def __init__(self, engine: Engine, embedder: Embedder) -> None:
        self._engine = engine
        self._embedder = embedder

    def embed_query(self, query: str) -> list[float]:
        return self._embedder.embed([query])[0].tolist()

    def search(self, query: str, k: int = 8) -> list[Candidate]:
        vector = self.embed_query(query)
        with self._engine.connect() as conn:
            return retrieve_vector(conn, vector, k)
```

- [ ] **Step 5: CLI**

`src/legal_ai/index/cli.py`:
```python
from typing import Annotated

import typer

from legal_ai.db.engine import ensure_database, make_engine, upgrade_database
from legal_ai.index.embed import build_corpus_chunks, embed_chunks
from legal_ai.index.embeddings import EmbeddingCache, get_embedder
from legal_ai.index.load import load_corpus
from legal_ai.ingest.layout import ProcessedLayout
from legal_ai.settings import Settings

db_app = typer.Typer(help="Base de datos: migraciones.")
index_app = typer.Typer(help="Índice: carga, chunks y embeddings en Postgres.")


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Crea la base si no existe y aplica las migraciones de Alembic."""
    settings = Settings()
    ensure_database(settings.database_url)
    upgrade_database(settings.database_url)
    typer.echo(f"migrado: {settings.database_url}")


@index_app.command("load")
def index_load(corpus: Annotated[str, typer.Argument(help="Corpus parseado (data/processed/<corpus>).")]) -> None:
    """Carga documents/articles/versions/relations/history en Postgres (idempotente)."""
    settings = Settings()
    report = load_corpus(make_engine(settings.database_url), ProcessedLayout(settings.data_dir), corpus)
    typer.echo(report.model_dump_json(indent=2))


@index_app.command("chunk")
def index_chunk(corpus: Annotated[str, typer.Argument()]) -> None:
    """Regenera los chunks del corpus a partir de las versiones vigentes."""
    settings = Settings()
    report = build_corpus_chunks(make_engine(settings.database_url), corpus)
    typer.echo(report.model_dump_json(indent=2))


@index_app.command("embed")
def index_embed(
    corpus: Annotated[str, typer.Argument()],
    model: Annotated[str | None, typer.Option("--model", help="hashing | BAAI/bge-m3 (default: settings).")] = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
) -> None:
    """Calcula embeddings de los chunks sin vector (o con otro modelo) y los guarda."""
    settings = Settings()
    name = model or settings.embedding_model
    embedder = get_embedder(name)
    cache = EmbeddingCache(settings.data_dir / "processed" / corpus / "embeddings" / f"{name.replace('/', '_')}.npz")
    report = embed_chunks(make_engine(settings.database_url), embedder, cache, corpus, limit)
    typer.echo(report.model_dump_json(indent=2))
```

Modify `src/legal_ai/cli.py`:
```python
from typing import Annotated

import typer

from legal_ai.index.cli import db_app, index_app
from legal_ai.ingest.cli import app as ingest_app
from legal_ai.parse.cli import run as parse_run

app = typer.Typer(help="Legal AI Argentina: herramientas de ingestion, indexado y evaluación.")
app.add_typer(ingest_app, name="ingest")
app.command("parse", help="Parsea el HTML de Infoleg a data/processed/<corpus>/*.jsonl.")(parse_run)
app.add_typer(db_app, name="db")
app.add_typer(index_app, name="index")


@app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="Pregunta o texto a buscar.")],
    k: Annotated[int, typer.Option("--k")] = 8,
    model: Annotated[str | None, typer.Option("--model")] = None,
) -> None:
    """Búsqueda vectorial: muestra los k chunks más cercanos con score."""
    from legal_ai.db.engine import make_engine
    from legal_ai.index.embeddings import get_embedder
    from legal_ai.retrieval.retriever import Retriever
    from legal_ai.settings import Settings

    settings = Settings()
    retriever = Retriever(make_engine(settings.database_url), get_embedder(model or settings.embedding_model))
    for c in retriever.search(query, k):
        typer.echo(f"{c.rank:2d} {c.score:.3f} {c.article_id:>16} {c.context_prefix[:90]}")


@app.callback()
def main() -> None:
    pass
```

- [ ] **Step 6: Run tests, lint, types**

Run: `uv run pytest tests/index tests/retrieval -v && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run legal-ai --help`
Expected: all passed; `db`, `index`, `search` listed. If `retrieve_vector` fails with "operator does not exist: vector <=> vector" the extension is missing (Task 1); if it fails on the parameter type, keep the `CAST(:q AS vector)` and pass the bracketed literal string.

- [ ] **Step 7: Commit**

```bash
git add src/legal_ai tests
git commit -m "Chunk, embed and search the corpus in Postgres with pgvector"
```

---

### Task 6: Grounded generation with Claude structured output

**Files:**
- Create: `src/legal_ai/generation/__init__.py`, `src/legal_ai/generation/schema.py`, `src/legal_ai/generation/prompt.py`, `src/legal_ai/generation/claude.py`, `tests/generation/__init__.py`, `tests/generation/test_prompt.py`, `tests/generation/test_claude.py`

**Interfaces:**
- Produces:
  ```python
  # schema.py
  class Claim(BaseModel): claim: str; sources: list[str]           # sources are version ids like "25552:245@current"
  class GroundedAnswer(BaseModel): answer: str; claims: list[Claim]; confidence: Literal["high","medium","low"]; insufficient_evidence: bool
  # prompt.py
  SYSTEM_PROMPT: str   # Spanish; rules: only from context; cite by [id]; say insufficient evidence; not legal advice
  def build_context(candidates: list[Candidate]) -> str      # blocks "[25552:245@current] <prefix>\n<text>"
  def build_user_message(question: str, context: str) -> str
  # claude.py
  class Usage(BaseModel): input_tokens: int; output_tokens: int; cache_read_input_tokens: int = 0; cache_creation_input_tokens: int = 0
  class Generation(BaseModel): answer: GroundedAnswer; usage: Usage; model: str; stop_reason: str | None; unsupported_sources: list[str]
  class ClaudeGenerator:
      def __init__(self, client, model: str) -> None
      def generate(self, question: str, candidates: list[Candidate]) -> Generation
  def make_client(api_key: str | None)   # anthropic.Anthropic(api_key=api_key) if key else anthropic.Anthropic()
  ```
- `generate` calls `client.messages.parse(model=..., max_tokens=4096, system=SYSTEM_PROMPT, cache_control={"type": "ephemeral"}, messages=[{"role": "user", "content": user_message}], output_format=GroundedAnswer)`; if `response.stop_reason == "refusal"` it returns a `GroundedAnswer(answer="", claims=[], confidence="low", insufficient_evidence=True)` with `stop_reason="refusal"`. `unsupported_sources` are claim sources not among the candidate `version_id`s.

- [ ] **Step 1: Write the failing tests**

`tests/generation/__init__.py`: empty. `tests/generation/test_prompt.py`:
```python
from legal_ai.generation.prompt import SYSTEM_PROMPT, build_context, build_user_message
from legal_ai.retrieval.types import Candidate


def cand(i: int, version: str, text: str) -> Candidate:
    return Candidate(chunk_id=f"{version}#0", version_id=version, article_id=version.split("@")[0], document_id=25552, score=1 - i * 0.1, rank=i, retriever="vector", context_prefix=f"Ley 20744 · Art. {i}", text=text)


def test_build_context_labels_blocks_with_version_ids():
    context = build_context([cand(1, "25552:245@current", "Texto del 245."), cand(2, "25552:92bis@current", "Texto del 92 bis.")])
    assert context.startswith("[25552:245@current] Ley 20744 · Art. 1\nTexto del 245.")
    assert "\n\n[25552:92bis@current] Ley 20744 · Art. 2\nTexto del 92 bis." in context


def test_user_message_and_system_prompt_rules():
    message = build_user_message("¿Cuánto dura el período de prueba?", "[x] ctx")
    assert "¿Cuánto dura el período de prueba?" in message and "[x] ctx" in message
    for rule in ("únicamente", "insufficient_evidence", "asesoramiento", "[25552:245@current]"):
        assert rule in SYSTEM_PROMPT
```

`tests/generation/test_claude.py`:
```python
from types import SimpleNamespace

from legal_ai.generation.claude import ClaudeGenerator
from legal_ai.generation.schema import Claim, GroundedAnswer
from legal_ai.retrieval.types import Candidate


class FakeMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed = parsed
        self.stop_reason = stop_reason
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            parsed_output=self.parsed,
            stop_reason=self.stop_reason,
            model=kwargs["model"],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=150, cache_read_input_tokens=1000, cache_creation_input_tokens=0),
        )


def make_client(parsed, stop_reason="end_turn"):
    messages = FakeMessages(parsed, stop_reason)
    return SimpleNamespace(messages=messages), messages


def candidates():
    return [
        Candidate(chunk_id="25552:92bis@current#0", version_id="25552:92bis@current", article_id="25552:92bis", document_id=25552, score=0.9, rank=1, retriever="vector", context_prefix="Ley 20744 · Art. 92 bis — Período de prueba", text="El contrato se entenderá celebrado a prueba durante los primeros seis (6) meses."),
    ]


def test_generate_passes_schema_prompt_and_context_and_validates_sources():
    parsed = GroundedAnswer(
        answer="Seis meses.",
        claims=[Claim(claim="El período de prueba dura seis meses.", sources=["25552:92bis@current"]), Claim(claim="Inventado.", sources=["25552:999@current"])],
        confidence="high",
        insufficient_evidence=False,
    )
    client, messages = make_client(parsed)
    generation = ClaudeGenerator(client, "claude-opus-5").generate("¿Cuánto dura el período de prueba?", candidates())
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5" and call["output_format"] is GroundedAnswer
    assert call["cache_control"] == {"type": "ephemeral"}
    assert "[25552:92bis@current]" in call["messages"][0]["content"]
    assert generation.answer.answer == "Seis meses."
    assert generation.unsupported_sources == ["25552:999@current"]
    assert generation.usage.input_tokens == 1200 and generation.usage.cache_read_input_tokens == 1000
    assert generation.stop_reason == "end_turn"


def test_refusal_becomes_insufficient_evidence():
    client, _ = make_client(None, stop_reason="refusal")
    generation = ClaudeGenerator(client, "claude-opus-5").generate("pregunta", candidates())
    assert generation.answer.insufficient_evidence is True and generation.answer.claims == []
    assert generation.stop_reason == "refusal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/generation -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/generation/__init__.py`: empty. `src/legal_ai/generation/schema.py`:
```python
from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    claim: str = Field(description="Una afirmación jurídica concreta, en castellano.")
    sources: list[str] = Field(description="Ids de versión del contexto que la sostienen, ej. 25552:245@current.")


class GroundedAnswer(BaseModel):
    answer: str = Field(description="Respuesta en castellano, breve y precisa, citando los ids entre corchetes.")
    claims: list[Claim]
    confidence: Literal["high", "medium", "low"]
    insufficient_evidence: bool = Field(description="true si el contexto no alcanza para responder.")
```

`src/legal_ai/generation/prompt.py`:
```python
from legal_ai.retrieval.types import Candidate

SYSTEM_PROMPT = """Sos un asistente de investigación jurídica sobre legislación laboral argentina.
Respondés únicamente con la evidencia del CONTEXTO que recibís: fragmentos de artículos, cada uno
precedido por un id entre corchetes, por ejemplo [25552:245@current].

Reglas:
1. Cada afirmación jurídica de tu respuesta tiene que estar sostenida por al menos un fragmento del
   contexto. En `claims` listá cada afirmación con los ids exactos que la sostienen.
2. En `answer` citá los ids entre corchetes al final de la oración que sostienen.
3. Si el contexto no alcanza para responder, o la pregunta habla de algo que no está en los fragmentos,
   marcá `insufficient_evidence: true`, explicá qué falta y no completes con conocimiento general.
4. No inventes números, plazos ni montos que no aparezcan textualmente en el contexto.
5. Si el fragmento indica una fecha de vigencia, mencionala cuando sea relevante.
6. Esto no es asesoramiento jurídico y no debés presentarlo como tal.
Respondé en castellano rioplatense, sin rodeos."""


def build_context(candidates: list[Candidate]) -> str:
    blocks = [f"[{c.version_id}] {c.context_prefix}\n{c.text}" for c in candidates]
    return "\n\n".join(blocks)


def build_user_message(question: str, context: str) -> str:
    return f"CONTEXTO:\n\n{context}\n\nPREGUNTA: {question}"
```

`src/legal_ai/generation/claude.py`:
```python
from typing import Any

import anthropic
from pydantic import BaseModel

from legal_ai.generation.prompt import SYSTEM_PROMPT, build_context, build_user_message
from legal_ai.generation.schema import GroundedAnswer
from legal_ai.retrieval.types import Candidate


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class Generation(BaseModel):
    answer: GroundedAnswer
    usage: Usage
    model: str
    stop_reason: str | None
    unsupported_sources: list[str]


def make_client(api_key: str | None) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


class ClaudeGenerator:
    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    def generate(self, question: str, candidates: list[Candidate]) -> Generation:
        message = build_user_message(question, build_context(candidates))
        response = self._client.messages.parse(
            model=self._model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            cache_control={"type": "ephemeral"},
            messages=[{"role": "user", "content": message}],
            output_format=GroundedAnswer,
        )
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            answer = GroundedAnswer(answer="", claims=[], confidence="low", insufficient_evidence=True)
        else:
            answer = response.parsed_output
        known = {c.version_id for c in candidates}
        unsupported = sorted({s for claim in answer.claims for s in claim.sources if s not in known})
        return Generation(
            answer=answer,
            usage=usage,
            model=response.model,
            stop_reason=response.stop_reason,
            unsupported_sources=unsupported,
        )
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/generation -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 4 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/generation tests/generation
git commit -m "Generate grounded answers with Claude structured output and source validation"
```

---

### Task 7: Pipeline, tracing, API and `ask`

**Files:**
- Create: `src/legal_ai/observability/__init__.py`, `src/legal_ai/observability/tracing.py`, `src/legal_ai/pipeline.py`, `src/legal_ai/api/__init__.py`, `src/legal_ai/api/app.py`, `tests/test_pipeline_api.py`
- Modify: `src/legal_ai/cli.py`

**Interfaces:**
- Produces:
  ```python
  # observability/tracing.py
  def setup_tracing(service_name: str, otlp_endpoint: str | None, traces_path: Path) -> Tracer
      # TracerProvider with a JsonlSpanExporter always (one JSON line per span: name, trace_id, span_id, parent_id, start, end, duration_ms, attributes) and an OTLP HTTP exporter when otlp_endpoint is set
  # pipeline.py
  class Timing(BaseModel): retrieval_ms: float; context_ms: float; llm_ms: float | None; total_ms: float
  class AskResponse(BaseModel): question: str; answer: GroundedAnswer | None; sources: list[str]; candidates: list[Candidate]; unsupported_sources: list[str]; usage: Usage | None; model: str | None; timing: Timing; trace_id: str
  class Pipeline:
      def __init__(self, retriever: Retriever, generator: ClaudeGenerator | None, tracer: Tracer) -> None
      def ask(self, question: str, k: int = 8, generate: bool = True) -> AskResponse
  def build_pipeline(settings: Settings, embedder_name: str | None = None) -> Pipeline   # generator is None when no API key
  # api/app.py
  def create_app(pipeline_factory=build_pipeline) -> FastAPI   # GET /health -> {"status": "ok", "db": true}; POST /ask {"question": str, "k": int = 8} -> AskResponse
  ```
- Spans: `ask` (root; attrs `legal_ai.question`, `legal_ai.k`), `retrieval.vector` (`legal_ai.candidates` = list of `version_id:score`), `context.build` (`legal_ai.context_chars`), `gen_ai.chat` (`gen_ai.system="anthropic"`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`).
- CLI: `legal-ai ask "<pregunta>" [--k 8] [--no-generate]` prints answer, claims with sources, and timing; `legal-ai serve [--port 8000]` runs uvicorn.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline_api.py`:
```python
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from legal_ai.api.app import create_app
from legal_ai.generation.claude import ClaudeGenerator
from legal_ai.generation.schema import Claim, GroundedAnswer
from legal_ai.index.embed import build_corpus_chunks, embed_chunks
from legal_ai.index.embeddings import EmbeddingCache, HashingEmbedder
from legal_ai.index.load import load_corpus
from legal_ai.observability.tracing import setup_tracing
from legal_ai.pipeline import Pipeline
from legal_ai.retrieval.retriever import Retriever
from tests.generation.test_claude import make_client
from tests.index.test_load import parsed_corpus


def indexed(db, tmp_path: Path):
    load_corpus(db, parsed_corpus(tmp_path), "mini")
    build_corpus_chunks(db, "mini")
    embed_chunks(db, HashingEmbedder(), EmbeddingCache(tmp_path / "emb.npz"), "mini")


def fake_generator():
    parsed = GroundedAnswer(answer="Seis meses [25552:92bis@current].", claims=[Claim(claim="Dura seis meses.", sources=["25552:92bis@current"])], confidence="high", insufficient_evidence=False)
    client, _ = make_client(parsed)
    return ClaudeGenerator(client, "claude-opus-5")


def test_pipeline_ask_traces_and_answers(db, tmp_path: Path):
    indexed(db, tmp_path)
    traces = tmp_path / "spans.jsonl"
    tracer = setup_tracing("legal-ai-test", None, traces)
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), fake_generator(), tracer)
    response = pipeline.ask("¿Cuánto dura el período de prueba?", k=5)
    assert response.answer is not None and response.answer.answer.startswith("Seis meses")
    assert response.sources == ["25552:92bis@current"] and response.unsupported_sources == []
    assert len(response.candidates) == 5 and response.timing.total_ms > 0 and response.timing.llm_ms is not None
    assert len(response.trace_id) == 32
    from opentelemetry import trace as ot

    ot.get_tracer_provider().force_flush()
    names = {json.loads(line)["name"] for line in traces.read_text().splitlines()}
    assert {"ask", "retrieval.vector", "context.build", "gen_ai.chat"} <= names


def test_pipeline_without_generator_returns_candidates_only(db, tmp_path: Path):
    indexed(db, tmp_path)
    tracer = setup_tracing("legal-ai-test", None, tmp_path / "s.jsonl")
    response = Pipeline(Retriever(db, HashingEmbedder()), None, tracer).ask("período de prueba", k=3)
    assert response.answer is None and response.timing.llm_ms is None and len(response.candidates) == 3


def test_api_health_and_ask(db, tmp_path: Path):
    indexed(db, tmp_path)
    tracer = setup_tracing("legal-ai-test", None, tmp_path / "s.jsonl")
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), fake_generator(), tracer)
    app = create_app(lambda: pipeline)
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    body = client.post("/ask", json={"question": "¿Cuánto dura el período de prueba?", "k": 4}).json()
    assert body["answer"]["answer"].startswith("Seis meses") and len(body["candidates"]) == 4
    assert client.post("/ask", json={"question": ""}).status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_pipeline_api.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement tracing**

`src/legal_ai/observability/__init__.py`: empty. `src/legal_ai/observability/tracing.py`:
```python
import json
from collections.abc import Sequence
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Tracer


class JsonlSpanExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self.path.open("a", encoding="utf-8") as fh:
            for span in spans:
                context = span.get_span_context()
                parent = span.parent.span_id if span.parent else None
                start = span.start_time or 0
                end = span.end_time or start
                fh.write(
                    json.dumps(
                        {
                            "name": span.name,
                            "trace_id": format(context.trace_id, "032x"),
                            "span_id": format(context.span_id, "016x"),
                            "parent_id": format(parent, "016x") if parent else None,
                            "start_ns": start,
                            "end_ns": end,
                            "duration_ms": (end - start) / 1e6,
                            "attributes": dict(span.attributes or {}),
                            "status": span.status.status_code.name,
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def setup_tracing(service_name: str, otlp_endpoint: str | None, traces_path: Path) -> Tracer:
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(traces_path)))
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    trace.set_tracer_provider(provider)
    return provider.get_tracer(service_name)
```

Note: `trace.set_tracer_provider` only takes effect once per process; the tests call `setup_tracing` several times, so return `provider.get_tracer(...)` from the newly created provider (as written) rather than `trace.get_tracer(...)`, and in the test flush via `ot.get_tracer_provider().force_flush()` only for the first-created provider; if the JSONL assertion fails because a later provider wrote elsewhere, assert against the tracer's own provider instead: keep a module-level `_provider` and expose `def flush() -> None` that calls `_provider.force_flush()`; use `flush()` in the test.

- [ ] **Step 4: Implement pipeline**

`src/legal_ai/pipeline.py`:
```python
import time

from opentelemetry.trace import Tracer, format_trace_id
from pydantic import BaseModel

from legal_ai.db.engine import make_engine
from legal_ai.generation.claude import ClaudeGenerator, Usage, make_client
from legal_ai.generation.prompt import build_context
from legal_ai.generation.schema import GroundedAnswer
from legal_ai.index.embeddings import get_embedder
from legal_ai.observability.tracing import setup_tracing
from legal_ai.retrieval.retriever import Retriever
from legal_ai.retrieval.types import Candidate
from legal_ai.settings import Settings


class Timing(BaseModel):
    retrieval_ms: float
    context_ms: float
    llm_ms: float | None
    total_ms: float


class AskResponse(BaseModel):
    question: str
    answer: GroundedAnswer | None
    sources: list[str]
    candidates: list[Candidate]
    unsupported_sources: list[str]
    usage: Usage | None
    model: str | None
    timing: Timing
    trace_id: str


def _ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


class Pipeline:
    def __init__(self, retriever: Retriever, generator: ClaudeGenerator | None, tracer: Tracer) -> None:
        self._retriever = retriever
        self._generator = generator
        self._tracer = tracer

    def ask(self, question: str, k: int = 8, generate: bool = True) -> AskResponse:
        total_start = time.perf_counter()
        with self._tracer.start_as_current_span("ask") as root:
            root.set_attribute("legal_ai.question", question)
            root.set_attribute("legal_ai.k", k)
            start = time.perf_counter()
            with self._tracer.start_as_current_span("retrieval.vector") as span:
                candidates = self._retriever.search(question, k)
                span.set_attribute("legal_ai.candidates", [f"{c.version_id}:{c.score:.3f}" for c in candidates])
            retrieval_ms = _ms(start)
            start = time.perf_counter()
            with self._tracer.start_as_current_span("context.build") as span:
                context = build_context(candidates)
                span.set_attribute("legal_ai.context_chars", len(context))
            context_ms = _ms(start)
            answer = usage = model = None
            unsupported: list[str] = []
            llm_ms: float | None = None
            if generate and self._generator is not None:
                start = time.perf_counter()
                with self._tracer.start_as_current_span("gen_ai.chat") as span:
                    span.set_attribute("gen_ai.system", "anthropic")
                    span.set_attribute("gen_ai.request.model", self._generator._model)
                    generation = self._generator.generate(question, candidates)
                    span.set_attribute("gen_ai.usage.input_tokens", generation.usage.input_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", generation.usage.output_tokens)
                    span.set_attribute("gen_ai.response.finish_reasons", [generation.stop_reason or ""])
                llm_ms = _ms(start)
                answer, usage, model, unsupported = generation.answer, generation.usage, generation.model, generation.unsupported_sources
            sources = sorted({s for claim in (answer.claims if answer else []) for s in claim.sources if s not in unsupported})
            trace_id = format_trace_id(root.get_span_context().trace_id)
        return AskResponse(
            question=question,
            answer=answer,
            sources=sources,
            candidates=candidates,
            unsupported_sources=unsupported,
            usage=usage,
            model=model,
            timing=Timing(retrieval_ms=retrieval_ms, context_ms=context_ms, llm_ms=llm_ms, total_ms=_ms(total_start)),
            trace_id=trace_id,
        )


def build_pipeline(settings: Settings | None = None, embedder_name: str | None = None) -> Pipeline:
    settings = settings or Settings()
    tracer = setup_tracing("legal-ai", settings.otlp_endpoint, settings.traces_path)
    retriever = Retriever(make_engine(settings.database_url), get_embedder(embedder_name or settings.embedding_model))
    generator = ClaudeGenerator(make_client(settings.anthropic_api_key), settings.llm_model) if settings.anthropic_api_key else None
    return Pipeline(retriever, generator, tracer)
```

- [ ] **Step 5: Implement API and CLI**

`src/legal_ai/api/__init__.py`: empty. `src/legal_ai/api/app.py`:
```python
from collections.abc import Callable
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import text

from legal_ai.pipeline import AskResponse, Pipeline, build_pipeline


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    k: int = Field(default=8, ge=1, le=50)


def create_app(pipeline_factory: Callable[[], Pipeline] = build_pipeline) -> FastAPI:
    app = FastAPI(title="Legal AI Argentina", version="0.1.0")
    get_pipeline = lru_cache(maxsize=1)(pipeline_factory)

    @app.get("/health")
    def health() -> dict[str, object]:
        pipeline = get_pipeline()
        with pipeline._retriever._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": True, "generation": pipeline._generator is not None}

    @app.post("/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        return get_pipeline().ask(request.question, request.k)

    return app


app = create_app()
```

Add to `src/legal_ai/cli.py` (after `search`):
```python
@app.command("ask")
def ask(
    question: Annotated[str, typer.Argument(help="Pregunta en castellano.")],
    k: Annotated[int, typer.Option("--k")] = 8,
    generate: Annotated[bool, typer.Option("--generate/--no-generate")] = True,
) -> None:
    """Pipeline completo: retrieval → contexto → Claude → respuesta con citas."""
    from legal_ai.pipeline import build_pipeline

    response = build_pipeline().ask(question, k, generate)
    if response.answer is None:
        typer.echo("(sin generación: falta ANTHROPIC_API_KEY o --no-generate)")
    else:
        typer.echo(response.answer.answer)
        typer.echo("")
        for claim in response.answer.claims:
            typer.echo(f"- {claim.claim}  ← {', '.join(claim.sources)}")
        if response.answer.insufficient_evidence:
            typer.echo("⚠ evidencia insuficiente según el modelo")
        if response.unsupported_sources:
            typer.echo(f"⚠ fuentes fuera del contexto: {response.unsupported_sources}")
    typer.echo("")
    for c in response.candidates:
        typer.echo(f"{c.rank:2d} {c.score:.3f} {c.version_id:>24} {c.context_prefix[:80]}")
    t = response.timing
    typer.echo(f"\nretrieval {t.retrieval_ms:.0f} ms · llm {t.llm_ms or 0:.0f} ms · total {t.total_ms:.0f} ms · trace {response.trace_id}")


@app.command("serve")
def serve(port: Annotated[int, typer.Option("--port")] = 8000) -> None:
    """Levanta la API HTTP (FastAPI + uvicorn)."""
    import uvicorn

    uvicorn.run("legal_ai.api.app:app", host="127.0.0.1", port=port)
```
Ensure `from typing import Annotated` and `import typer` are at the top (they are, from Task 5).

- [ ] **Step 6: Run tests, lint, types**

Run: `uv run pytest tests/test_pipeline_api.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: all passed, clean. If pyright complains about accessing `_retriever`/`_generator`/`_model` (private attributes) from `app.py`/`pipeline.py`, add public read-only properties `retriever`, `generator`, `model` to `Pipeline` and `ClaudeGenerator` and use those.

- [ ] **Step 7: Commit**

```bash
git add src/legal_ai tests/test_pipeline_api.py
git commit -m "Wire the RAG pipeline with OpenTelemetry spans, FastAPI and the ask command"
```

---

### Task 8: Smoke benchmark, real run, docs

**Files:**
- Create: `eval/smoke_questions.jsonl`, `src/legal_ai/bench.py`, `tests/test_bench.py`, `experiments/.gitkeep`
- Modify: `src/legal_ai/cli.py`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, `README.md`, `.gitignore` (add `data/traces/`)

**Interfaces:**
- `eval/smoke_questions.jsonl`: one JSON per line `{"id": "s01", "question": "...", "expected_articles": ["25552:92bis"], "category": "direct"}`. These are smoke questions for latency and sanity, not the Phase 4 benchmark. Twenty lines, written now:
  ```
  {"id":"s01","question":"¿Cuánto dura el período de prueba en un contrato por tiempo indeterminado?","expected_articles":["25552:92bis"],"category":"direct"}
  {"id":"s02","question":"¿Qué plazo de preaviso debe dar el empleador a un trabajador con más de cinco años de antigüedad?","expected_articles":["25552:231"],"category":"direct"}
  {"id":"s03","question":"¿Cómo se calcula la indemnización por antigüedad en caso de despido sin causa?","expected_articles":["25552:245"],"category":"direct"}
  {"id":"s04","question":"¿Qué es el despido indirecto?","expected_articles":["25552:246"],"category":"direct"}
  {"id":"s05","question":"¿Cuáles son las fuentes de regulación del contrato de trabajo?","expected_articles":["25552:1"],"category":"direct"}
  {"id":"s06","question":"¿Qué se entiende por contrato de trabajo?","expected_articles":["25552:21"],"category":"direct"}
  {"id":"s07","question":"¿Qué obligación tiene el empleador de entregar certificados al terminar la relación laboral?","expected_articles":["25552:80"],"category":"direct"}
  {"id":"s08","question":"¿Cuántos días de vacaciones corresponden según la antigüedad?","expected_articles":["25552:150"],"category":"direct"}
  {"id":"s09","question":"¿Qué licencias especiales tiene el trabajador, por ejemplo por nacimiento de hijo o matrimonio?","expected_articles":["25552:158"],"category":"direct"}
  {"id":"s10","question":"¿Qué pasa si el empleador despide a una trabajadora embarazada?","expected_articles":["25552:178","25552:182"],"category":"multi"}
  {"id":"s11","question":"¿Cuál es la jornada máxima de trabajo?","expected_articles":["25552:196"],"category":"context"}
  {"id":"s12","question":"¿Cómo se paga el sueldo anual complementario?","expected_articles":["25552:121","25552:122"],"category":"multi"}
  {"id":"s13","question":"¿Qué es la justa causa de despido?","expected_articles":["25552:242"],"category":"direct"}
  {"id":"s14","question":"¿Qué indemnización corresponde por falta de registración del trabajador?","expected_articles":["412:8","64555:1"],"category":"multi"}
  {"id":"s15","question":"¿Cuál es el tope indemnizatorio vigente para el convenio de comercio?","expected_articles":[],"category":"not_in_corpus"}
  {"id":"s16","question":"¿Qué dice el artículo 14 bis de la Constitución Nacional?","expected_articles":[],"category":"not_in_corpus"}
  {"id":"s17","question":"¿Puede el trabajador renunciar a derechos que le da la ley?","expected_articles":["25552:12"],"category":"direct"}
  {"id":"s18","question":"¿En qué casos no hay derecho a indemnización por despido?","expected_articles":["25552:242","25552:247"],"category":"negation"}
  {"id":"s19","question":"¿Qué diferencia hay entre suspensión por falta de trabajo y despido por fuerza mayor?","expected_articles":["25552:219","25552:247"],"category":"confusable"}
  {"id":"s20","question":"¿Está derogado el artículo 28 de la Ley de Contrato de Trabajo?","expected_articles":["25552:28"],"category":"derogated"}
  ```
- `bench.py`:
  ```python
  class QuestionResult(BaseModel): id: str; question: str; category: str; expected_articles: list[str]; retrieved_articles: list[str]; hit_at_k: bool; retrieval_ms: float; llm_ms: float | None; total_ms: float; input_tokens: int | None; output_tokens: int | None; insufficient_evidence: bool | None; unsupported_sources: list[str]; trace_id: str
  class BenchReport(BaseModel): name: str; ran_at: datetime; catalog_date: str; k: int; embedding_model: str; llm_model: str | None; n: int; hit_rate_at_k: float; p50_retrieval_ms: float; p95_retrieval_ms: float; p50_total_ms: float; p95_total_ms: float; total_input_tokens: int; total_output_tokens: int; estimated_cost_usd: float | None; results: list[QuestionResult]
  def run_smoke(pipeline: Pipeline, questions_path: Path, k: int, generate: bool, embedding_model: str, llm_model: str | None, catalog_date: str, price_in_per_mtok: float = 5.0, price_out_per_mtok: float = 25.0) -> BenchReport
  def write_report(report: BenchReport, experiments_dir: Path) -> Path    # experiments/<YYYY-MM-DD>-<name>.json
  ```
  `hit_at_k` is true when any expected article id appears among the candidates' `article_id`s; for `not_in_corpus` questions it is true when `insufficient_evidence` is true (or `None` → counted as false). Prices default to the Opus 5 rates from the API pricing table ($5 in / $25 out per MTok); cost is `None` when nothing was generated.
- CLI: `legal-ai bench smoke [--k 8] [--no-generate] [--name phase3-baseline]`.

- [ ] **Step 1: Write the failing test**

`tests/test_bench.py`:
```python
import json
from pathlib import Path

from legal_ai.bench import run_smoke, write_report
from legal_ai.index.embeddings import HashingEmbedder
from legal_ai.observability.tracing import setup_tracing
from legal_ai.pipeline import Pipeline
from legal_ai.retrieval.retriever import Retriever
from tests.test_pipeline_api import fake_generator, indexed


def test_run_smoke_computes_hits_and_percentiles(db, tmp_path: Path):
    indexed(db, tmp_path)
    questions = tmp_path / "q.jsonl"
    questions.write_text(
        json.dumps({"id": "a", "question": "período de prueba contrato por tiempo indeterminado seis meses", "expected_articles": ["25552:92bis"], "category": "direct"}) + "\n"
        + json.dumps({"id": "b", "question": "tope indemnizatorio comercio", "expected_articles": [], "category": "not_in_corpus"}) + "\n",
        encoding="utf-8",
    )
    pipeline = Pipeline(Retriever(db, HashingEmbedder()), fake_generator(), setup_tracing("t", None, tmp_path / "s.jsonl"))
    report = run_smoke(pipeline, questions, k=5, generate=True, embedding_model="hashing-1024", llm_model="claude-opus-5", catalog_date="2026-09-12")
    assert report.n == 2 and report.k == 5
    by_id = {r.id: r for r in report.results}
    assert by_id["a"].hit_at_k is True and "25552:92bis" in by_id["a"].retrieved_articles
    assert by_id["b"].hit_at_k is False
    assert report.hit_rate_at_k == 0.5
    assert report.p95_retrieval_ms >= report.p50_retrieval_ms > 0
    assert report.total_input_tokens == 2400 and report.estimated_cost_usd is not None
    path = write_report(report, tmp_path / "experiments")
    assert path.exists() and json.loads(path.read_text())["hit_rate_at_k"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/bench.py`:
```python
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from legal_ai.pipeline import Pipeline


class QuestionResult(BaseModel):
    id: str
    question: str
    category: str
    expected_articles: list[str]
    retrieved_articles: list[str]
    hit_at_k: bool
    retrieval_ms: float
    llm_ms: float | None
    total_ms: float
    input_tokens: int | None
    output_tokens: int | None
    insufficient_evidence: bool | None
    unsupported_sources: list[str]
    trace_id: str


class BenchReport(BaseModel):
    name: str
    ran_at: datetime
    catalog_date: str
    k: int
    embedding_model: str
    llm_model: str | None
    n: int
    hit_rate_at_k: float
    p50_retrieval_ms: float
    p95_retrieval_ms: float
    p50_total_ms: float
    p95_total_ms: float
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float | None
    results: list[QuestionResult]


def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def run_smoke(
    pipeline: Pipeline,
    questions_path: Path,
    k: int,
    generate: bool,
    embedding_model: str,
    llm_model: str | None,
    catalog_date: str,
    price_in_per_mtok: float = 5.0,
    price_out_per_mtok: float = 25.0,
    name: str = "phase3-baseline",
) -> BenchReport:
    results: list[QuestionResult] = []
    for line in questions_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        response = pipeline.ask(item["question"], k=k, generate=generate)
        retrieved = [c.article_id for c in response.candidates]
        insufficient = response.answer.insufficient_evidence if response.answer else None
        if item["category"] == "not_in_corpus":
            hit = insufficient is True
        else:
            hit = any(a in retrieved for a in item["expected_articles"])
        results.append(
            QuestionResult(
                id=item["id"],
                question=item["question"],
                category=item["category"],
                expected_articles=item["expected_articles"],
                retrieved_articles=retrieved,
                hit_at_k=hit,
                retrieval_ms=response.timing.retrieval_ms,
                llm_ms=response.timing.llm_ms,
                total_ms=response.timing.total_ms,
                input_tokens=response.usage.input_tokens if response.usage else None,
                output_tokens=response.usage.output_tokens if response.usage else None,
                insufficient_evidence=insufficient,
                unsupported_sources=response.unsupported_sources,
                trace_id=response.trace_id,
            )
        )
    total_in = sum(r.input_tokens or 0 for r in results)
    total_out = sum(r.output_tokens or 0 for r in results)
    generated = any(r.input_tokens is not None for r in results)
    cost = (total_in * price_in_per_mtok + total_out * price_out_per_mtok) / 1_000_000 if generated else None
    return BenchReport(
        name=name,
        ran_at=datetime.now(UTC),
        catalog_date=catalog_date,
        k=k,
        embedding_model=embedding_model,
        llm_model=llm_model if generated else None,
        n=len(results),
        hit_rate_at_k=sum(r.hit_at_k for r in results) / len(results) if results else 0.0,
        p50_retrieval_ms=_p([r.retrieval_ms for r in results], 0.5),
        p95_retrieval_ms=_p([r.retrieval_ms for r in results], 0.95),
        p50_total_ms=_p([r.total_ms for r in results], 0.5),
        p95_total_ms=_p([r.total_ms for r in results], 0.95),
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        estimated_cost_usd=cost,
        results=results,
    )


def write_report(report: BenchReport, experiments_dir: Path) -> Path:
    experiments_dir.mkdir(parents=True, exist_ok=True)
    path = experiments_dir / f"{report.ran_at.date().isoformat()}-{report.name}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path
```

Add to `src/legal_ai/cli.py`:
```python
bench_app = typer.Typer(help="Benchmarks reproducibles; escriben en experiments/.")
app.add_typer(bench_app, name="bench")


@bench_app.command("smoke")
def bench_smoke(
    k: Annotated[int, typer.Option("--k")] = 8,
    generate: Annotated[bool, typer.Option("--generate/--no-generate")] = True,
    name: Annotated[str, typer.Option("--name")] = "phase3-baseline",
) -> None:
    """Corre eval/smoke_questions.jsonl por el pipeline y guarda latencias, hits, tokens y costo."""
    from pathlib import Path

    from legal_ai.bench import run_smoke, write_report
    from legal_ai.ingest.layout import ProcessedLayout
    from legal_ai.ingest.manifest import read_resolved
    from legal_ai.pipeline import build_pipeline
    from legal_ai.settings import Settings

    settings = Settings()
    pipeline = build_pipeline(settings)
    catalog_date = read_resolved(ProcessedLayout(settings.data_dir).resolved_path("laboral")).catalog_date.isoformat()
    report = run_smoke(
        pipeline, Path("eval/smoke_questions.jsonl"), k, generate and pipeline.generator is not None,
        settings.embedding_model, settings.llm_model, catalog_date, name=name,
    )
    path = write_report(report, Path("experiments"))
    typer.echo(f"n={report.n} hit@{k}={report.hit_rate_at_k:.2f} retrieval p50/p95={report.p50_retrieval_ms:.0f}/{report.p95_retrieval_ms:.0f} ms total p50/p95={report.p50_total_ms:.0f}/{report.p95_total_ms:.0f} ms tokens in/out={report.total_input_tokens}/{report.total_output_tokens} cost={report.estimated_cost_usd}")
    for r in report.results:
        mark = "✓" if r.hit_at_k else "✗"
        typer.echo(f"{mark} {r.id} {r.category:<14} {r.total_ms:6.0f} ms  {r.question[:70]}")
    typer.echo(f"escrito: {path}")
```
(`pipeline.generator` requires the public property from Task 7 Step 6.)

Add `data/traces/` to `.gitignore` and create `experiments/.gitkeep`.

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: green.

- [ ] **Step 5: Commit the code**

```bash
git add eval src/legal_ai/bench.py src/legal_ai/cli.py tests/test_bench.py experiments/.gitkeep .gitignore
git commit -m "Add the smoke benchmark with latency, hit@k, tokens and cost"
```

- [ ] **Step 6: Real run**

```bash
docker compose up -d postgres
uv run legal-ai db upgrade
uv run legal-ai index load laboral
uv run legal-ai index chunk laboral
uv run legal-ai index embed laboral --model hashing
uv run legal-ai search "¿Cuánto dura el período de prueba?" --model hashing
uv run legal-ai bench smoke --no-generate --name phase3-hashing-retrieval-only
```
Expected: load report with 933 documents; chunk report with a few thousand chunks; hashing embeddings in seconds; `search` returns 8 candidates; bench writes `experiments/<date>-phase3-hashing-retrieval-only.json`. Record `hit@8` and p50/p95.

Then bge-m3 (downloads ~2.3 GB once; embedding 4–5k chunks on Apple Silicon takes minutes):
```bash
uv run legal-ai index embed laboral
uv run legal-ai search "¿Cuánto dura el período de prueba?"
uv run legal-ai bench smoke --no-generate --name phase3-bgem3-retrieval-only
```
Record `hit@8` and latencies. Then, if `ANTHROPIC_API_KEY` is in `.env`:
```bash
uv run legal-ai ask "¿Cuánto dura el período de prueba en un contrato por tiempo indeterminado?"
uv run legal-ai bench smoke --name phase3-baseline
```
Record hit rate, p50/p95 total, tokens and cost. Inspect the two `not_in_corpus` questions: `insufficient_evidence` must be true for both; if the model answered s15 with a number, that is the first documented grounding failure and goes into the roadmap as a Phase 8 test case. Check `data/traces/spans.jsonl` has `gen_ai.chat` spans with token attributes.

- [ ] **Step 7: Document**

`docs/ARCHITECTURE.md`: in *Retrieval*, replace the vector bullet with the exact SQL of `VECTOR_SQL` in a code block; in *chunks*, state the baseline selection rule and the `HashingEmbedder` as the no-download fallback; in *Observabilidad*, state that spans always go to `data/traces/spans.jsonl` and to OTLP when `LEGAL_AI_OTLP_ENDPOINT` is set, and that Langfuse's Compose stack is a Phase 13 task. `docs/DECISIONS.md`: append
```
## ADR-018: Baseline de chunks: una versión vigente por artículo, con prefijo de contexto

**Decisión.** El chunk baseline es la versión `current` (o la `original` si no hay
actualizada), sólo `vigente`, con texto, fuera de anexos. Se embebe
`context_prefix + "\n" + text`. Artículos de más de 2.500 caracteres se
parten por incisos. Anexos, derogados y preámbulos quedan para experimentos
de la Fase 5.

**Alternativas.** Chunks de N tokens con solapamiento: pierde la identidad
jurídica (ADR-005). Indexar todas las versiones: mezcla vigente e histórico
antes de tener el filtro temporal de la Fase 9.

## ADR-019: Embedder intercambiable con un fallback determinista

**Decisión.** `Embedder` es un protocolo; `bge-m3` es el modelo del baseline y
`HashingEmbedder` (feature hashing de unigramas y bigramas, 1024 dimensiones)
es el fallback sin descarga que usan los tests y sirve como control: si un
modelo de 2 GB no supera al hashing en el benchmark, algo está mal.

## ADR-020: Trazas OTel siempre a disco, OTLP opcional

**Decisión.** Cada request escribe sus spans (GenAI semantic conventions) en
`data/traces/spans.jsonl` con un exportador propio de 40 líneas, y además a un
endpoint OTLP si está configurado. Langfuse se levanta en la Fase 13; la
instrumentación no cambia.
```
`docs/ROADMAP.md`: Fase 3 `hecha`, Fase 4 `siguiente`, and a "## Fase 3 en detalle" with the real numbers from Step 6 (chunks, hashing vs bge-m3 hit@8, p50/p95, tokens, cost, the not_in_corpus behaviour). `README.md`: status "Fases 0 a 3 completas"; *Cómo ejecutar* gains `db upgrade`, `index load/chunk/embed`, `ask`, `serve`, `bench smoke`; mention Colima.

- [ ] **Step 8: Final check and commit**

Run: `uv run pytest -q && uv run ruff check . && uv run pyright && git status --short`
```bash
git add docs README.md experiments
git commit -m "Run the Phase 3 baseline on the laboral corpus and record results"
```

---

## Self-review

**Spec coverage.** Postgres + pgvector + pg_search (ADR-002) → Task 1. Chunks with context prefix (ADR-005, contextual retrieval) → Task 3. bge-m3 baseline + comparison harness (ADR-007) → Tasks 4, 8 (hashing vs bge-m3 both measured). Claude Opus 5 structured output with claims/sources/insufficient_evidence (ADR-008, Phase 8 preview) → Task 6. OTel GenAI spans (ADR-009) → Task 7; Langfuse stack explicitly deferred to Phase 13 and recorded in ADR-020. FastAPI `/ask` → Task 7. Measurement in `experiments/` → Task 8. Temporal filter (`as_of`) is not in this phase: recorded as Phase 9.

**Placeholder scan.** None. The smoke questions are written in full; expected article ids are best-effort (the LCT numbering for vacaciones 150, licencias 158, jornada 196, SAC 121/122, embarazo 177/178/182, suspensión 219/247) and are labelled smoke, not benchmark; Phase 4 builds the real benchmark with the lawyers.

**Type consistency.** `Candidate` (Task 5) is consumed by `build_context` (Task 6), `Pipeline` (Task 7) and `run_smoke` (Task 8). `GroundedAnswer`/`Usage`/`Generation` names match between Tasks 6–8. `Retriever.search(query, k)` signature matches Tasks 5, 7. `setup_tracing(service_name, otlp_endpoint, traces_path)` matches Tasks 7–8. `build_pipeline(settings, embedder_name)` is used by the CLI and API. `pipeline.generator` property must exist before Task 8's CLI uses it (Task 7 Step 6 note).
