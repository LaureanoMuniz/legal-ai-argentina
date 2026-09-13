"""Article-level cross references: 'conforme al artículo 245' becomes an edge between articles."""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel

_REF_RE = re.compile(
    r"\b(?:art[íi]culos?|arts?\.)\s+(?P<list>\d{1,3}\s*[°º]?(?:\s*(?:bis|ter|qu[áa]ter))?"
    r"(?:\s*(?:,|y|e|al|a)\s*\d{1,3}\s*[°º]?(?:\s*(?:bis|ter|qu[áa]ter))?)*)"
    r"(?P<tail>\s*(?:de\s+(?:la\s+)?(?:presente|esta)\s+(?:ley|norma)|"
    r"de\s+la\s+(?:ley|Ley)\s*(?:N[°º]?\s*)?(?P<law>\d{1,2}\.?\d{3})|"
    r"de\s+la\s+Ley\s+de\s+Contrato\s+de\s+Trabajo)?)",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"(\d{1,3})\s*[°º]?\s*(bis|ter|qu[áa]ter)?", re.IGNORECASE)
_LCT_RE = re.compile(r"Ley\s+de\s+Contrato\s+de\s+Trabajo", re.IGNORECASE)


class Reference(BaseModel):
    source_article_id: str
    target_article_id: str
    kind: str = "cites"
    evidence: str


def _keys(listing: str) -> list[str]:
    keys: list[str] = []
    for m in _NUM_RE.finditer(listing):
        suffix = (m.group(2) or "").lower().replace("á", "a")
        keys.append(f"{m.group(1)}{suffix}")
    return keys


def extract_references(
    versions: Iterable[Mapping[str, Any]],
    article_ids: set[str],
    law_by_numero: Mapping[str, int],
) -> list[Reference]:
    out: dict[tuple[str, str], Reference] = {}
    for v in versions:
        if v["version_kind"] not in ("current", "original"):
            continue
        text = v.get("text") or ""
        source = v["article_id"]
        doc = v["document_id"]
        for m in _REF_RE.finditer(text):
            tail = m.group("tail") or ""
            target_doc: int | None = doc
            if m.group("law"):
                target_doc = law_by_numero.get(m.group("law").replace(".", ""))
            elif _LCT_RE.search(tail):
                target_doc = law_by_numero.get("20744")
            if target_doc is None:
                continue
            for key in _keys(m.group("list")):
                target = f"{target_doc}:{key}"
                if target == source or target not in article_ids:
                    continue
                snippet = text[max(0, m.start() - 60) : m.end() + 20].replace("\n", " ")
                out.setdefault(
                    (source, target),
                    Reference(
                        source_article_id=source, target_article_id=target, evidence=snippet.strip()
                    ),
                )
    return list(out.values())
