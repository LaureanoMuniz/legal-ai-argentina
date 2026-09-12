"""HTTP API: /health and /ask over the RAG pipeline."""

from collections.abc import Callable
from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import text

from legal_ai.pipeline import AskResponse, Pipeline, build_pipeline


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    k: int = Field(default=8, ge=1, le=50)


def create_app(pipeline_factory: Callable[[], Pipeline] = build_pipeline) -> FastAPI:
    app = FastAPI(title="Legal AI Argentina", version="0.1.0")
    get_pipeline = lru_cache(maxsize=1)(pipeline_factory)

    @app.get("/health")
    def health() -> dict[str, object]:
        pipeline = get_pipeline()
        with pipeline.retriever.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": True, "generation": pipeline.generator is not None}

    @app.post("/ask", response_model=AskResponse)
    def ask(request: AskRequest) -> AskResponse:
        return get_pipeline().ask(request.question, request.k)

    return app


app = create_app()
