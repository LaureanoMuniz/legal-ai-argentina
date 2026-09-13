"""Ranking metrics over article ids: recall@k, precision@k, MRR, nDCG@k, hit@k."""

import math
from collections.abc import Iterable, Sequence


def dedupe_ordered(ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def recall_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    if not expected:
        return 0.0
    top = set(retrieved[:k])
    return sum(1 for e in expected if e in top) / len(expected)


def precision_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    top = retrieved[:k]
    if not top:
        return 0.0
    wanted = set(expected)
    return sum(1 for r in top if r in wanted) / len(top)


def reciprocal_rank(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    wanted = set(expected)
    for index, item in enumerate(retrieved[:k]):
        if item in wanted:
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    if not expected:
        return 0.0
    wanted = set(expected)
    dcg = sum(
        1.0 / math.log2(index + 2) for index, item in enumerate(retrieved[:k]) if item in wanted
    )
    ideal_hits = min(len(expected), k)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return dcg / ideal if ideal else 0.0


def hit_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> bool:
    wanted = set(expected)
    return any(item in wanted for item in retrieved[:k])
