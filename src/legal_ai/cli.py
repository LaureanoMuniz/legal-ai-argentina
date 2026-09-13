from typing import TYPE_CHECKING, Annotated

import typer

from legal_ai.index.cli import db_app, index_app
from legal_ai.ingest.cli import app as ingest_app
from legal_ai.parse.cli import run as parse_run

if TYPE_CHECKING:
    from legal_ai.retrieval.rerank import Reranker
    from legal_ai.retrieval.rewrite import Rewriter
    from legal_ai.settings import Settings

app = typer.Typer(help="Legal AI Argentina: herramientas de ingestion, indexado y evaluación.")
app.add_typer(ingest_app, name="ingest")
app.command("parse", help="Parsea el HTML de Infoleg a data/processed/<corpus>/*.jsonl.")(parse_run)
app.add_typer(db_app, name="db")
app.add_typer(index_app, name="index")
bench_app = typer.Typer(help="Benchmarks reproducibles; escriben en experiments/.")
app.add_typer(bench_app, name="bench")


@app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="Pregunta o texto a buscar.")],
    k: Annotated[int, typer.Option("--k")] = 8,
    model: Annotated[str | None, typer.Option("--model")] = None,
    retriever: Annotated[
        str | None, typer.Option("--retriever", help="vector | bm25 | rrf | hybrid")
    ] = None,
    dedupe: Annotated[bool, typer.Option("--dedupe/--no-dedupe")] = False,
    rerank: Annotated[bool | None, typer.Option("--rerank/--no-rerank")] = None,
    pool: Annotated[int | None, typer.Option("--pool")] = None,
    rewrite: Annotated[bool | None, typer.Option("--rewrite/--no-rewrite")] = None,
    multi: Annotated[bool | None, typer.Option("--multi/--no-multi")] = None,
) -> None:
    """Búsqueda: muestra los k chunks mejor rankeados con su score."""
    from legal_ai.db.engine import make_engine
    from legal_ai.index.embeddings import get_embedder
    from legal_ai.retrieval.retriever import Retriever, parse_mode
    from legal_ai.settings import Settings

    settings = Settings()
    searcher = Retriever(
        make_engine(settings.database_url),
        get_embedder(model or settings.embedding_model),
        mode=parse_mode(retriever) if retriever else settings.retrieval_mode,
        dedupe=dedupe,
        reranker=_reranker(settings, rerank),
        pool=pool or settings.rerank_pool,
        rewriter=_rewriter(settings, rewrite),
        multi_query=settings.rewrite_multi_query if multi is None else multi,
    )
    searcher.require_index()
    for c in searcher.search(query, k):
        typer.echo(f"{c.rank:2d} {c.score:.3f} {c.article_id:>16} {c.context_prefix[:90]}")


@app.command("ask")
def ask(
    question: Annotated[str, typer.Argument(help="Pregunta en castellano.")],
    k: Annotated[int, typer.Option("--k")] = 8,
    generate: Annotated[bool, typer.Option("--generate/--no-generate")] = True,
    model: Annotated[str | None, typer.Option("--model")] = None,
    retriever: Annotated[str | None, typer.Option("--retriever")] = None,
) -> None:
    """Pipeline completo: retrieval → contexto → Claude → respuesta con citas."""
    from legal_ai.pipeline import build_pipeline
    from legal_ai.retrieval.retriever import parse_mode

    mode = parse_mode(retriever) if retriever else None
    response = build_pipeline(embedder_name=model, mode=mode).ask(question, k, generate)
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


@bench_app.command("smoke")
def bench_smoke(
    k: Annotated[int, typer.Option("--k")] = 8,
    generate: Annotated[bool, typer.Option("--generate/--no-generate")] = True,
    name: Annotated[str, typer.Option("--name")] = "phase3-baseline",
    model: Annotated[str | None, typer.Option("--model")] = None,
) -> None:
    """Corre eval/smoke_questions.jsonl por el pipeline; guarda latencias, hits, tokens y costo."""
    from pathlib import Path

    from legal_ai.bench import run_smoke, write_report
    from legal_ai.ingest.layout import ProcessedLayout
    from legal_ai.ingest.manifest import read_resolved
    from legal_ai.pipeline import build_pipeline
    from legal_ai.settings import Settings

    settings = Settings()
    pipeline = build_pipeline(settings, embedder_name=model)
    pipeline.retriever.require_index()
    resolved = read_resolved(ProcessedLayout(settings.data_dir).resolved_path("laboral"))
    report = run_smoke(
        pipeline,
        Path("eval/smoke_questions.jsonl"),
        k,
        generate and pipeline.generator is not None,
        pipeline.retriever.embedder.name,
        settings.llm_model,
        resolved.catalog_date.isoformat(),
        name=name,
    )
    path = write_report(report, Path("experiments"))
    typer.echo(
        f"n={report.n} hit@{k}={report.hit_rate_at_k:.2f} "
        f"retrieval p50/p95={report.p50_retrieval_ms:.0f}/{report.p95_retrieval_ms:.0f} ms "
        f"total p50/p95={report.p50_total_ms:.0f}/{report.p95_total_ms:.0f} ms "
        f"tokens in/out={report.total_input_tokens}/{report.total_output_tokens} "
        f"cost={report.estimated_cost_usd}"
    )
    for r in report.results:
        mark = "✓" if r.hit_at_k else "✗"
        typer.echo(f"{mark} {r.id} {r.category:<14} {r.total_ms:6.0f} ms  {r.question[:70]}")
    typer.echo(f"escrito: {path}")


