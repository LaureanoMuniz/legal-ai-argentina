from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGAL_AI_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    infoleg_user_agent: str = DEFAULT_USER_AGENT
    infoleg_min_interval_seconds: float = 0.5
    infoleg_timeout_seconds: float = 60.0
    database_url: str = "postgresql+psycopg://legal_ai:legal_ai@localhost:5433/legal_ai"
    test_database_url: str = "postgresql+psycopg://legal_ai:legal_ai@localhost:5433/legal_ai_test"
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    llm_model: str = "claude-opus-5"
    retrieval_mode: Literal["vector", "bm25", "rrf", "hybrid"] = "hybrid"
    hybrid_alpha: float = 0.8
    reranker_model: str | None = None
    rerank_pool: int = 30
    rewrite_model: str | None = "claude-sonnet-5"
    rewrite_multi_query: bool = True
    graph_extra: int = 0
    retrieval_dedupe: bool = False
    otlp_endpoint: str | None = None
    traces_path: Path = Path("data/traces/spans.jsonl")


@lru_cache
def get_settings() -> Settings:
    return Settings()
