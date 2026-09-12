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
    retriever = Retriever(
        make_engine(settings.database_url), get_embedder(model or settings.embedding_model)
    )
    for c in retriever.search(query, k):
        typer.echo(f"{c.rank:2d} {c.score:.3f} {c.article_id:>16} {c.context_prefix[:90]}")


@app.callback()
def main() -> None:
    pass
