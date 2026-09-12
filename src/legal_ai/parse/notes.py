import re
from datetime import date

from pydantic import BaseModel

_NOTE_RE = re.compile(
    r"\(\s*(?P<scope>Art[íi]culo|Art\.|Cap[íi]tulo\s+\S+|T[íi]tulo\s+\S+|Secci[óo]n\s+\S+|"
    r"Incisos?\s+[^\s,]+(?:\)|\b)|[ÚU]ltimo\s+p[áa]rrafo|"
    r"Pen[úu]ltimo\s+p[áa]rrafo|Primer\s+p[áa]rrafo|Segundo\s+p[áa]rrafo|Tercer\s+p[áa]rrafo|"
    r"Cuarto\s+p[áa]rrafo|"
    r"P[áa]rrafos?(?:\s+(?:\d+[°º]?|[a-z]\)|primero|segundo|tercero|cuarto|quinto|final|[úu]ltimo))?|"
    r"Puntos?\s+\S+|Apartados?\s+\S+|"
    r"Expresi[óo]n\s+\"[^\"]+\")\s*"
    r"(?P<kind>sustituid|derogad|incorporad|observad|vetad|restablecid|modificad|renumerad|"
    r"suspendid|abrogad)[oa]s?\s+"
    r"por\s+(?P<by>(?:[^()]|\([^()]*\))*?)\s*\)",
    re.IGNORECASE,
)
_EXTRA_EVENT_RE = re.compile(
    r"\.\s+(?=(?P<kind>Sustituid|Derogad|Incorporad|Observad|Vetad|Restablecid|Modificad|"
    r"Renumerad|Suspendid|Abrogad)[oa]s?\s+por\s)",
    re.IGNORECASE,
)
_EVENT_HEAD_RE = re.compile(
    r"^(?P<kind>sustituid|derogad|incorporad|observad|vetad|restablecid|modificad|renumerad|"
    r"suspendid|abrogad)[oa]s?\s+por\s+(?P<by>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_BY_RE = re.compile(
    r"^(?:art(?:[íi]culo|\.)?\s*(?P<art>\d{1,4})\s*[°ºª]?\s*(?P<artsuf>(?i:bis|ter))?\s+"
    r"(?:de\s+la|de\s+el|del|de)\s+)?"
    r"(?P<tipo>Ley|Decreto(?:\s+Nacional)?|Resoluci[óo]n(?:\s+Conjunta)?|"
    r"Decisi[óo]n\s+Administrativa|"
    r"Disposici[óo]n)\s*"
    r"(?:N(?:ro|°|º|\.)?\.?\s*)?(?P<num>\d[\d.]*(?:/\d{2,4})?)\s*"
    r"(?:B\.?\s*O\.?\s*(?P<bo>\d{1,2}/\d{1,2}/\d{4}))?\s*\.?\s*"
    r"(?:Vigencia:\s*(?P<vig>[^\"]*?))?\s*(?:\..*|\".*)?$",
    re.IGNORECASE | re.DOTALL,
)
_TIPO_CANON = {
    "ley": "Ley",
    "decreto": "Decreto",
    "decreto nacional": "Decreto",
    "resolucion": "Resolución",
    "resolución": "Resolución",
    "resolucion conjunta": "Resolución Conjunta",
    "resolución conjunta": "Resolución Conjunta",
    "decision administrativa": "Decisión Administrativa",
    "decisión administrativa": "Decisión Administrativa",
    "disposicion": "Disposición",
    "disposición": "Disposición",
}
KIND_CANON = {
    "sustituid": "sustituido",
    "derogad": "derogado",
    "incorporad": "incorporado",
    "observad": "observado",
    "vetad": "vetado",
    "restablecid": "restablecido",
    "modificad": "modificado",
    "renumerad": "renumerado",
    "suspendid": "suspendido",
    "abrogad": "abrogado",
}


class ByClause(BaseModel):
    tipo: str | None = None
    numero: str | None = None
    article: str | None = None
    bo_date: date | None = None
    vigencia: str | None = None


def _parse_bo(value: str | None) -> date | None:
    if not value:
        return None
    day, month, year = (int(part) for part in value.split("/"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_by_clause(text: str) -> ByClause:
    normalized = " ".join(text.split())
    match = _BY_RE.match(normalized)
    if not match:
        return ByClause()
    tipo_key = " ".join(match.group("tipo").lower().split())
    article = match.group("art")
    if article and match.group("artsuf"):
        article = f"{article} {match.group('artsuf').lower()}"
    vigencia = match.group("vig")
    return ByClause(
        tipo=_TIPO_CANON.get(tipo_key, match.group("tipo")),
        numero=match.group("num").replace(".", ""),
        article=article,
        bo_date=_parse_bo(match.group("bo")),
        vigencia=vigencia.strip().rstrip(".") or None if vigencia else None,
    )


class ModificationNote(BaseModel):
    kind: str
    scope: str
    scope_detail: str | None
    by: ByClause
    raw: str

    @property
    def affects_whole_article(self) -> bool:
        return self.scope == "articulo"

    @property
    def affects_container(self) -> bool:
        return self.scope in ("capitulo", "titulo", "seccion")


def _classify_scope(scope: str) -> tuple[str, str | None]:
    lowered = scope.lower()
    if lowered.startswith(("artículo", "articulo", "art.")):
        return "articulo", None
    if lowered.startswith(("capítulo", "capitulo")):
        return "capitulo", scope.split(None, 1)[1].strip()
    if lowered.startswith(("título", "titulo")):
        return "titulo", scope.split(None, 1)[1].strip()
    if lowered.startswith(("sección", "seccion")):
        return "seccion", scope.split(None, 1)[1].strip()
    if lowered.startswith("inciso"):
        return "inciso", scope.split(None, 1)[1].strip() if " " in scope else None
    if "párrafo" in lowered or "parrafo" in lowered:
        detail = lowered.replace("párrafo", "").replace("parrafo", "").strip() or None
        return "parrafo", detail
    if lowered.startswith("punto"):
        return "punto", scope.split(None, 1)[1].strip()
    if lowered.startswith("apartado"):
        return "apartado", scope.split(None, 1)[1].strip()
    if lowered.startswith("expresi"):
        return "expresion", scope.split(None, 1)[1].strip()
    return "otro", scope


def parse_notes(text: str) -> list[ModificationNote]:
    normalized = " ".join(text.split())
    notes: list[ModificationNote] = []
    for match in _NOTE_RE.finditer(normalized):
        scope, detail = _classify_scope(match.group("scope"))
        segments = _EXTRA_EVENT_RE.split(match.group("by"))
        kinds = [match.group("kind")] + [k for k in segments[1::2]]
        bodies = (
            [segments[0]]
            + [
                _EVENT_HEAD_RE.match(seg).group("by")  # type: ignore[union-attr]
                for seg in segments[2::2]
            ]
        )
        for kind, body in zip(kinds, bodies, strict=True):
            notes.append(
                ModificationNote(
                    kind=KIND_CANON[kind.lower()],
                    scope=scope,
                    scope_detail=detail,
                    by=parse_by_clause(body),
                    raw=match.group(0),
                )
            )
    return notes


def strip_notes(text: str) -> str:
    normalized = " ".join(text.split())
    return " ".join(_NOTE_RE.sub(" ", normalized).split())
