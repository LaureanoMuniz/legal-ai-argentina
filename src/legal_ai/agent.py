"""Agent with explicit tools (Pydantic AI): the model decides what to search and what to read."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from legal_ai.generation.schema import GroundedAnswer
from legal_ai.tools import ArticleInfo, ArticleVersion, SearchHit, Toolbox

AGENT_INSTRUCTIONS = """Sos un asistente de investigación sobre legislación laboral argentina.
Tenés herramientas para buscar artículos, leer un artículo con todas sus versiones y obtener
el texto que regía en una fecha. Usalas antes de responder: primero buscá, y si la pregunta
habla de una fecha o de un texto derogado, pedí la versión correspondiente.
Respondé sólo con lo que devuelvan las herramientas. Cada afirmación en `claims` cita los
ids de versión exactos que la sostienen (por ejemplo 25552:245@current). Si las
herramientas no traen evidencia suficiente, marcá `insufficient_evidence: true`.
No inventes números ni plazos. `answer` es un resumen breve (tres o cuatro oraciones); el
detalle va en `claims`. Esto no es asesoramiento jurídico."""


@dataclass
class AgentDeps:
    toolbox: Toolbox
    seen_versions: set[str] = field(default_factory=set)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def build_agent(model: Model | str) -> Agent[AgentDeps, GroundedAnswer]:
    agent: Agent[AgentDeps, GroundedAnswer] = Agent(
        model,
        deps_type=AgentDeps,
        output_type=GroundedAnswer,
        instructions=AGENT_INSTRUCTIONS,
        retries=3,
        model_settings={"max_tokens": 8000},
    )

    @agent.tool
    def search_laws(
        ctx: RunContext[AgentDeps],
        query: str,
        k: int = 6,
        as_of: date | None = None,
        historical: bool = False,
    ) -> list[SearchHit]:
        """Busca artículos por significado; as_of filtra por fecha; historical incluye derogados."""
        hits = ctx.deps.toolbox.search_laws(query, k, as_of=as_of, historical=historical)
        ctx.deps.seen_versions.update(h.version_id for h in hits)
        ctx.deps.tool_calls.append(
            {
                "tool": "search_laws",
                "query": query,
                "k": k,
                "as_of": str(as_of),
                "hits": [h.article_id for h in hits],
            }
        )
        return hits

    @agent.tool
    def get_article(ctx: RunContext[AgentDeps], article_id: str) -> ArticleInfo | None:
        """Lee un artículo completo con sus versiones (original, reconstruidas, vigente)."""
        info = ctx.deps.toolbox.get_article(article_id)
        if info is not None:
            ctx.deps.seen_versions.update(v.version_id for v in info.versions)
        ctx.deps.tool_calls.append(
            {"tool": "get_article", "article_id": article_id, "found": info is not None}
        )
        return info

    @agent.tool
    def get_law_version(
        ctx: RunContext[AgentDeps], article_id: str, as_of: date
    ) -> ArticleVersion | None:
        """Texto del artículo vigente en la fecha dada."""
        version = ctx.deps.toolbox.get_law_version(article_id, as_of)
        if version is not None:
            ctx.deps.seen_versions.add(version.version_id)
        ctx.deps.tool_calls.append(
            {
                "tool": "get_law_version",
                "article_id": article_id,
                "as_of": str(as_of),
                "found": version is not None,
            }
        )
        return version

    return agent


def anthropic_model(name: str, api_key: str) -> AnthropicModel:
    return AnthropicModel(name, provider=AnthropicProvider(api_key=api_key))


@dataclass
class AgentRun:
    answer: GroundedAnswer
    unsupported_sources: list[str]
    tool_calls: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int


def run_agent(agent: Agent[AgentDeps, GroundedAnswer], toolbox: Toolbox, question: str) -> AgentRun:
    deps = AgentDeps(toolbox=toolbox)
    result = agent.run_sync(question, deps=deps)
    answer = result.output
    unsupported = sorted(
        {s for c in answer.claims for s in c.sources if s not in deps.seen_versions}
    )
    usage = result.usage
    return AgentRun(
        answer=answer,
        unsupported_sources=unsupported,
        tool_calls=deps.tool_calls,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
    )
