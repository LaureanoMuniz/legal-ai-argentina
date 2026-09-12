import typer

from legal_ai.ingest.cli import app as ingest_app

app = typer.Typer(help="Legal AI Argentina: herramientas de ingestion, indexado y evaluación.")
app.add_typer(ingest_app, name="ingest")


@app.callback()
def main() -> None:
    pass