@bench_app.command("run")
def bench_run(
    k: Annotated[int, typer.Option("--k")] = 8,
    model: Annotated[str | None, typer.Option("--model")] = None,
    name: Annotated[str, typer.Option("--name")] = "phase4-baseline",
    questions: Annotated[str, typer.Option("--questions")] = "eval/benchmark.jsonl",
    retriever: Annotated[
        str | None, typer.Option("--retriever", help="vector | bm25 | rrf | hybrid")
    ] = None,
    dedupe: Annotated[bool, typer.Option("--dedupe/--no-dedupe")] = False,
    rerank: Annotated[bool | None, typer.Option("--rerank/--no-rerank")] = None,
    pool: Annotated[int | None, typer.Option("--pool")] = None,
    rewrite: Annotated[bool | None, typer.Option("--rewrite/--no-rewrite")] = None,
    multi: Annotated[bool | None, typer.Option("--multi/--no-multi")] = None,
) -> None:
    """Benchmark de retrieval: recall@k, MRR, nDCG y hit@k por categoría (eval/benchmark.jsonl)."""
    from pathlib import Path

    from legal_ai.db.engine import make_engine
    from legal_ai.eval.benchmark import run_benchmark, write_report
    from legal_ai.index.embeddings import get_embedder
    from legal_ai.ingest.layout import ProcessedLayout
    from legal_ai.ingest.manifest import read_resolved
    from legal_ai.retrieval.retriever import Retriever, parse_mode
    from legal_ai.retrieval.rewrite import ClaudeRewriter
    from legal_ai.settings import Settings

    settings = Settings()
    embedder = get_embedder(model or settings.embedding_model)
    searcher = Retriever(
        make_engine(settings.database_url),
        embedder,
        mode=parse_mode(retriever) if retriever else settings.retrieval_mode,
        dedupe=dedupe,
        reranker=_reranker(settings, rerank),
        pool=pool or settings.rerank_pool,
        rewriter=_rewriter(settings, rewrite),
        multi_query=settings.rewrite_multi_query if multi is None else multi,
    )
    searcher.require_index()
    resolved = read_resolved(ProcessedLayout(settings.data_dir).resolved_path("laboral"))
    report = run_benchmark(
        searcher, Path(questions), k, name, embedder.name, resolved.catalog_date.isoformat()
    )
    path = write_report(report, Path("experiments"))

    def fmt(v: float | None) -> str:
        return "  -  " if v is None else f"{v:5.2f}"

    typer.echo(f"{'categoría':<16}{'n':>3} {'hit@k':>6} {'recall':>7} {'mrr':>6} {'ndcg':>6}")
    rows = [("overall", report.overall)] + list(report.by_category.items())
    for label, agg in rows:
        typer.echo(
            f"{label:<16}{agg.n_scored:>3} {fmt(agg.hit_at_k):>6} {fmt(agg.recall_at_k):>7} "
            f"{fmt(agg.mrr):>6} {fmt(agg.ndcg_at_k):>6}"
        )
    typer.echo(
        f"retrieval p50/p95 {report.overall.p50_retrieval_ms:.0f}/"
        f"{report.overall.p95_retrieval_ms:.0f} ms · k={k} · {searcher.name}"
    )
    rw = searcher.rewriter
    if isinstance(rw, ClaudeRewriter):
        cost = (rw.input_tokens * 5 + rw.output_tokens * 25) / 1e6
        typer.echo(
            f"reescrituras: {rw.calls} llamadas, tokens in/out "
            f"{rw.input_tokens}/{rw.output_tokens}, costo lista ${cost:.4f}"
        )
    for r in report.results:
        if r.scored and not r.hit_at_k:
            typer.echo(
                f"✗ {r.id} {r.category:<15} {r.question[:60]}  esperado {r.expected_articles}"
            )
    typer.echo(f"escrito: {path}")


def _reranker(settings: "Settings", flag: bool | None) -> "Reranker | None":
    from legal_ai.retrieval.rerank import BgeReranker, get_reranker

    if flag is False or (flag is None and not settings.reranker_model):
        return None
    return get_reranker(settings.reranker_model or BgeReranker.name)


def _rewriter(settings: "Settings", flag: bool | None) -> "Rewriter | None":
    from legal_ai.generation.claude import make_client
    from legal_ai.retrieval.rewrite import ClaudeRewriter

    if flag is False or (flag is None and not settings.rewrite_model):
        return None
    if not settings.anthropic_api_key:
        raise typer.BadParameter("--rewrite necesita ANTHROPIC_API_KEY en .env")
    model = settings.rewrite_model or settings.llm_model
    cache = settings.data_dir / "cache" / "rewrites" / f"{model}.json"
    return ClaudeRewriter(make_client(settings.anthropic_api_key), model, cache)


@app.callback()
def main() -> None:
    pass
