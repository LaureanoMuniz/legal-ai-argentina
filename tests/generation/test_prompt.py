from legal_ai.generation.prompt import SYSTEM_PROMPT, build_context, build_user_message
from legal_ai.retrieval.types import Candidate


def cand(i: int, version: str, text: str) -> Candidate:
    return Candidate(
        chunk_id=f"{version}#0",
        version_id=version,
        article_id=version.split("@")[0],
        document_id=25552,
        score=1 - i * 0.1,
        rank=i,
        retriever="vector",
        context_prefix=f"Ley 20744 · Art. {i}",
        text=text,
    )


def test_build_context_labels_blocks_with_version_ids():
    context = build_context(
        [
            cand(1, "25552:245@current", "Texto del 245."),
            cand(2, "25552:92bis@current", "Texto del 92 bis."),
        ]
    )
    assert context.startswith("[25552:245@current] Ley 20744 · Art. 1\nTexto del 245.")
    assert "\n\n[25552:92bis@current] Ley 20744 · Art. 2\nTexto del 92 bis." in context


def test_user_message_and_system_prompt_rules():
    message = build_user_message("¿Cuánto dura el período de prueba?", "[x] ctx")
    assert "¿Cuánto dura el período de prueba?" in message and "[x] ctx" in message
    for rule in (
        "únicamente",
        "insufficient_evidence",
        "asesoramiento",
        "[25552:245@current]",
    ):
        assert rule in SYSTEM_PROMPT
