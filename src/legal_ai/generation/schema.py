from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    claim: str = Field(description="Una afirmación jurídica concreta, en castellano.")
    sources: list[str] = Field(
        description="Ids de versión del contexto que la sostienen, ej. 25552:245@current."
    )


class GroundedAnswer(BaseModel):
    answer: str = Field(
        description="Respuesta en castellano, breve y precisa, citando los ids entre corchetes."
    )
    claims: list[Claim]
    confidence: Literal["high", "medium", "low"]
    insufficient_evidence: bool = Field(
        description="true si el contexto no alcanza para responder."
    )
