from datetime import date

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
    status: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
