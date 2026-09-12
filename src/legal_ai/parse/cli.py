from typing import Annotated

import typer

from legal_ai.ingest.catalog import latest_snapshot, load_snapshot
from legal_ai.ingest.catalog_reader import ZipCatalog, collect_rows
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import read_resolved
from legal_ai.parse.corpus import parse_corpus
from legal_ai.settings import Settings


def run(
    corpus: Annotated[
        str, typer.Argument(help="Corpus ya resuelto y descargado (ingest resolve + fetch).")
    ],
    show_warnings: Annotated[
        bool, typer.Option("--warnings", help="Lista las advertencias por norma.")
    ] = False,
) -> None:
    """Genera data/processed/<corpus>/*.jsonl a partir de data/raw."""
    settings = Settings()
    raw = RawLayout(settings.data_dir)
    processed = ProcessedLayout(settings.data_dir)
    resolved = read_resolved(processed.resolved_path(corpus))
    snapshot = (
        load_snapshot(raw, resolved.catalog_date)
        if raw.catalog_dir(resolved.catalog_date).exists()
        else latest_snapshot(raw)
    )
    if snapshot is None:
        typer.echo("No hay snapshot del catálogo; corré `legal-ai ingest catalog`.", err=True)
        raise typer.Exit(1)
    rows = collect_rows(ZipCatalog(snapshot, raw), set(resolved.ids()))
    report = parse_corpus(resolved, rows, raw, processed)
    for key, value in report.totals.items():
        typer.echo(f"{key}: {value}")
    if show_warnings:
        for doc in report.documents:
            for warning in doc.warnings:
                typer.echo(f"[{doc.id_norma}] {warning}")
    typer.echo(f"escrito en: {processed.corpus_dir(corpus)}")
