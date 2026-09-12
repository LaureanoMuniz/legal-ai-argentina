import re
from datetime import date

from pydantic import BaseModel

from legal_ai.parse.html_text import decode_html, html_to_lines

_ROW_RE = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<td\b.*?</td>", re.IGNORECASE | re.DOTALL)
_ID_RE = re.compile(r"verNorma\.do[^\"']*?[?&;]id=(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"^(\d{1,2})-([a-z]{3})-(\d{4})$", re.IGNORECASE)
_MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_KINDS = (
    ("DEROGA", "repeals"),
    ("REGLAMENT", "regulates"),
    ("TEXTO ORDENADO", "consolidates"),
    ("PRORROG", "extends"),
    ("SUSPEN", "suspends"),
    ("VETO", "vetoes"),
    ("OBSERVACION", "vetoes"),
    ("MODIFICA", "modifies"),
    ("SUSTITU", "modifies"),
    ("INCORPORA", "modifies"),
    ("COMPLEMENT", "complements"),
)


class Relation(BaseModel):
    source_id: int
    target_id: int
    kind: str
    evidence: str
    tipo: str | None = None
    numero: str | None = None
    organismo: str | None = None
    fecha_boletin: date | None = None
    tema: str | None = None
    descripcion: str | None = None


def relation_kind(descripcion: str | None) -> str:
    if not descripcion:
        return "related"
    upper = descripcion.upper()
    for needle, kind in _KINDS:
        if needle in upper:
            return kind
    return "related"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    match = _DATE_RE.match(value.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def parse_vinculos(raw: bytes, self_id: int, direction: str) -> list[Relation]:
    doc = decode_html(raw)
    relations: list[Relation] = []
    for row in _ROW_RE.findall(doc):
        id_match = _ID_RE.search(row)
        cells = _CELL_RE.findall(row)
        if id_match is None or len(cells) < 3:
            continue
        other_id = int(id_match.group(1))
        who = html_to_lines(cells[0])
        when = html_to_lines(cells[1])
        what = html_to_lines(cells[2])
        descripcion = what[1] if len(what) > 1 else (what[0] if what else None)
        source, target = (self_id, other_id) if direction == "modifica" else (other_id, self_id)
        relations.append(
            Relation(
                source_id=source,
                target_id=target,
                kind=relation_kind(descripcion),
                evidence="infoleg_vinculos",
                tipo=who[0] if who else None,
                numero=who[1] if len(who) > 1 else None,
                organismo=who[2] if len(who) > 2 else None,
                fecha_boletin=_parse_date(when[0] if when else None),
                tema=what[0] if len(what) > 1 else None,
                descripcion=descripcion,
            )
        )
    return relations
