"""Retriever facade: vector, BM25 or hybrid (RRF), optionally deduplicated by article."""

from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.engine import Engine

from legal_ai.index.embeddings import Embedder
from legal_ai.retrieval.bm25 import bm25_index_exists, retrieve_bm25
from legal_ai.retrieval.fusion import convex, dedupe_by_article, rrf
from legal_ai.retrieval.rerank import Reranker, rerank
from legal_ai.retrieval.rewrite import Rewriter
from legal_ai.retrieval.types import Candidate
from legal_ai.retrieval.vector import count_embedded, retrieve_vector


class SearchPlan(BaseModel):
    query: str
    rewritten: str | None
    as_of: date | None
    historical: bool


Mode = Literal["vector", "bm25", "rrf", "hybrid"]
MODES: tuple[Mode, ...] = ("vector", "bm25", "rrf", "hybrid")
POOL_FACTOR = 3
FUSION_POOL = 24
HYBRID_ALPHA = 0.8
RERANK_POOL = 30


def parse_mode(value: str) -> Mode:
    if value == "vector" or value == "bm25" or value == "rrf" or value == "hybrid":
        return value
    raise ValueError(f"retriever desconocido: {value} (vector | bm25 | rrf | hybrid)")


class Retriever:
    def __init__(
        self,
        engine: Engine,
        embedder: Embedder,
        mode: Mode = "vector",
        dedupe: bool = False,
        alpha: float = HYBRID_ALPHA,
        reranker: Reranker | None = None,
        pool: int = RERANK_POOL,
        rewriter: Rewriter | None = None,
        multi_query: bool = True,
    ) -> None:
        self.engine = engine
        self.embedder = embedder
        self.mode: Mode = mode
        self.dedupe = dedupe
        self.alpha = alpha
        self.reranker = reranker
        self.pool = pool
        self.rewriter = rewriter
        self.multi_query = multi_query

    @property
    def name(self) -> str:
        label = self.mode if self.mode == "bm25" else f"{self.mode}({self.embedder.name})"
        if self.mode == "hybrid":
            label = f"hybrid(a={self.alpha:g},{self.embedder.name})"
        if self.dedupe:
            label += "+dedupe"
        if self.reranker is not None:
            label += f"+rerank({self.reranker.name},pool={self.pool})"
        if self.rewriter is not None:
            label += f"+{self.rewriter.name}"
            if self.multi_query:
                label += "+multi"
        return label

    def embed_query(self, query: str) -> list[float]:
        return self.embedder.embed([query])[0].tolist()

    def embedded_chunks(self) -> int:
        with self.engine.connect() as conn:
            return count_embedded(conn, self.embedder.name)

    def require_index(self) -> None:
        if self.mode != "bm25" and self.embedded_chunks() == 0:
            raise RuntimeError(
                f"no hay chunks embebidos con {self.embedder.name}; "
                f"corré `legal-ai index embed <corpus> --model ...` con ese modelo"
            )
        if self.mode != "vector":
            with self.engine.connect() as conn:
                if not bm25_index_exists(conn):
                    raise RuntimeError(
                        "falta el índice BM25 chunks_bm25; corré `legal-ai db upgrade`"
                    )

    def _search(
        self, query: str, k: int, as_of: date | None = None, historical: bool = False
    ) -> list[Candidate]:
        with self.engine.connect() as conn:
            if self.mode == "bm25":
                return retrieve_bm25(conn, query, k, as_of, historical)
            vector = self.embed_query(query)
            if self.mode == "vector":
                return retrieve_vector(conn, vector, k, self.embedder.name, as_of, historical)
            pool = max(k, FUSION_POOL)
            dense = retrieve_vector(conn, vector, pool, self.embedder.name, as_of, historical)
            sparse = retrieve_bm25(conn, query, pool, as_of, historical)
        if self.mode == "rrf":
            return rrf([dense, sparse], k)
        return convex(dense, sparse, k, self.alpha)

    def _ranked(self, query: str, k: int, as_of: date | None, historical: bool) -> list[Candidate]:
        if not self.dedupe:
            return self._search(query, k, as_of, historical)
        return dedupe_by_article(self._search(query, k * POOL_FACTOR, as_of, historical), k)

    def plan(self, query: str, as_of: date | None, historical: bool | None) -> SearchPlan:
        rewrite = self.rewriter.rewrite(query) if self.rewriter else None
        if as_of is None and rewrite is not None and rewrite.as_of:
            as_of = rewrite.as_of
        if historical is None:
            historical = bool(rewrite.historical) if rewrite is not None else False
        return SearchPlan(
            query=query,
            rewritten=rewrite.search_text if rewrite else None,
            as_of=as_of,
            historical=historical,
        )

    def _candidates(self, plan: SearchPlan, k: int) -> list[Candidate]:
        if plan.rewritten is None:
            return self._ranked(plan.query, k, plan.as_of, plan.historical)
        if not self.multi_query:
            return self._ranked(plan.rewritten, k, plan.as_of, plan.historical)
        return rrf(
            [
                self._ranked(plan.rewritten, k, plan.as_of, plan.historical),
                self._ranked(plan.query, k, plan.as_of, plan.historical),
            ],
            k,
        )

    def search(
        self,
        query: str,
        k: int = 8,
        as_of: date | None = None,
        historical: bool | None = None,
        plan: SearchPlan | None = None,
    ) -> list[Candidate]:
        plan = plan or self.plan(query, as_of, historical)
        if self.reranker is None:
            return self._candidates(plan, k)
        return rerank(self.reranker, query, self._candidates(plan, max(k, self.pool)), k)
