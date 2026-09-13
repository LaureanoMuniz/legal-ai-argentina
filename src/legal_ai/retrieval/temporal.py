"""Temporal filter shared by every retriever: which versions are visible for a question."""

from datetime import date

CURRENT_ONLY = "v.status = 'vigente' AND v.effective_until IS NULL"
AS_OF = "v.effective_from <= :as_of AND (v.effective_until IS NULL OR v.effective_until > :as_of)"
ANY = "TRUE"


def version_filter(as_of: date | None, historical: bool) -> tuple[str, dict[str, object]]:
    if as_of is not None:
        return AS_OF, {"as_of": as_of}
    if historical:
        return ANY, {}
    return CURRENT_ONLY, {}
