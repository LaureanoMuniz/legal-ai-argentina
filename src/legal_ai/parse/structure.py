import re

from pydantic import BaseModel, Field

from legal_ai.parse.notes import ModificationNote, parse_notes
from legal_ai.parse.patterns import (
    ArticleHeader,
    Section,
    is_antecedentes,
    is_closing,
    match_annex,
    match_article,
    match_hierarchy,
    split_hierarchy_line,
)

_ORDER = ["LIBRO", "TITULO", "CAPITULO", "SECCION"]
_QUOTE_INTRO_RE = re.compile(r":\s*[\"“«'‘]?\s*$")
_SECTION_NOTE_RE = re.compile(r"\s*\([^()]*\)\s*$")
_INDEX_RE = re.compile(r"^[IÍ]NDICE\b")


class ParsedArticle(BaseModel):
    key: str
    label: str
    number: int
    suffix: str | None
    ordinal: int
    heading: str | None
    text: str
    sections: list[Section]
    annex: str | None
    notes: list[ModificationNote] = Field(default_factory=list)
    status: str = "vigente"
    raw_header: str


class Annex(BaseModel):
    label: str
    text: str


class ParsedText(BaseModel):
    front_matter: str
    articles: list[ParsedArticle]
    annexes: list[Annex]
    antecedentes_lines: list[str]
    trailer: str
    warnings: list[str]

    def article(self, key: str) -> ParsedArticle | None:
        return next((a for a in self.articles if a.key == key), None)

    def main_articles(self) -> list[ParsedArticle]:
        return [a for a in self.articles if a.annex is None]

    def annex_articles(self) -> list[ParsedArticle]:
        return [a for a in self.articles if a.annex is not None]


def _status(notes: list[ModificationNote]) -> str:
    whole = [n for n in notes if n.affects_whole_article]
    if any(n.kind in ("derogado", "abrogado") for n in whole):
        return "derogado"
    if any(n.kind in ("observado", "vetado") for n in whole):
        return "observado"
    return "vigente"


