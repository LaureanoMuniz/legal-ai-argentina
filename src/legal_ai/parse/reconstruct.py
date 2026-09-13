"""Rebuild intermediate article versions from the modifying laws present in the corpus."""

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from pydantic import BaseModel

_INTRO_RE = re.compile(
    r"^(?P<verb>Sustit[úu]y[ea]se|Sustit[úu]y[ea]nse|Incorp[óo]r[ae]se|Incorp[óo]rense|"
    r"Agr[ée]g[au]se|Modif[íi]case|Modif[íi]canse)\s+(?:como\s+)?(?:el|los|la|las)?\s*"
    r"art[íi]culos?\s+(?P<arts>[\d\s,°ºy]+?(?:\s*(?:bis|ter|qu[áa]ter|quinquies))?)\s*"
    r"(?:de|a|en)\s+la\s+(?P<law>.{0,160}?)"
    r"(?:,?\s+(?:por|con)\s+(?:el|los|la|las)\s+siguientes?(?:\s+textos?)?|"
    r",?\s+(?:el|los)\s+siguientes?(?:\s+textos?)?|\s+que\s+quedar[áa]n?\s+redactados?\s+(?:de\s+la\s+siguiente\s+manera|as[íi]|como\s+sigue))?\s*:\s*(?P<quoted>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_LAW_NUM_RE = re.compile(r"(?:ley|Ley|LEY)\s*(?:N[°º]?\s*)?(\d{1,2}\.?\d{3})")
_LCT_RE = re.compile(r"contrato de trabajo|20\.?744", re.IGNORECASE)
_ART_HEADER_RE = re.compile(
    r"^[\"“']?\s*(?:ART[IÍ]CULO|Art[íi]culo|Art\.)\s*(?P<num>\d+)\s*[°º]?\s*(?P<suf>bis|ter|qu[áa]ter)?(?:\s*[.:\-–—])*\s*",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^(?P<h>[A-ZÁÉÍÓÚ][^.]{1,90})\.\s*[—–-]?\s*(?=[A-ZÁÉÍÓÚ¿(\"“])")
_NOTE_RE = re.compile(
    r"\s*\((?:Art[íi]culo|Inciso|Párrafo|Nota Infoleg)[^()]*\)\s*$", re.IGNORECASE
)


_DEROGA_ARTICLES_RE = re.compile(
    r"^Der[óo]g(?:a|an)se\s+(?:el|los)\s+art[íi]culos?\s+"
    r"(?P<arts>\d[\d\s,°ºy]*(?:\s*(?:bis|ter|qu[áa]ter))?)\s+de\s+la\s+(?P<law>[^.;]{0,140})",
    re.IGNORECASE,
)
_DEROGA_LAW_RE = re.compile(
    r"^Der[óo]g(?:a|an)se\s+la\s+[Ll]ey\s*(?:N[°º]?\s*)?(?P<num>\d{1,2}\.?\d{3})",
    re.IGNORECASE,
)


class Derogation(BaseModel):
    target_document_id: int
    article_key: str | None
    effective_from: date
    source_document_id: int
    source_article_id: str
    scope: str


class Reconstructed(BaseModel):
    target_document_id: int
    article_key: str
    kind: str
    text: str
    effective_from: date | None
    source_document_id: int
    source_article_id: str
    source_tipo: str
    source_numero: str


def _split_article_keys(raw: str) -> list[str]:
    parts = re.split(r"\s*(?:,|\sy\s)\s*", raw.strip())
    keys: list[str] = []
    for part in parts:
        m = re.match(r"(\d+)\s*[°º]?\s*(bis|ter|qu[áa]ter|quinquies)?", part.strip(), re.IGNORECASE)
        if m:
            suffix = (m.group(2) or "").lower().replace("á", "a")
            keys.append(f"{m.group(1)}{suffix}")
    return keys


def resolve_target(law: str, by_numero: Mapping[str, int]) -> int | None:
    m = _LAW_NUM_RE.search(law)
    if m:
        return by_numero.get(m.group(1).replace(".", ""))
    if _LCT_RE.search(law):
        return by_numero.get("20744")
    return None


def strip_quoted_header(quoted: str) -> str:
    text = quoted.strip().strip("\"“”'")
    text = _ART_HEADER_RE.sub("", text, count=1)
    text = _NOTE_RE.sub("", text)
    return text.strip().strip("\"“”'").lstrip("—–- ").strip()


def split_quoted_articles(quoted: str) -> list[tuple[str | None, str]]:
    pieces = re.split(r"\n(?=[\"“']?\s*(?:ART[IÍ]CULO|Art[íi]culo)\s*\d)", quoted.strip())
    out: list[tuple[str | None, str]] = []
    for piece in pieces:
        m = _ART_HEADER_RE.match(piece.strip())
        key = None
        if m:
            key = m.group("num") + (m.group("suf") or "").lower().replace("á", "a")
        out.append((key, strip_quoted_header(piece)))
    return out


def reconstruct(
    documents: Iterable[Mapping[str, Any]],
    versions: Iterable[Mapping[str, Any]],
) -> list[Reconstructed]:
    docs = {d["id_norma"]: d for d in documents}
    by_numero: dict[str, int] = {}
    for d in docs.values():
        if d["tipo_norma"] == "Ley":
            for n in d.get("numeros") or []:
                by_numero.setdefault(str(n).replace(".", ""), d["id_norma"])
    out: list[Reconstructed] = []
    for v in versions:
        if v["version_kind"] not in ("original", "current"):
            continue
        text = (v.get("text") or "").strip()
        m = _INTRO_RE.match(text)
        if not m:
            continue
        target = resolve_target(m.group("law"), by_numero)
        if target is None:
            continue
        keys = _split_article_keys(m.group("arts"))
        pieces = split_quoted_articles(m.group("quoted"))
        src = docs[v["document_id"]]
        kind = "incorporado" if m.group("verb").lower().startswith("incorp") else "sustituido"
        effective = src.get("fecha_boletin")
        if isinstance(effective, str):
            effective = date.fromisoformat(effective)
        for key in keys:
            piece = None
            for pk, ptext in pieces:
                if pk == key:
                    piece = ptext
                    break
            if piece is None and len(keys) == 1 and pieces:
                piece = pieces[0][1]
            if piece is None or len(piece) < 20:
                continue
            out.append(
                Reconstructed(
                    target_document_id=target,
                    article_key=key,
                    kind=kind,
                    text=piece,
                    effective_from=effective,
                    source_document_id=src["id_norma"],
                    source_article_id=v["article_id"],
                    source_tipo=src["tipo_norma"],
                    source_numero=str((src.get("numeros") or [""])[0]),
                )
            )
    seen: set[tuple[int, str, int]] = set()
    unique: list[Reconstructed] = []
    for r in out:
        sig = (r.target_document_id, r.article_key, r.source_document_id)
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(r)
    return unique


def find_derogations(
    documents: Iterable[Mapping[str, Any]],
    versions: Iterable[Mapping[str, Any]],
) -> list[Derogation]:
    docs = {d["id_norma"]: d for d in documents}
    by_numero: dict[str, int] = {}
    for d in docs.values():
        if d["tipo_norma"] == "Ley":
            for n in d.get("numeros") or []:
                by_numero.setdefault(str(n).replace(".", ""), d["id_norma"])
    out: list[Derogation] = []
    for v in versions:
        if v["version_kind"] not in ("original", "current"):
            continue
        text = (v.get("text") or "").strip()
        if not text.lower().startswith("der"):
            continue
        src = docs.get(v["document_id"])
        if src is None:
            continue
        effective = src.get("fecha_boletin")
        if isinstance(effective, str):
            effective = date.fromisoformat(effective)
        if effective is None:
            continue
        whole = _DEROGA_LAW_RE.match(text)
        if whole:
            target = by_numero.get(whole.group("num").replace(".", ""))
            if target is not None and target != v["document_id"]:
                out.append(
                    Derogation(
                        target_document_id=target,
                        article_key=None,
                        effective_from=effective,
                        source_document_id=src["id_norma"],
                        source_article_id=v["article_id"],
                        scope="norma",
                    )
                )
            continue
        partial_match = _DEROGA_ARTICLES_RE.match(text)
        if partial_match is None:
            continue
        target = resolve_target(partial_match.group("law"), by_numero)
        if target is None:
            continue
        for key in _split_article_keys(partial_match.group("arts")):
            out.append(
                Derogation(
                    target_document_id=target,
                    article_key=key,
                    effective_from=effective,
                    source_document_id=src["id_norma"],
                    source_article_id=v["article_id"],
                    scope="articulo",
                )
            )
    return out


def apply_derogations(versions: list[dict[str, Any]], derogations: Iterable[Derogation]) -> int:
    by_article: dict[str, list[dict[str, Any]]] = {}
    by_document: dict[int, list[dict[str, Any]]] = {}
    for v in versions:
        by_article.setdefault(v["article_id"], []).append(v)
        by_document.setdefault(v["document_id"], []).append(v)
    changed = 0
    for d in sorted(derogations, key=lambda x: x.effective_from):
        if d.article_key is None:
            group = by_document.get(d.target_document_id, [])
        else:
            group = by_article.get(f"{d.target_document_id}:{d.article_key}", [])
        for v in group:
            if v["version_kind"] == "current" or (
                v["version_kind"] == "original"
                and not any(x["version_kind"] == "current" for x in by_article[v["article_id"]])
            ):
                if v["status"] != "vigente":
                    continue
                if v.get("effective_from") and v["effective_from"] > d.effective_from:
                    continue
                v["status"] = "derogado"
                v["effective_until"] = d.effective_from
                v["modification_kind"] = "derogado"
                changed += 1
    return changed


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chain_versions(
    versions: list[dict[str, Any]], reconstructed: list[Reconstructed], article_ids: set[str]
) -> list[dict[str, Any]]:
    """Insert reconstructed versions between original and current; fix effective ranges."""
    by_article: dict[str, list[dict[str, Any]]] = {}
    for v in versions:
        by_article.setdefault(v["article_id"], []).append(v)
    new_versions: list[dict[str, Any]] = []
    for r in reconstructed:
        article_id = f"{r.target_document_id}:{r.article_key}"
        if article_id not in article_ids or r.effective_from is None:
            continue
        existing = by_article.get(article_id, [])
        current = next((v for v in existing if v["version_kind"] == "current"), None)
        original = next((v for v in existing if v["version_kind"] == "original"), None)
        if current is not None and current.get("effective_from") == r.effective_from:
            continue
        if (
            original is not None
            and original.get("effective_from")
            and r.effective_from <= original["effective_from"]
        ):
            continue
        if any(
            v["version_kind"] == "reconstructed" and v["effective_from"] == r.effective_from
            for v in existing
        ):
            continue
        record = {
            "id": f"{article_id}@{r.effective_from.isoformat()}",
            "article_id": article_id,
            "document_id": r.target_document_id,
            "version_kind": "reconstructed",
            "text": r.text,
            "text_with_notes": r.text,
            "status": "historico",
            "effective_from": r.effective_from,
            "effective_until": None,
            "modification_kind": r.kind,
            "modified_by_tipo": r.source_tipo,
            "modified_by_numero": r.source_numero,
            "modified_by_article": r.source_article_id.split(":", 1)[1],
            "source_document_id": r.source_document_id,
            "source_url": None,
            "text_sha256": text_sha(r.text),
            "unchanged_from_original": None,
            "similarity_to_original": None,
        }
        existing.append(record)
        by_article[article_id] = existing
        new_versions.append(record)
    for group in by_article.values():
        dated = sorted(
            (
                v
                for v in group
                if v.get("effective_from")
                and v["version_kind"] != "current"
                or v["version_kind"] == "current"
            ),
            key=lambda v: (v.get("effective_from") or date.min, v["version_kind"] == "current"),
        )
        historical = [v for v in dated if v["version_kind"] in ("original", "reconstructed")]
        current = next((v for v in group if v["version_kind"] == "current"), None)
        for i, v in enumerate(historical):
            nxt = historical[i + 1] if i + 1 < len(historical) else current
            if (
                nxt is not None
                and nxt.get("effective_from")
                and v.get("effective_from")
                and nxt["effective_from"] > v["effective_from"]
            ):
                v["effective_until"] = nxt["effective_from"]
                if v["version_kind"] == "reconstructed":
                    v["status"] = "historico"
    return new_versions
