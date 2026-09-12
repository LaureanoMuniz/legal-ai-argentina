from pydantic import BaseModel


class Candidate(BaseModel):
    chunk_id: str
    version_id: str
    article_id: str
    document_id: int
    score: float
    rank: int
    retriever: str
    context_prefix: str
    text: str
