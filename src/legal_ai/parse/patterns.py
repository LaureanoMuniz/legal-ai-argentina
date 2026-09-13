import re

from pydantic import BaseModel

_ARTICLE_RE = re.compile(
    r"^(?P<prefix>ARTICULO|ARTÍCULO|Artículo|Articulo|Art\.)\s*"
    r"(?P<num>\d{1,4})\s*[°ºª]?\s*\.?\s*"
    r"(?P<suf>(?i:bis|ter|qu[aá]ter|quinquies))?(?![a-záéíóúA-ZÁÉÍÓÚ])\s*[°ºª]?\s*"
    r"(?P<sep>[.:\-–—](?:\s*[.:\-–—])*)?\s*"
    r"(?P<rest>.*)$"
)
_CROSS_REF_RE = re.compile(r"^(?:de\s|del\s|y\s|,|que\s|a\s\d|al\s)", re.IGNORECASE)
_HEADING_WITH_BODY_RE = re.compile(r"^(?P<h>.{2,120}?)\.\s*[—–-]\s*(?P<b>\S.*)$")
_HEADING_ONLY_RE = re.compile(r"^(?P<h>.{2,160}?)\.?$")
_HEADING_THEN_SENTENCE_RE = re.compile(
    r"^(?P<h>[A-ZÁÉÍÓÚ][^.()]{1,80}?(?:\.\s+[A-ZÁÉÍÓÚ][^.()]{1,80}?){0,3})\.\s+(?P<b>[A-ZÁÉÍÓÚ].*)$"
)
_SENTENCE_START_RE = re.compile(
    r"^(?:El|La|Los|Las|Se|Cuando|Si|En|No|Toda|Todo|Todas|Todos|Queda|Quedan|Es|Son|Ser[áa]n?|"
    r"Este|Esta|Estos|Estas|Dicho|Dicha|Ning[úu]n|Ninguna|Cada|Para|Por|Con|Sin|Durante|Salvo|"
    r"Hasta|Desde|Ante|Corresponde|Deber[áa]n?|Podr[áa]n?|Tendr[áa]n?|Habr[áa]n?|Hay|"
    r"Quien|Quienes|Al|A|Dentro|Vencido|Vencida|Producida|Producido|Transcurrido|Transcurrida|"
    r"Antes|Despu[ée]s|Vigente|Prescriben|Prescribe|Proceder[áa]|Procede|Est[áa]n?|Existiendo|"
    r"Mientras|Aunque|Siempre|S[óo]lo|Solo|Tanto|Tambi[ée]n|Ser[íi]a|Deber[íi]a|Podr[íi]a|"
    r"Regir[áa]n?|Rige|Rigen|Gozar[áa]n?|Percibir[áa]n?|Tiene|Tienen|Debe|Deben|Puede|Pueden|"
    r"Constituye|Constituyen|Configura|Incurre|Incurren)\s"
)
_IMPERATIVE_RE = re.compile(
    r"^(?:Comun[íi]quese|Reg[íi]strese|Publ[íi]quese|D[ée]se|Arch[íi]vese|T[ée]ngase|"
    r"[A-ZÁÉÍÓÚ][a-záéíóúñ]*[áéíóú][a-záéíóúñ]*(?:se|nse)\b)"
)
_HEADING_TAIL_RE = re.compile(r"^(?P<h>[A-ZÁÉÍÓÚ][^.]{1,40})\.\s*[—–-]\s*(?P<b>\S.*)$")
_HIERARCHY_RE = re.compile(
    r"^(?P<kind>LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N)\s+"
    r"(?P<num>[IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)(?![A-Za-záéíóúñ])"
    r"(?:\s*[.:\-–—])?\s*(?P<name>[A-ZÁÉÍÓÚÑ].*?)?\s*\.?$"
)
_INLINE_HIERARCHY_RE = re.compile(
    r"\s+(?=(?:LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N)\s+(?:[IVXLCDM]+|\d+)(?![a-záéíóúñ]))"
)
_ANNEX_RE = re.compile(
    r"^(?i:anexos?)(?:\s+(?P<num>[IVXLC]+|\d+|[A-Z]))?(?![a-záéíóú])\s*(?:[-:–—.].*)?$"
)
_ANTECEDENTES_RE = re.compile(r"^Antecedentes Normativos\.?$")
_CLOSING_RE = re.compile(r"arch[íi]vese|Comun[íi]quese al Poder Ejecutivo", re.IGNORECASE)
_KIND_NORMALIZE = {"TÍTULO": "TITULO", "CAPÍTULO": "CAPITULO", "SECCIÓN": "SECCION"}


