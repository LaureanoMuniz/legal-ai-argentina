"""Cross-encoder reranking over a candidate pool: the query and each chunk are read together."""

from collections.abc import Sequence
from typing import Protocol

from legal_ai.retrieval.types import Candidate


class Reranker(Protocol):
    name: str

    def score(self, query: str, texts: list[str]) -> list[float]: ...


class BgeReranker:
    name = "BAAI/bge-reranker-v2-m3"

    def __init__(self, max_length: int = 1024, batch_size: int = 16) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self.name, max_length=max_length)
        self._batch_size = batch_size

    def score(self, query: str, texts: list[str]) -> list[float]:
        if not texts:
            return []
        scores = self._model.predict(
            [(query, text) for text in texts], batch_size=self._batch_size, show_progress_bar=False
        )
        return [float(s) for s in scores]


class OverlapReranker:
    name = "overlap"

    def score(self, query: str, texts: list[str]) -> list[float]:
        words = {w for w in query.lower().split() if len(w) > 3}
        return [sum(1 for w in words if w in text.lower()) / (len(words) or 1) for text in texts]


def get_reranker(name: str) -> Reranker:
    if name == BgeReranker.name:
        return BgeReranker()
    if name == OverlapReranker.name:
        return OverlapReranker()
    raise ValueError(f"reranker desconocido: {name}")


def rerank(
    reranker: Reranker, query: str, candidates: Sequence[Candidate], k: int
) -> list[Candidate]:
    if not candidates:
        return []
    scores = reranker.score(query, [f"{c.context_prefix}\n{c.text}" for c in candidates])
    order = sorted(range(len(candidates)), key=lambda i: (-scores[i], candidates[i].rank))
    return [
        candidates[i].model_copy(
            update={
                "score": scores[i],
                "rank": position + 1,
                "retriever": f"{candidates[i].retriever}+rerank",
            }
        )
        for position, i in enumerate(order[:k])
    ]
