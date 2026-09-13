"""Question → vector retrieval → context → Claude → grounded answer, with spans per step."""

import time

from opentelemetry.trace import Tracer, format_trace_id
from pydantic import BaseModel

from legal_ai.db.engine import make_engine
from legal_ai.generation.claude import ClaudeGenerator, Usage, make_client
from legal_ai.generation.prompt import build_context
from legal_ai.generation.schema import GroundedAnswer
from legal_ai.index.embeddings import get_embedder
from legal_ai.observability.tracing import setup_tracing
from legal_ai.retrieval.rerank import get_reranker
from legal_ai.retrieval.retriever import Mode, Retriever
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
    def __init__(
        self, retriever: Retriever, generator: ClaudeGenerator | None, tracer: Tracer
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self._tracer = tracer

    def ask(self, question: str, k: int = 8, generate: bool = True) -> AskResponse:
        total_start = time.perf_counter()
        with self._tracer.start_as_current_span("ask") as root:
            root.set_attribute("legal_ai.question", question)
            root.set_attribute("legal_ai.k", k)
            start = time.perf_counter()
            with self._tracer.start_as_current_span(f"retrieval.{self.retriever.mode}") as span:
                candidates = self.retriever.search(question, k)
                span.set_attribute(
                    "legal_ai.candidates", [f"{c.version_id}:{c.score:.3f}" for c in candidates]
                )
            retrieval_ms = _ms(start)
            start = time.perf_counter()
            with self._tracer.start_as_current_span("context.build") as span:
                context = build_context(candidates)
                span.set_attribute("legal_ai.context_chars", len(context))
            context_ms = _ms(start)

            answer: GroundedAnswer | None = None
            usage: Usage | None = None
            model: str | None = None
            unsupported: list[str] = []
            llm_ms: float | None = None
            if generate and self.generator is not None:
                start = time.perf_counter()
                with self._tracer.start_as_current_span("gen_ai.chat") as span:
                    span.set_attribute("gen_ai.system", "anthropic")
                    span.set_attribute("gen_ai.request.model", self.generator.model)
                    generation = self.generator.generate(question, candidates)
                    span.set_attribute("gen_ai.usage.input_tokens", generation.usage.input_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", generation.usage.output_tokens)
                    span.set_attribute(
                        "gen_ai.response.finish_reasons", [generation.stop_reason or ""]
                    )
                llm_ms = _ms(start)
                answer = generation.answer
                usage = generation.usage
                model = generation.model
                unsupported = generation.unsupported_sources
            claims = answer.claims if answer else []
            sources = sorted({s for c in claims for s in c.sources if s not in unsupported})
            trace_id = format_trace_id(root.get_span_context().trace_id)
        return AskResponse(
            question=question,
            answer=answer,
            sources=sources,
            candidates=candidates,
            unsupported_sources=unsupported,
            usage=usage,
            model=model,
            timing=Timing(
                retrieval_ms=retrieval_ms,
                context_ms=context_ms,
                llm_ms=llm_ms,
                total_ms=_ms(total_start),
            ),
            trace_id=trace_id,
        )


def build_pipeline(
    settings: Settings | None = None,
    embedder_name: str | None = None,
    mode: Mode | None = None,
    dedupe: bool | None = None,
) -> Pipeline:
    settings = settings or Settings()
    tracer = setup_tracing("legal-ai", settings.otlp_endpoint, settings.traces_path)
    retriever = Retriever(
        make_engine(settings.database_url),
        get_embedder(embedder_name or settings.embedding_model),
        mode=mode or settings.retrieval_mode,
        dedupe=settings.retrieval_dedupe if dedupe is None else dedupe,
        alpha=settings.hybrid_alpha,
        reranker=get_reranker(settings.reranker_model) if settings.reranker_model else None,
        pool=settings.rerank_pool,
    )
    generator = (
        ClaudeGenerator(make_client(settings.anthropic_api_key), settings.llm_model)
        if settings.anthropic_api_key
        else None
    )
    return Pipeline(retriever, generator, tracer)
