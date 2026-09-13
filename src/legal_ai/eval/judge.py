"""LLM judge: does each cited fragment actually support the claim that cites it?"""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from legal_ai.generation.schema import GroundedAnswer
from legal_ai.retrieval.types import Candidate

JUDGE_SYSTEM = """Sos un evaluador de respuestas jurídicas. Recibís una PREGUNTA, una lista de
AFIRMACIONES numeradas, cada una con los FRAGMENTOS de ley que la respuesta citó como
sostén, y devolvés un veredicto por afirmación:
- "supported": el contenido de la afirmación se lee directamente en los fragmentos citados.
- "partial": los fragmentos sostienen una parte; otra parte no está en ellos o los contradice.
- "unsupported": los fragmentos citados no sostienen la afirmación (o no hay fragmentos).
Juzgá sólo con los fragmentos, no con lo que sepas del derecho. Sé estricto con números,
plazos y montos: si la afirmación dice un número que no aparece textual, no es "supported".
Además marcá `answers_question`: true si el conjunto de afirmaciones responde lo que se
preguntó (aunque sea parcialmente), false si responde otra cosa o no responde."""


class ClaimVerdict(BaseModel):
    index: int = Field(description="Número de la afirmación, empezando en 1.")
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str = Field(description="Una oración: qué sostiene o qué falta.")


class Judgement(BaseModel):
    verdicts: list[ClaimVerdict]
    answers_question: bool


def build_judge_message(question: str, answer: GroundedAnswer, candidates: list[Candidate]) -> str:
    by_version = {c.version_id: c for c in candidates}
    blocks = [f"PREGUNTA: {question}", ""]
    for i, claim in enumerate(answer.claims, start=1):
        blocks.append(f"AFIRMACIÓN {i}: {claim.claim}")
        if not claim.sources:
            blocks.append("  (sin fragmentos citados)")
        for source in claim.sources:
            c = by_version.get(source)
            if c is None:
                blocks.append(f"  [{source}] (id no presente en el contexto)")
            else:
                blocks.append(f"  [{source}] {c.context_prefix}\n  {c.text}")
        blocks.append("")
    return "\n".join(blocks)


class ClaudeJudge:
    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.truncated = 0

    def judge(
        self, question: str, answer: GroundedAnswer, candidates: list[Candidate]
    ) -> Judgement:
        if not answer.claims:
            return Judgement(verdicts=[], answers_question=False)
        message = build_judge_message(question, answer, candidates)
        parsed = None
        for max_tokens in (4000, 8000):
            try:
                response = self._client.messages.parse(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": JUDGE_SYSTEM,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": message}],
                    output_format=Judgement,
                )
            except ValidationError:
                self.truncated += 1
                continue
            self.calls += 1
            self.input_tokens += response.usage.input_tokens
            self.output_tokens += response.usage.output_tokens
            parsed = response.parsed_output
            break
        if parsed is None:
            return Judgement(
                verdicts=[
                    ClaimVerdict(index=i + 1, verdict="unsupported", reason="sin veredicto")
                    for i in range(len(answer.claims))
                ],
                answers_question=False,
            )
        return parsed
