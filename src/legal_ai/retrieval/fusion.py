"""Fusion of ranked candidate lists: RRF, normalized-score convex combination, article dedupe."""

from collections.abc import Sequence

from legal_ai.retrieval.types import Candidate

RRF_K = 60


def rrf(lists: Sequence[Sequence[Candidate]], k: int, rrf_k: int = RRF_K) -> list[Candidate]:
    scores: dict[str, float] = {}
    first: dict[str, Candidate] = {}
    for ranked in lists:
        for candidate in ranked:
            scores[candidate.chunk_id] = scores.get(candidate.chunk_id, 0.0) + 1.0 / (
                rrf_k + candidate.rank
            )
            first.setdefault(candidate.chunk_id, candidate)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]
    return [
        first[chunk_id].model_copy(update={"score": score, "rank": i + 1, "retriever": "rrf"})
        for i, (chunk_id, score) in enumerate(ordered)
    ]


def dedupe_by_article(candidates: Sequence[Candidate], k: int) -> list[Candidate]:
    seen: set[str] = set()
    kept: list[Candidate] = []
    for candidate in candidates:
        if candidate.article_id in seen:
            continue
        seen.add(candidate.article_id)
        kept.append(candidate.model_copy(update={"rank": len(kept) + 1}))
        if len(kept) == k:
            break
    return kept


def _minmax(candidates: Sequence[Candidate]) -> dict[str, float]:
    if not candidates:
        return {}
    high, low = candidates[0].score, candidates[-1].score
    if high <= low:
        return {c.chunk_id: 1.0 for c in candidates}
    return {c.chunk_id: (c.score - low) / (high - low) for c in candidates}


def convex(
    dense: Sequence[Candidate], sparse: Sequence[Candidate], k: int, alpha: float
) -> list[Candidate]:
    dense_scores, sparse_scores = _minmax(dense), _minmax(sparse)
    first: dict[str, Candidate] = {}
    for candidate in (*dense, *sparse):
        first.setdefault(candidate.chunk_id, candidate)
    fused = {
        chunk_id: alpha * dense_scores.get(chunk_id, 0.0)
        + (1 - alpha) * sparse_scores.get(chunk_id, 0.0)
        for chunk_id in first
    }
    ordered = sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:k]
    return [
        first[chunk_id].model_copy(update={"score": score, "rank": i + 1, "retriever": "hybrid"})
        for i, (chunk_id, score) in enumerate(ordered)
    ]


def quota_merge(
    main: Sequence[Candidate],
    subs: Sequence[Sequence[Candidate]],
    k: int,
    per: int = 2,
    rrf_k: int = RRF_K,
) -> list[Candidate]:
    """Reserve `per` slots for each sub-query, fill the rest with the main ranking."""
    if not subs:
        return list(main[:k])
    reserved = min(per * len(subs), max(0, k - 1))
    out: list[Candidate] = []
    seen: set[str] = set()

    def take(candidate: Candidate) -> None:
        seen.add(candidate.article_id)
        out.append(candidate)

    for candidate in main:
        if len(out) >= k - reserved:
            break
        if candidate.article_id not in seen:
            take(candidate)
    for sub in subs:
        taken = 0
        for candidate in sub:
            if taken >= per or len(out) >= k:
                break
            if candidate.article_id not in seen:
                take(candidate)
                taken += 1
    for candidate in rrf([main, *subs], k * 2, rrf_k):
        if len(out) >= k:
            break
        if candidate.article_id not in seen:
            take(candidate)
    return [c.model_copy(update={"rank": i + 1}) for i, c in enumerate(out[:k])]
