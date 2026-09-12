import re

from pydantic import BaseModel

from legal_ai.parse.notes import KIND_CANON, ByClause, parse_by_clause

_SPLIT_RE = re.compile(r"(?:^|\s)[-.]\s*(?=Art[íi]culo\s+\d)")
_ITEM_RE = re.compile(
    r"^Art[íi]culo\s+(?P<num>\d{1,4})\s*[°ºª]?\s*(?P<suf>(?i:bis|ter|qu[aá]ter|quinquies))?\b\s*,?\s*"
    r"(?:(?P<kind>sustituid|derogad|incorporad|observad|vetad|restablecid|modificad|renumerad|"
    r"suspendid|abrogad)[oa]s?\s+por\s+(?P<by>.*))?.*$",
    re.DOTALL,
)


class HistoryEvent(BaseModel):
    article_key: str | None
    article_label: str | None
    kind: str
    by: ByClause
    raw: str


def parse_antecedentes(lines: list[str]) -> list[HistoryEvent]:
    joined = " ".join(" ".join(lines).split())
    if not joined:
        return []
    items = [part.strip().rstrip(";").strip() for part in _SPLIT_RE.split(" " + joined)]
    events: list[HistoryEvent] = []
    for item in items:
        if not item:
            continue
        match = _ITEM_RE.match(item)
        if not match:
            events.append(
                HistoryEvent(
                    article_key=None, article_label=None, kind="nota", by=ByClause(), raw=item
                )
            )
            continue
        suffix = match.group("suf").lower().replace("á", "a") if match.group("suf") else None
        number = match.group("num")
        key = f"{number}{suffix}" if suffix else number
        label = f"{number} {suffix}" if suffix else number
        if match.group("kind"):
            by = parse_by_clause(match.group("by").rstrip(". "))
            kind = KIND_CANON[match.group("kind").lower()]
        else:
            by, kind = ByClause(), "nota"
        events.append(
            HistoryEvent(article_key=key, article_label=label, kind=kind, by=by, raw=item)
        )
    return events
