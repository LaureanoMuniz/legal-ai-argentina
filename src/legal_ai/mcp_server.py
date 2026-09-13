"""MCP server exposing the legal corpus tools to any MCP client (Claude Desktop, Claude Code)."""

from datetime import date

from mcp.server.mcpserver import MCPServer

from legal_ai.db.engine import make_engine
from legal_ai.index.embeddings import get_embedder
from legal_ai.retrieval.retriever import Retriever
from legal_ai.settings import Settings
from legal_ai.tools import ArticleInfo, ArticleVersion, RelatedNorm, SearchHit, Toolbox

INSTRUCTIONS = (
    "Herramientas sobre legislación laboral argentina (Infoleg). Las respuestas citan "
    "artículos por id (por ejemplo 25552:245). No es asesoramiento jurídico."
)


def build_server(settings: Settings | None = None) -> MCPServer:
    settings = settings or Settings()
    server = MCPServer("legal-ai-argentina", instructions=INSTRUCTIONS)
    box: Toolbox | None = None

    def toolbox() -> Toolbox:
        nonlocal box
        if box is None:
            retriever = Retriever(
                make_engine(settings.database_url),
                get_embedder(settings.embedding_model),
                mode=settings.retrieval_mode,
            )
            box = Toolbox(retriever.engine, retriever)
        return box

    @server.tool()
    def search_laws(
        query: str, k: int = 8, as_of: date | None = None, historical: bool = False
    ) -> list[SearchHit]:
        """Busca artículos por significado y palabras; as_of filtra por fecha de vigencia."""
        return toolbox().search_laws(query, k, as_of=as_of, historical=historical)

    @server.tool()
    def get_article(article_id: str) -> ArticleInfo | None:
        """Devuelve un artículo con todas sus versiones (original, reconstruidas, vigente)."""
        return toolbox().get_article(article_id)

    @server.tool()
    def get_law_version(article_id: str, as_of: date) -> ArticleVersion | None:
        """Devuelve el texto del artículo que regía en una fecha dada."""
        return toolbox().get_law_version(article_id, as_of)

    @server.tool()
    def find_related_legislation(id_norma: int, limit: int = 20) -> list[RelatedNorm]:
        """Normas que modifican, derogan o complementan a una norma, según Infoleg."""
        return toolbox().find_related_legislation(id_norma, limit)

    return server


def main() -> None:
    build_server().run("stdio")
