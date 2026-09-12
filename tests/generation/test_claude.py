from types import SimpleNamespace

from legal_ai.generation.claude import ClaudeGenerator
from legal_ai.generation.schema import Claim, GroundedAnswer
from legal_ai.retrieval.types import Candidate


class FakeMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed = parsed
        self.stop_reason = stop_reason
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            parsed_output=self.parsed,
            stop_reason=self.stop_reason,
            model=kwargs["model"],
            usage=SimpleNamespace(
                input_tokens=1200,
                output_tokens=150,
                cache_read_input_tokens=1000,
                cache_creation_input_tokens=0,
            ),
        )


def make_client(parsed, stop_reason="end_turn"):
    messages = FakeMessages(parsed, stop_reason)
    return SimpleNamespace(messages=messages), messages


def candidates():
    return [
        Candidate(
            chunk_id="25552:92bis@current#0",
            version_id="25552:92bis@current",
            article_id="25552:92bis",
            document_id=25552,
            score=0.9,
            rank=1,
            retriever="vector",
            context_prefix="Ley 20744 · Art. 92 bis — Período de prueba",
            text="El contrato se entenderá celebrado a prueba durante los primeros seis (6) meses.",
        ),
    ]


def test_generate_passes_schema_prompt_and_context_and_validates_sources():
    parsed = GroundedAnswer(
        answer="Seis meses.",
        claims=[
            Claim(claim="El período de prueba dura seis meses.", sources=["25552:92bis@current"]),
            Claim(claim="Inventado.", sources=["25552:999@current"]),
        ],
        confidence="high",
        insufficient_evidence=False,
    )
    client, messages = make_client(parsed)
    generation = ClaudeGenerator(client, "claude-opus-5").generate(
        "¿Cuánto dura el período de prueba?", candidates()
    )
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5" and call["output_format"] is GroundedAnswer
    assert call["cache_control"] == {"type": "ephemeral"}
    assert "[25552:92bis@current]" in call["messages"][0]["content"]
    assert generation.answer.answer == "Seis meses."
    assert generation.unsupported_sources == ["25552:999@current"]
    assert (
        generation.usage.input_tokens == 1200 and generation.usage.cache_read_input_tokens == 1000
    )
    assert generation.stop_reason == "end_turn"


def test_refusal_becomes_insufficient_evidence():
    client, _ = make_client(None, stop_reason="refusal")
    generation = ClaudeGenerator(client, "claude-opus-5").generate("pregunta", candidates())
    assert generation.answer.insufficient_evidence is True and generation.answer.claims == []
    assert generation.stop_reason == "refusal"
