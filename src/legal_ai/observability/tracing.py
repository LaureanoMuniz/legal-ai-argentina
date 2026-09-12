"""OpenTelemetry setup: spans always to a JSONL file, optionally to an OTLP endpoint."""

import json
from collections.abc import Sequence
from pathlib import Path

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Tracer

_provider: TracerProvider | None = None


class JsonlSpanExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self.path.open("a", encoding="utf-8") as fh:
            for span in spans:
                context = span.get_span_context()
                if context is None:
                    continue
                parent = span.parent.span_id if span.parent else None
                start = span.start_time or 0
                end = span.end_time or start
                record = {
                    "name": span.name,
                    "trace_id": format(context.trace_id, "032x"),
                    "span_id": format(context.span_id, "016x"),
                    "parent_id": format(parent, "016x") if parent else None,
                    "start_ns": start,
                    "end_ns": end,
                    "duration_ms": (end - start) / 1e6,
                    "attributes": dict(span.attributes or {}),
                    "status": span.status.status_code.name,
                }
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def setup_tracing(service_name: str, otlp_endpoint: str | None, traces_path: Path) -> Tracer:
    global _provider
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(traces_path)))
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    _provider = provider
    return provider.get_tracer(service_name)


def flush() -> None:
    if _provider is not None:
        _provider.force_flush()
