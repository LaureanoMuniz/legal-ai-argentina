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


@app.command("ask")
def ask(
    question: Annotated[str, typer.Argument(help="Pregunta en castellano.")],
    k: Annotated[int, typer.Option("--k")] = 8,
    generate: Annotated[bool, typer.Option("--generate/--no-generate")] = True,
    model: Annotated[str | None, typer.Option("--model")] = None,
) -> None:
    """Pipeline completo: retrieval → contexto → Claude → respuesta con citas."""
    from legal_ai.pipeline import build_pipeline

    response = build_pipeline(embedder_name=model).ask(question, k, generate)
    if response.answer is None:
        typer.echo("(sin generación: falta ANTHROPIC_API_KEY o se pasó --no-generate)")
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
    typer.echo(
        f"\nretrieval {t.retrieval_ms:.0f} ms · llm {t.llm_ms or 0:.0f} ms · "
        f"total {t.total_ms:.0f} ms · trace {response.trace_id}"
    )


@app.command("serve")
def serve(port: Annotated[int, typer.Option("--port")] = 8000) -> None:
    """Levanta la API HTTP (FastAPI + uvicorn)."""
    import uvicorn

    uvicorn.run("legal_ai.api.app:app", host="127.0.0.1", port=port)


@app.callback()
def main() -> None:
    pass
