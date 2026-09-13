import hashlib
import re
from pathlib import Path
from typing import Protocol

import numpy as np

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _features(self, text: str) -> list[str]:
        tokens = _TOKEN_RE.findall(text.lower())
        return tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature in self._features(text):
                digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
                value = int.from_bytes(digest, "big")
                out[row, value % self.dim] += 1.0 if (value >> 63) else -1.0
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out


class BgeM3Embedder:
    name = "BAAI/bge-m3"
    dim = 1024

    def __init__(self, batch_size: int = 16) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.name)
        self._batch_size = batch_size

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(
            texts, batch_size=self._batch_size, normalize_embeddings=True, convert_to_numpy=True
        )
        return np.asarray(vectors, dtype=np.float32)


class E5Embedder:
    """multilingual-e5-large: asymmetric, needs 'query: ' and 'passage: ' prefixes."""

    name = "intfloat/multilingual-e5-large"
    dim = 1024

    def __init__(self, batch_size: int = 16) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.name)
        self._batch_size = batch_size

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        vectors = self._model.encode(
            [f"{prefix}{t}" for t in texts],
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return np.asarray(vectors, dtype=np.float32)

    def embed(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "passage: ")

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "query: ")


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.hits = 0
        self.misses = 0
        self._data: dict[str, np.ndarray] = {}
        if path.exists():
            with np.load(path) as stored:
                self._data = {key: stored[key] for key in stored.files}

    @staticmethod
    def key(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()

    def get(self, key: str) -> np.ndarray | None:
        return self._data.get(key)

    def put(self, key: str, vector: np.ndarray) -> None:
        self._data[key] = vector.astype(np.float32)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, allow_pickle=False, **self._data)


def get_embedder(name: str) -> Embedder:
    if name == "hashing":
        return HashingEmbedder()
    if name in ("e5", E5Embedder.name):
        return E5Embedder()
    if name == BgeM3Embedder.name:
        return BgeM3Embedder()
    raise ValueError(f"embedder desconocido: {name}")


def embed_with_cache(embedder: Embedder, cache: EmbeddingCache, texts: list[str]) -> np.ndarray:
    out = np.zeros((len(texts), embedder.dim), dtype=np.float32)
    missing: list[int] = []
    for i, text in enumerate(texts):
        cached = cache.get(cache.key(embedder.name, text))
        if cached is None:
            missing.append(i)
            cache.misses += 1
        else:
            out[i] = cached
            cache.hits += 1
    if missing:
        fresh = embedder.embed([texts[i] for i in missing])
        for row, i in enumerate(missing):
            out[i] = fresh[row]
            cache.put(cache.key(embedder.name, texts[i]), fresh[row])
    return out
