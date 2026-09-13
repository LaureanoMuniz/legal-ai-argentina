from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from legal_ai.generation.prompt import (
    SYSTEM_PROMPT,
    build_context,
    build_history_messages,
    build_user_message,
)
from legal_ai.generation.schema import GroundedAnswer
from legal_ai.retrieval.types import Candidate


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class Generation(BaseModel):
    answer: GroundedAnswer
    usage: Usage
    model: str
    stop_reason: str | None
    unsupported_sources: list[str]


def make_client(api_key: str | None, max_retries: int = 5) -> anthropic.Anthropic:
    if api_key:
        return anthropic.Anthropic(api_key=api_key, max_retries=max_retries)
    return anthropic.Anthropic(max_retries=max_retries)


class ClaudeGenerator:
    def __init__(self, client: Any, model: str, max_tokens: int = 6000) -> None:
        self._client = client
        self.model = model
        self.max_tokens = max_tokens

    def generate(
        self,
        question: str,
        candidates: list[Candidate],
        history: list[tuple[str, str]] | None = None,
    ) -> Generation:
        message = build_user_message(question, build_context(candidates))
        messages = [*build_history_messages(history or []), {"role": "user", "content": message}]
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[
                    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
                ],
                messages=messages,
                output_format=GroundedAnswer,
            )
        except ValidationError:
            empty = GroundedAnswer(
                answer="", claims=[], confidence="low", insufficient_evidence=True
            )
            return Generation(
                answer=empty,
                usage=Usage(input_tokens=0, output_tokens=self.max_tokens),
                model=self.model,
                stop_reason="max_tokens",
                unsupported_sources=[],
            )
        usage = Usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0)
            or 0,
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            answer = GroundedAnswer(
                answer="", claims=[], confidence="low", insufficient_evidence=True
            )
        else:
            answer = response.parsed_output
        known = {c.version_id for c in candidates}
        unsupported = sorted(
            {s for claim in answer.claims for s in claim.sources if s not in known}
        )
        return Generation(
            answer=answer,
            usage=usage,
            model=response.model,
            stop_reason=response.stop_reason,
            unsupported_sources=unsupported,
        )
