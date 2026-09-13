"""HTTP API: ask, ask/stream (etapas en vivo), trace, feedback, questions, article and the UI."""

import json
import queue
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import insert, text

from legal_ai.db.schema import feedback
from legal_ai.pipeline import AskResponse, Pipeline, build_pipeline
from legal_ai.settings import Settings
from legal_ai.tools import ArticleInfo, Toolbox

STATIC = Path(__file__).parent / "static"
Label = Literal[
    "correct",
    "partially_correct",
    "incorrect",
    "unsupported",
    "wrong_source",
    "wrong_version",
    "incomplete",
]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    k: int = Field(default=8, ge=1, le=50)
    as_of: date | None = None
    historical: bool | None = None


class FeedbackRequest(BaseModel):
    trace_id: str = Field(min_length=8, max_length=32)
    question: str
    answer: str | None = None
    label: Label
    comment: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=64)
    sources: list[str] = Field(default_factory=list)


def load_catalog(path: Path = Path("eval/questions_catalog.json")) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def read_trace(traces_path: Path, trace_id: str) -> list[dict[str, object]]:
    if not traces_path.exists():
        return []
    spans = []
    with traces_path.open(encoding="utf-8") as fh:
        for line in fh:
            if trace_id in line:
                span = json.loads(line)
                if span.get("trace_id") == trace_id:
                    spans.append(span)
    return sorted(spans, key=lambda s: s.get("start_ns", 0))


def create_app(pipeline_factory: Callable[[], Pipeline] = build_pipeline) -> FastAPI:
    app = FastAPI(title="Legal AI Argentina", version="0.2.0")
    get_pipeline = lru_cache(maxsize=1)(pipeline_factory)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/health")
    def health() -> dict[str, object]:
        pipeline = get_pipeline()
        with pipeline.retriever.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "db": True,
            "generation": pipeline.generator is not None,
            "retriever": pipeline.retriever.name,
        }

    @app.get("/questions")
    def questions() -> list[dict[str, object]]:
        return load_catalog()

    @app.post("/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        return get_pipeline().ask(
            request.question, request.k, as_of=request.as_of, historical=request.historical
        )

    @app.post("/ask/stream")
    def ask_stream(request: AskRequest) -> StreamingResponse:
        pipeline = get_pipeline()
        events: queue.Queue[tuple[str, object] | None] = queue.Queue()

        def on_stage(stage: str, payload: dict[str, object]) -> None:
            events.put((stage, payload))

        def work() -> None:
            try:
                response = pipeline.ask(
                    request.question,
                    request.k,
                    as_of=request.as_of,
                    historical=request.historical,
                    on_stage=on_stage,
                )
                events.put(("done", response.model_dump(mode="json")))
            except Exception as exc:  # noqa: BLE001
                events.put(("error", {"message": str(exc)}))
            finally:
                events.put(None)

        threading.Thread(target=work, daemon=True).start()

        def stream() -> Iterator[str]:
            while True:
                item = events.get()
                if item is None:
                    break
                stage, payload = item
                data = json.dumps(payload, ensure_ascii=False, default=str)
                yield f"event: {stage}\ndata: {data}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/trace/{trace_id}")
    def trace(trace_id: str) -> list[dict[str, object]]:
        return read_trace(Settings().traces_path, trace_id)

    @app.get("/article/{article_id}", response_model=ArticleInfo)
    def article(article_id: str) -> ArticleInfo:
        pipeline = get_pipeline()
        info = Toolbox(pipeline.retriever.engine, pipeline.retriever).get_article(article_id)
        if info is None:
            raise HTTPException(status_code=404, detail="artículo no encontrado")
        return info

    @app.post("/feedback")
    def post_feedback(request: FeedbackRequest) -> dict[str, object]:
        pipeline = get_pipeline()
        with pipeline.retriever.engine.begin() as conn:
            row = conn.execute(
                insert(feedback)
                .values(
                    created_at=datetime.now(UTC),
                    trace_id=request.trace_id,
                    question=request.question,
                    answer=request.answer,
                    label=request.label,
                    comment=request.comment,
                    reviewer=request.reviewer,
                    sources=request.sources,
                )
                .returning(feedback.c.id)
            ).scalar_one()
        return {"id": row, "label": request.label}

    @app.get("/feedback")
    def list_feedback(limit: int = 100) -> list[dict[str, object]]:
        pipeline = get_pipeline()
        with pipeline.retriever.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, created_at, trace_id, question, label, comment, reviewer, sources "
                    "FROM feedback ORDER BY id DESC LIMIT :limit"
                ),
                {"limit": limit},
            ).mappings()
            return [dict(r) for r in rows]

    return app


app = create_app()