class _Builder:
    def __init__(self) -> None:
        self.front: list[str] = []
        self.articles: list[ParsedArticle] = []
        self.annexes: list[Annex] = []
        self.antecedentes: list[str] = []
        self.trailer: list[str] = []
        self.warnings: list[str] = []
        self.sections: dict[str, Section] = {}
        self.pending_section: Section | None = None
        self.annex: str | None = None
        self.annex_lines: list[str] = []
        self.header: ArticleHeader | None = None
        self.body: list[str] = []
        self.prev_number: int | None = None
        self.quoting = False
        self.styles: set[str] = set()
        self.closed = False
        self.in_antecedentes = False
        self.seen_keys: set[str] = set()

    def flush_article(self) -> None:
        if self.header is None:
            return
        text = "\n".join(self.body).strip()
        notes = parse_notes(text)
        key = self.header.key
        if key in self.seen_keys:
            self.warnings.append(f"duplicate article {key}")
            key = f"{key}#2"
        self.seen_keys.add(key)
        self.articles.append(
            ParsedArticle(
                key=key,
                label=self.header.label,
                number=self.header.number,
                suffix=self.header.suffix,
                ordinal=len(self.articles) + 1,
                heading=self.header.heading,
                text=text,
                sections=[self.sections[k] for k in _ORDER if k in self.sections],
                annex=self.annex,
                notes=notes,
                status=_status(notes),
                raw_header=self.header.raw,
            )
        )
        self.header = None
        self.body = []

    def flush_annex(self) -> None:
        if self.annex is not None:
            self.annexes.append(Annex(label=self.annex, text="\n".join(self.annex_lines).strip()))
        self.annex_lines = []

    def set_section(self, section: Section) -> None:
        for kind in _ORDER[_ORDER.index(section.kind) :]:
            self.sections.pop(kind, None)
        self.sections[section.kind] = section

    def _recent_colon(self) -> bool:
        return any(_QUOTE_INTRO_RE.search(line) for line in self.body)

    def _expected(self, header: ArticleHeader) -> bool:
        if self.prev_number is None:
            return True
        return header.number == self.prev_number + 1 or (
            header.number == self.prev_number and header.suffix is not None
        )

    def _intro_quotes(self, header: ArticleHeader) -> bool:
        if self.header is None or not self.body:
            return False
        intro = self.body[-1].rstrip()
        if not intro.endswith(":"):
            return False
        suffix = rf"\s*{header.suffix}" if header.suffix else r"(?!\s*(?:bis|ter|qu[aá]ter))"
        return (
            re.search(rf"art[íi]culo\s+{header.number}\s*[°º]?{suffix}\b", intro, re.IGNORECASE)
            is not None
        )

    def accept_article(self, header: ArticleHeader) -> bool:
        if self.prev_number is None:
            return True
        if self._intro_quotes(header):
            self.quoting = True
            return False
        expected = self._expected(header)
        if self.quoting:
            if expected and (not self.styles or header.prefix in self.styles):
                self.quoting = False
                return True
            return False
        foreign_style = bool(self.styles) and header.prefix not in self.styles
        if self.header is not None and not expected and (self._recent_colon() or foreign_style):
            self.quoting = True
            return False
        if header.number < self.prev_number and header.suffix is None:
            return False
        if header.number == self.prev_number and header.suffix is None:
            return True
        if header.number > self.prev_number + 1:
            self.warnings.append(f"numbering gap {self.prev_number} → {header.number}")
        return True

    def feed(self, line: str) -> None:
        if self.in_antecedentes:
            self.antecedentes.append(line)
            return
        if is_antecedentes(line):
            self.flush_article()
            self.in_antecedentes = True
            return
        if _INDEX_RE.match(line):
            self.flush_article()
            self.closed = True
            self.trailer.append(line)
            return
        annex_label = match_annex(line)
        if annex_label is not None:
            self.flush_article()
            self.flush_annex()
            self.annex = annex_label
            self.sections = {}
            self.prev_number = None
            self.quoting = False
            self.styles = set()
            self.seen_keys = set()
            self.closed = False
            return
        section = match_hierarchy(line)
        if (
            section is not None
            and self.header is not None
            and (self.quoting or self._recent_colon())
        ):
            self.quoting = True
            self.body.append(line)
            return
        if section is not None:
            self.flush_article()
            self.set_section(section)
            self.pending_section = section if section.name is None else None
            self.closed = False
            return
        header = match_article(line)
        if header is not None and self.closed and not self.quoting and not self._expected(header):
            self.trailer.append(line)
            return
        if header is not None and self.accept_article(header):
            self.flush_article()
            self.pending_section = None
            self.header = header
            self.body = [header.body] if header.body else []
            self.prev_number = header.number
            self.styles.add(header.prefix)
            self.closed = is_closing(header.body)
            return
        if header is not None and not self.quoting:
            self.warnings.append(f"cross-reference-like header ignored: {line}")
        if self.pending_section is not None and len(line) <= 250:
            self.pending_section.name = _SECTION_NOTE_RE.sub("", line).strip(" .")
            self.pending_section = None
            return
        if self.header is not None and not self.closed:
            self.body.append(line)
            self.closed = is_closing(line)
        elif self.closed:
            self.trailer.append(line)
        elif self.annex is not None:
            self.annex_lines.append(line)
        else:
            self.front.append(line)

    def build(self) -> ParsedText:
        self.flush_article()
        self.flush_annex()
        return ParsedText(
            front_matter="\n".join(self.front),
            articles=self.articles,
            annexes=self.annexes,
            antecedentes_lines=self.antecedentes,
            trailer="\n".join(self.trailer),
            warnings=self.warnings,
        )


def _propagate_container_notes(articles: list[ParsedArticle]) -> list[str]:
    warnings: list[str] = []
    for source in articles:
        for note in list(source.notes):
            if not (note.affects_container and note.kind in ("derogado", "abrogado")):
                continue
            kind = note.scope.upper()
            container = next((s for s in source.sections if s.kind == kind), None)
            detail = (note.scope_detail or "").upper().rstrip(".")
            if container is None or container.number.upper() != detail:
                warnings.append(
                    f"{note.scope} {detail} derogation noted at article {source.label}, "
                    f"which is not inside it"
                )
                continue
            path = [(s.kind, s.number) for s in source.sections]
            for sibling in articles:
                if sibling.annex != source.annex:
                    continue
                if [(s.kind, s.number) for s in sibling.sections][: len(path)] != path:
                    continue
                if not any(n.raw == note.raw for n in sibling.notes):
                    sibling.notes.append(note)
                sibling.status = "derogado"
    return warnings


def parse_text(lines: list[str]) -> ParsedText:
    builder = _Builder()
    for line in lines:
        for part in split_hierarchy_line(line):
            builder.feed(part)
    parsed = builder.build()
    parsed.warnings.extend(_propagate_container_notes(parsed.articles))
    return parsed