class ArticleHeader(BaseModel):
    number: int
    suffix: str | None
    heading: str | None
    body: str
    raw: str
    prefix: str

    @property
    def label(self) -> str:
        return f"{self.number} {self.suffix}" if self.suffix else str(self.number)

    @property
    def key(self) -> str:
        return f"{self.number}{self.suffix}" if self.suffix else str(self.number)


def _split_heading(rest: str) -> tuple[str | None, str]:
    rest = rest.strip()
    if not rest or rest.startswith("("):
        return None, rest
    with_body = _HEADING_WITH_BODY_RE.match(rest)
    if with_body and with_body.group("h")[0].isupper() and not _IMPERATIVE_RE.match(rest):
        heading, body = with_body.group("h").strip(), with_body.group("b").strip()
        while True:
            tail = _HEADING_TAIL_RE.match(body)
            if not tail or len(tail.group("h").split()) > 4 or _IMPERATIVE_RE.match(body):
                break
            heading = f"{heading}. {tail.group('h').strip()}"
            body = tail.group("b").strip()
        return heading, body
    then_sentence = _HEADING_THEN_SENTENCE_RE.match(rest)
    if (
        then_sentence
        and not _IMPERATIVE_RE.match(rest)
        and not _SENTENCE_START_RE.match(rest)
        and _SENTENCE_START_RE.match(then_sentence.group("b"))
        and all(len(part.split()) <= 8 for part in then_sentence.group("h").split(". "))
    ):
        return then_sentence.group("h").strip(), then_sentence.group("b").strip()
    if (
        len(rest) <= 160
        and " — " not in rest
        and not rest.endswith(":")
        and rest[0].isupper()
        and all(len(part.split()) <= 8 for part in rest.split(". "))
        and not _IMPERATIVE_RE.match(rest)
        and not _SENTENCE_START_RE.match(rest)
    ):
        only = _HEADING_ONLY_RE.match(rest)
        if only and "(" not in rest:
            return only.group("h").strip(), ""
    return None, rest


def match_article(line: str) -> ArticleHeader | None:
    match = _ARTICLE_RE.match(line)
    if not match:
        return None
    rest = match.group("rest")
    if match.group("sep") is None and rest and _CROSS_REF_RE.match(rest):
        return None
    if match.group("sep") is None and rest and rest[0].islower():
        return None
    suffix = match.group("suf")
    heading, body = _split_heading(rest)
    return ArticleHeader(
        number=int(match.group("num")),
        suffix=suffix.lower().replace("á", "a") if suffix else None,
        heading=heading,
        body=body,
        raw=line,
        prefix=match.group("prefix"),
    )


class Section(BaseModel):
    kind: str
    number: str
    name: str | None


def split_hierarchy_line(line: str) -> list[str]:
    parts = _INLINE_HIERARCHY_RE.split(line)
    if len(parts) == 1:
        return [line]
    head = parts[0]
    uppercase_title = head == head.upper() and len(head) <= 100
    if match_hierarchy(head) is None and not uppercase_title:
        return [line]
    return parts


def match_hierarchy(line: str) -> Section | None:
    if len(line) > 250:
        return None
    match = _HIERARCHY_RE.match(line)
    if not match:
        return None
    kind = match.group("kind").upper()
    return Section(
        kind=_KIND_NORMALIZE.get(kind, kind),
        number=match.group("num"),
        name=match.group("name").strip(" .") if match.group("name") else None,
    )


def match_annex(line: str) -> str | None:
    if len(line) > 80:
        return None
    match = _ANNEX_RE.match(line)
    if not match:
        return None
    return "ANEXO" + (f" {match.group('num')}" if match.group("num") else "")


def is_antecedentes(line: str) -> bool:
    return bool(_ANTECEDENTES_RE.match(line))


def is_closing(text: str) -> bool:
    return bool(_CLOSING_RE.search(text))
