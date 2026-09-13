"""Query rewriting: turn a lay question into the vocabulary of the law before searching."""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

REWRITE_SYSTEM = """Sos un asistente de búsqueda sobre legislación laboral argentina.
Recibís una pregunta escrita por una persona común y devolvés una consulta de búsqueda
reformulada con el vocabulario que usan las leyes: nombrá el instituto jurídico y los
términos técnicos (por ejemplo: irrenunciabilidad, justa causa, injuria, abandono de
trabajo, preaviso, presunción, remuneración, licencia, jornada), tal como aparecerían en
el texto de un artículo.
Reglas:
1. No respondas la pregunta ni agregues información: sólo reformulá.
2. Conservá lo que la pregunta ya dice: régimen especial (casas particulares, trabajo
   agrario, teletrabajo), números de ley o de artículo, fechas, negaciones ("no", "sin").
3. Si la pregunta es en negativo ("¿cuándo no corresponde…?"), nombrá las excepciones o
   causales tal como las llama la ley.
4. No inventes números de artículo ni de ley que la pregunta no mencione.
5. `query`: una o dos oraciones en castellano. `terms`: entre 3 y 8 términos jurídicos.
6. `as_of`: si la pregunta refiere a una fecha o año concreto ("en 2020", "antes de 2024",
   "cuando regía la ley X"), la fecha en formato AAAA-MM-DD que mejor la representa (para un
   año, el 30 de junio; para "antes de <fecha>", el día anterior). Si no, null.
7. `historical`: true si la pregunta pide un texto que ya no rige ("¿qué decía…?", "¿qué
   establecía…?", "antes de su derogación", "está derogado"); false si pregunta por el
   derecho vigente."""


class Rewrite(BaseModel):
    query: str = Field(description="Consulta reformulada con vocabulario legal, sin responder.")
    terms: list[str] = Field(description="Términos jurídicos clave, entre 3 y 8.")
    as_of: date | None = Field(default=None, description="Fecha de referencia AAAA-MM-DD o null.")
    historical: bool = Field(default=False, description="true si pide un texto que ya no rige.")

    @property
    def search_text(self) -> str:
        return f"{self.query} {' '.join(self.terms)}".strip()


class Rewriter(Protocol):
    name: str

    def rewrite(self, question: str) -> Rewrite: ...


class ClaudeRewriter:
    def __init__(self, client: Any, model: str, cache_path: Path | None = None) -> None:
        self._client = client
        self.model = model
        self.name = f"rewrite({model})"
        self._cache_path = cache_path
        self._cache: dict[str, dict[str, Any]] = {}
        if cache_path and cache_path.exists():
            self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def _key(self, question: str) -> str:
        return hashlib.sha256(f"{self.model}\n{question}".encode()).hexdigest()

    def rewrite(self, question: str) -> Rewrite:
        key = self._key(question)
        if key in self._cache:
            return Rewrite.model_validate(self._cache[key])
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=400,
            system=[
                {"type": "text", "text": REWRITE_SYSTEM, "cache_control": {"type": "ephemeral"}}
            ],
            messages=[{"role": "user", "content": f"PREGUNTA: {question}"}],
            output_format=Rewrite,
        )
        self.calls += 1
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        parsed = response.parsed_output
        rewrite = parsed if parsed is not None else Rewrite(query=question, terms=[])
        self._cache[key] = rewrite.model_dump(mode="json")
        if self._cache_path:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        return rewrite
