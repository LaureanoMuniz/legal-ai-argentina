import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

MAX_CHUNK_CHARS = 2500
SPLIT_QUOTES = True
_INCISO_RE = re.compile(r"^(?:[a-z]\)|\d{1,2}[.)])\s")
_SENTENCE_RE = re.compile(r"(?<=[.;:])\s+")
_QUOTE_INTRO_RE = re.compile(
    r"^(?P<intro>.{0,400}?(?:por (?:el|la|los|las) siguientes?(?: textos?)?|"
    r"el siguiente texto|los siguientes|como sigue)\s*:)\s*(?P<quoted>\S.*)$",
    re.DOTALL,
)


class ChunkRecord(BaseModel):
    id: str
    version_id: str
    article_id: str
    document_id: int
    chunk_index: int
    context_prefix: str
    text: str
    embed_text: str
    token_estimate: int


def _title(value: str | None) -> str | None:
    return value.title() if value else None


def context_prefix(
    doc: Mapping[str, Any], article: Mapping[str, Any], version: Mapping[str, Any]
) -> str:
    numero = doc["numeros"][0] if doc.get("numeros") else ""
    head = f"{doc['tipo_norma']} {numero}".strip()
    title = _title(doc.get("titulo_sumario"))
    parts = [f"{head} — {title}" if title else head]
    sections = " › ".join(
        " ".join(p for p in (s.get("kind"), s.get("number"), s.get("name")) if p)
        for s in article.get("sections", [])
    )
    if sections:
        parts.append(sections)
    art = f"Art. {article['label']}"
    if article.get("heading"):
        art += f" — {article['heading']}"
    parts.append(art)
    return " · ".join(parts) + "." + period_note(version)


def _pack(units: list[str], max_chars: int, joiner: str) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for unit in units:
        extra = len(unit) + (len(joiner) if current else 0)
        if current and size + extra > max_chars:
            pieces.append(joiner.join(current))
            current, size = [], 0
            extra = len(unit)
        current.append(unit)
        size += extra
    if current:
        pieces.append(joiner.join(current))
    return pieces


def split_quoted(text: str) -> tuple[str, str] | None:
    match = _QUOTE_INTRO_RE.match(text.strip())
    if match is None:
        return None
    intro, quoted = match.group("intro").strip(), match.group("quoted").strip()
    if len(quoted) < 40:
        return None
    return intro, quoted


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    blocks: list[str] = []
    for line in text.split("\n"):
        if blocks and not _INCISO_RE.match(line):
            blocks[-1] = blocks[-1] + "\n" + line
        else:
            blocks.append(line)
    expanded: list[str] = []
    for block in blocks:
        if len(block) <= max_chars:
            expanded.append(block)
        else:
            expanded.extend(_pack(_SENTENCE_RE.split(block), max_chars, " "))
    return _pack(expanded, max_chars, "\n")


def article_pieces(text: str, split_quotes: bool = SPLIT_QUOTES) -> list[str]:
    parts = split_quoted(text) if split_quotes else None
    if parts is None:
        return split_text(text)
    intro, quoted = parts
    return [intro, *split_text(quoted)]


def original_unchanged(version: Mapping[str, Any]) -> bool:
    return bool(version.get("unchanged_from_original", False))


def indexable_versions(versions: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    by_kind = {v["version_kind"]: v for v in versions if v["version_kind"] != "reconstructed"}
    chosen: list[Mapping[str, Any]] = []
    current = by_kind.get("current")
    original = by_kind.get("original")
    if current is not None and (current.get("text") or "").strip():
        chosen.append(current)
    superseded = (
        current is not None
        and original is not None
        and not original_unchanged(current)
        and original.get("effective_until") is not None
        and original.get("text_sha256") != current.get("text_sha256")
    )
    if original is not None and (original.get("text") or "").strip():
        if current is None or superseded:  # noqa: SIM102
            chosen.append(original)
    chosen.extend(
        v
        for v in versions
        if v["version_kind"] == "reconstructed" and (v.get("text") or "").strip()
    )
    return chosen


def period_note(version: Mapping[str, Any]) -> str:
    start, end, status = (
        version.get("effective_from"),
        version.get("effective_until"),
        version.get("status"),
    )
    if status == "derogado":
        return f" Derogado desde {end or start}." if (end or start) else " Derogado."
    if end:
        return (
            f" Texto histórico: vigente de {start} a {end}."
            if start
            else f" Texto histórico hasta {end}."
        )
    return f" Vigente desde {start}." if start else ""


def choose_version(versions: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    by_kind = {v["version_kind"]: v for v in versions}
    chosen = by_kind.get("current") or by_kind.get("original")
    if (
        chosen is None
        or chosen.get("status") != "vigente"
        or not (chosen.get("text") or "").strip()
    ):
        return None
    return chosen


def build_chunks(
    doc: Mapping[str, Any], article: Mapping[str, Any], versions: Sequence[Mapping[str, Any]]
) -> list[ChunkRecord]:
    if article.get("annex"):
        return []
    records: list[ChunkRecord] = []
    for version in indexable_versions(versions):
        prefix = context_prefix(doc, article, version)
        for index, piece in enumerate(article_pieces(version["text"])):
            embed_text = f"{prefix}\n{piece}"
            records.append(
                ChunkRecord(
                    id=f"{version['id']}#{index}",
                    version_id=version["id"],
                    article_id=article["id"],
                    document_id=doc["id_norma"],
                    chunk_index=index,
                    context_prefix=prefix,
                    text=piece,
                    embed_text=embed_text,
                    token_estimate=max(1, len(embed_text) // 4),
                )
            )
    return records
