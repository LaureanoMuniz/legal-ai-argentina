from sqlalchemy.engine import Engine

from legal_ai.index.embeddings import Embedder
from legal_ai.retrieval.types import Candidate
from legal_ai.retrieval.vector import count_embedded, retrieve_vector


class Retriever:
    def __init__(self, engine: Engine, embedder: Embedder) -> None:
        self.engine = engine
        self.embedder = embedder

    def embed_query(self, query: str) -> list[float]:
        return self.embedder.embed([query])[0].tolist()

    def embedded_chunks(self) -> int:
        with self.engine.connect() as conn:
            return count_embedded(conn, self.embedder.name)

    def require_index(self) -> None:
        if self.embedded_chunks() == 0:
            raise RuntimeError(
                f"no hay chunks embebidos con {self.embedder.name}; "
                f"corré `legal-ai index embed <corpus> --model ...` con ese modelo"
            )

    def search(self, query: str, k: int = 8) -> list[Candidate]:
        vector = self.embed_query(query)
        with self.engine.connect() as conn:
            return retrieve_vector(conn, vector, k, self.embedder.name)
