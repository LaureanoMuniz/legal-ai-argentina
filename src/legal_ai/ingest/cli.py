from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated

import httpx
import typer

from legal_ai.ingest.catalog import (
    SnapshotExistsError,
    download_catalog,
    latest_snapshot,
    load_snapshot,
)
from legal_ai.ingest.catalog_reader import ZipCatalog
from legal_ai.ingest.fetch import FetchOutcome, InfolegClient, fetch_norm
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import load_manifest, read_resolved, resolve_corpus, write_resolved
from legal_ai.settings import Settings

app = typer.Typer(help="Descarga reproducible de Infoleg a data/raw.")


def _http(settings: Settings) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.infoleg_user_agent},
        timeout=settings.infoleg_timeout_seconds,
    )


@app.command()
def catalog(
    snapshot_date: Annotated[
        str | None, typer.Option("--date", help="Fecha del snapshot (YYYY-MM-DD). Default: hoy.")
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Reemplaza un snapshot existente.")
    ] = False,
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
    """Resuelve el manifest a id_norma y escribe data/processed/<corpus>/resolved.json."""
    settings = Settings()
    raw = RawLayout(settings.data_dir)
    processed = ProcessedLayout(settings.data_dir)
    snapshot = (
        load_snapshot(raw, date.fromisoformat(catalog_date))
        if catalog_date
        else latest_snapshot(raw)
    )
    if snapshot is None:
        typer.echo(
            "No hay ningún snapshot del catálogo; corré `legal-ai ingest catalog` primero.",
            err=True,
        )
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
    force: Annotated[
        bool, typer.Option("--force", help="Vuelve a bajar aunque esté en caché.")
    ] = False,
    limit: Annotated[
        int | None, typer.Option("--limit", help="Procesa solo las primeras N normas.")
    ] = None,
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
            label = f"{norm.tipo_norma} {norm.numero_norma} ({norm.id_norma})"
            typer.echo(f"[{i}/{len(norms)}] {label} {summary}")
            for name, error in report.errors.items():
                typer.echo(f"    {name}: {error}", err=True)
    typer.echo("total: " + " ".join(f"{o.value}={totals.get(o, 0)}" for o in FetchOutcome))
    if totals.get(FetchOutcome.FAILED):
        raise typer.Exit(1)
