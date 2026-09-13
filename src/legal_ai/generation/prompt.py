from legal_ai.retrieval.types import Candidate

SYSTEM_PROMPT = """Sos un asistente de investigación jurídica sobre legislación laboral argentina.
Respondés únicamente con la evidencia del CONTEXTO que recibís: fragmentos de artículos, cada uno
precedido por un id entre corchetes, por ejemplo [25552:245@current].

Reglas:
1. Cada afirmación jurídica de tu respuesta tiene que estar sostenida por al menos un fragmento del
   contexto. En `claims` listá cada afirmación con los ids exactos que la sostienen.
2. En `answer` citá los ids entre corchetes al final de la oración que sostienen.
3. Si el contexto no alcanza para responder, o la pregunta habla de algo que no está en los
   fragmentos, marcá `insufficient_evidence: true`, explicá qué falta y no completes con
   conocimiento general.
4. No inventes números, plazos ni montos que no aparezcan textualmente en el contexto.
5. Si el fragmento indica una fecha de vigencia, mencionala cuando sea relevante.
6. Esto no es asesoramiento jurídico y no debés presentarlo como tal.
Respondé en castellano rioplatense, sin rodeos."""


def build_context(candidates: list[Candidate]) -> str:
    blocks = [f"[{c.version_id}] {c.context_prefix}\n{c.text}" for c in candidates]
    return "\n\n".join(blocks)


def build_user_message(question: str, context: str) -> str:
    return f"CONTEXTO:\n\n{context}\n\nPREGUNTA: {question}"


def build_history_messages(
    history: list[tuple[str, str]], max_turns: int = 6
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for question, answer in history[-max_turns:]:
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": answer})
    return messages
