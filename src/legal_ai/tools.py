"""Tools shared by the MCP server and the agent: search, article lookup, versions, relations."""

from datetime import date

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from legal_ai.retrieval.retriever import Retriever

ARTICLE_SQL = """
SELECT a.id, a.document_id, a.label, a.heading, a.sections, d.tipo_norma, d.numeros
FROM articles a JOIN documents d ON d.id_norma = a.document_id
WHERE a.id = :id
"""
VERSIONS_SQL = """
SELECT id, version_kind, status, effective_from, effective_until, text,
       modified_by_tipo, modified_by_numero
FROM article_versions WHERE article_id = :id
ORDER BY effective_from NULLS FIRST, version_kind
"""
RELATED_SQL = """
SELECT r.source_id, r.target_id, r.kind, r.descripcion, d.tipo_norma, d.numeros, d.id_norma
FROM relations r
JOIN documents d ON d.id_norma = CASE WHEN r.source_id = :id THEN r.target_id ELSE r.source_id END
WHERE r.source_id = :id OR r.target_id = :id
ORDER BY r.kind, d.id_norma LIMIT :limit
"""


class ArticleVersion(BaseModel):
    version_id: str
    version_kind: str
    status: str
    effective_from: date | None
    effective_until: date | None
    text: str
    modified_by: str | None


class ArticleInfo(BaseModel):
    article_id: str
    document_id: int
    norm: str
    label: str
    heading: str | None
    sections: list[str]
    versions: list[ArticleVersion]


class SearchHit(BaseModel):
    article_id: str
    version_id: str
    norm: str
    context: str
    text: str
    score: float
    rank: int
    effective_from: date | None
    effective_until: date | None
    status: str | None


class RelatedNorm(BaseModel):
    id_norma: int
    norm: str
    kind: str
    direction: str
    descripcion: str | None


class Toolbox:
    def __init__(self, engine: Engine, retriever: Retriever) -> None:
        self.engine = engine
        self.retriever = retriever

    def search_laws(
        self, query: str, k: int = 8, as_of: date | None = None, historical: bool | None = None
    ) -> list[SearchHit]:
        hits = self.retriever.search(query, k, as_of=as_of, historical=historical)
        return [
            SearchHit(
                article_id=c.article_id,
                version_id=c.version_id,
                norm=c.context_prefix.split(" · ")[0],
                context=c.context_prefix,
                text=c.text,
                score=c.score,
                rank=c.rank,
                effective_from=c.effective_from,
                effective_until=c.effective_until,
                status=c.status,
            )
            for c in hits
        ]

    def get_article(self, article_id: str) -> ArticleInfo | None:
        with self.engine.connect() as conn:
            row = conn.execute(text(ARTICLE_SQL), {"id": article_id}).mappings().first()
            if row is None:
                return None
            versions = conn.execute(text(VERSIONS_SQL), {"id": article_id}).mappings()
            sections = row["sections"] or []
            return ArticleInfo(
                article_id=row["id"],
                document_id=row["document_id"],
                norm=f"{row['tipo_norma']} {(row['numeros'] or [''])[0]}",
                label=row["label"],
                heading=row["heading"],
                sections=[
                    " ".join(p for p in (s.get("kind"), s.get("number"), s.get("name")) if p)
                    for s in sections
                ],
                versions=[
                    ArticleVersion(
                        version_id=v["id"],
                        version_kind=v["version_kind"],
                        status=v["status"],
                        effective_from=v["effective_from"],
                        effective_until=v["effective_until"],
                        text=v["text"],
                        modified_by=(
                            f"{v['modified_by_tipo']} {v['modified_by_numero']}"
                            if v["modified_by_numero"]
                            else None
                        ),
                    )
                    for v in versions
                ],
            )

    def get_law_version(self, article_id: str, as_of: date) -> ArticleVersion | None:
        info = self.get_article(article_id)
        if info is None:
            return None
        for v in info.versions:
            started = v.effective_from is not None and v.effective_from <= as_of
            if started and (v.effective_until is None or v.effective_until > as_of):
                return v
        return None

    def find_related_legislation(self, id_norma: int, limit: int = 20) -> list[RelatedNorm]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(RELATED_SQL), {"id": id_norma, "limit": limit}).mappings()
            return [
                RelatedNorm(
                    id_norma=r["id_norma"],
                    norm=f"{r['tipo_norma']} {(r['numeros'] or [''])[0]}",
                    kind=r["kind"],
                    direction="modifies" if r["source_id"] == id_norma else "modified_by",
                    descripcion=r["descripcion"],
                )
                for r in rows
            ]
