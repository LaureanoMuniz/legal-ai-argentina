import math

from legal_ai.eval.metrics import (
    dedupe_ordered,
    hit_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_dedupe_keeps_first_occurrence_order():
    assert dedupe_ordered(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_recall_and_precision():
    retrieved = ["x", "a", "y", "b", "z"]
    assert recall_at_k(retrieved, ["a", "b"], 5) == 1.0
    assert recall_at_k(retrieved, ["a", "b"], 3) == 0.5
    assert recall_at_k(retrieved, ["q"], 5) == 0.0
    assert recall_at_k(retrieved, [], 5) == 0.0
    assert precision_at_k(retrieved, ["a", "b"], 4) == 0.5
    assert precision_at_k([], ["a"], 4) == 0.0


def test_reciprocal_rank_and_hit():
    retrieved = ["x", "a", "y"]
    assert reciprocal_rank(retrieved, ["a"], 3) == 0.5
    assert reciprocal_rank(retrieved, ["y"], 2) == 0.0
    assert hit_at_k(retrieved, ["y"], 3) is True
    assert hit_at_k(retrieved, ["y"], 2) is False


def test_ndcg_perfect_and_partial():
    assert ndcg_at_k(["a", "b"], ["a", "b"], 2) == 1.0
    partial = ndcg_at_k(["x", "a"], ["a"], 2)
    assert math.isclose(partial, (1 / math.log2(3)) / 1.0)
    assert ndcg_at_k(["x"], ["a"], 1) == 0.0
    assert ndcg_at_k(["a"], [], 1) == 0.0
