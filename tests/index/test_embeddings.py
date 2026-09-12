from pathlib import Path

import numpy as np

from legal_ai.index.embeddings import (
    BgeM3Embedder,
    EmbeddingCache,
    HashingEmbedder,
    embed_with_cache,
    get_embedder,
)


def test_hashing_embedder_is_deterministic_normalized_and_semantic_ish():
    emb = HashingEmbedder()
    a = emb.embed(["período de prueba del contrato de trabajo", "período de prueba del contrato"])
    b = emb.embed(["período de prueba del contrato de trabajo"])
    assert a.shape == (2, 1024) and a.dtype == np.float32
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-5)
    assert np.allclose(a[0], b[0])
    far = emb.embed(["tope indemnizatorio promedio de remuneraciones"])[0]
    assert float(a[0] @ a[1]) > float(a[0] @ far)


def test_cache_roundtrip_and_hits(tmp_path: Path):
    emb = HashingEmbedder()
    cache = EmbeddingCache(tmp_path / "cache.npz")
    texts = ["uno", "dos", "tres"]
    first = embed_with_cache(emb, cache, texts)
    cache.save()
    reloaded = EmbeddingCache(tmp_path / "cache.npz")
    assert reloaded.get(cache.key(emb.name, "dos")) is not None
    second = embed_with_cache(emb, reloaded, texts + ["cuatro"])
    assert np.allclose(first, second[:3]) and second.shape == (4, 1024)
    assert reloaded.hits == 3 and reloaded.misses == 1


def test_get_embedder_names():
    assert get_embedder("hashing").name == "hashing-1024"
    assert BgeM3Embedder.name == "BAAI/bge-m3"
