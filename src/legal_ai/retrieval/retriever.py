from sqlalchemy.engine import Engine

from legal_ai.index.embeddings import Embedder
from legal_ai.retrieval.types import Candidate
from legal_ai.retrieval.vector import retrieve_vector


class Retriever:
    def __init__(self, engine: Engine, embedder: Embedder) -> None:
        self.engine = engine
        self.embedder = embedder

    def embed_query(self, query: str) -> list[float]:
        return self.embedder.embed([query])[0].tolist()

    def search(self, query: str, k: int = 8) -> list[Candidate]:
        vector = self.embed_query(query)
        with self.engine.connect() as conn:
            return retrieve_vector(conn, vector, k)
