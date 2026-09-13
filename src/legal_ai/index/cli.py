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
def index_load(
    corpus: Annotated[str, typer.Argument(help="Corpus parseado (data/processed/<corpus>).")],
) -> None:
    """Carga documents/articles/versions/relations/history en Postgres (idempotente)."""
    settings = Settings()
    report = load_corpus(
        make_engine(settings.database_url), ProcessedLayout(settings.data_dir), corpus
    )
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
    model: Annotated[
        str | None, typer.Option("--model", help="hashing | BAAI/bge-m3 (default: settings).")
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
) -> None:
    """Calcula embeddings de los chunks sin vector (o con otro modelo) y los guarda."""
    settings = Settings()
    name = model or settings.embedding_model
    embedder = get_embedder(name)
    cache_path = settings.data_dir / "cache" / "embeddings" / f"{name.replace('/', '_')}.npz"
    report = embed_chunks(
        make_engine(settings.database_url), embedder, EmbeddingCache(cache_path), corpus, limit
    )
    typer.echo(report.model_dump_json(indent=2))
