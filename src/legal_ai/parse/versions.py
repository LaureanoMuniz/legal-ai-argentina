import difflib
import hashlib
import re
from datetime import date

from pydantic import BaseModel

from legal_ai.parse.notes import ModificationNote, strip_notes
from legal_ai.parse.patterns import Section
from legal_ai.parse.structure import ParsedArticle, ParsedText


class ArticleRecord(BaseModel):
    id: str
    document_id: int
    key: str
    label: str
    number: int
    suffix: str | None
    ordinal: int
    heading: str | None
    sections: list[Section]
    annex: str | None


class ArticleVersionRecord(BaseModel):
    id: str
    article_id: str
    document_id: int
    version_kind: str
    text: str
    text_with_notes: str
    status: str
    effective_from: date | None
    effective_until: date | None
    modification_kind: str | None = None
    modified_by_tipo: str | None = None
    modified_by_numero: str | None = None
    modified_by_article: str | None = None
    source_document_id: int
    source_url: str | None
    text_sha256: str
    unchanged_from_original: bool | None = None
    similarity_to_original: float | None = None


class VersionSource(BaseModel):
    parsed: ParsedText
    document_id: int
    fecha_boletin: date | None
    url: str | None
    use_annex_articles: bool = False
    include_annex: bool = True

    def articles(self) -> list[ParsedArticle]:
        if self.use_annex_articles:
            return self.parsed.annex_articles()
        if not self.include_annex:
            return self.parsed.main_articles()
        prefixed = [
            a.model_copy(update={"key": f"{_annex_slug(a.annex)}:{a.key}"})
            for a in self.parsed.annex_articles()
        ]
        return self.parsed.main_articles() + prefixed


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
SIMILARITY_THRESHOLD = 0.9


def similarity(a: str, b: str) -> float:
    left = " ".join(_PUNCT_RE.sub(" ", a).casefold().split())
    right = " ".join(_PUNCT_RE.sub(" ", b).casefold().split())
    if left == right:
        return 1.0
    return difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()


def _annex_slug(label: str | None) -> str:
    return (label or "anexo").lower().replace(" ", "")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _latest_dated_note(article: ParsedArticle) -> ModificationNote | None:
    dated = [n for n in article.notes if n.by.bo_date is not None]
    whole = [n for n in dated if n.affects_whole_article]
    pool = whole or dated
    if not pool:
        return None
    return max(pool, key=lambda n: n.by.bo_date or date.min)


def _record(document_id: int, article: ParsedArticle, annex_reset: bool) -> ArticleRecord:
    return ArticleRecord(
        id=f"{document_id}:{article.key}",
        document_id=document_id,
        key=article.key,
        label=article.label,
        number=article.number,
        suffix=article.suffix,
        ordinal=article.ordinal,
        heading=article.heading,
        sections=article.sections,
        annex=None if annex_reset else article.annex,
    )


def _version(
    document_id: int,
    article: ParsedArticle,
    kind: str,
    source: VersionSource,
    effective_from: date | None,
    effective_until: date | None,
    note: ModificationNote | None,
    unchanged: bool | None,
    sim: float | None = None,
) -> ArticleVersionRecord:
    text = "" if article.status == "derogado" else strip_notes(article.text)
    return ArticleVersionRecord(
        id=f"{document_id}:{article.key}@{kind}",
        article_id=f"{document_id}:{article.key}",
        document_id=document_id,
        version_kind=kind,
        text=text,
        text_with_notes=article.text,
        status=article.status,
        effective_from=effective_from,
        effective_until=effective_until,
        modification_kind=note.kind if note else None,
        modified_by_tipo=note.by.tipo if note else None,
        modified_by_numero=note.by.numero if note else None,
        modified_by_article=note.by.article if note else None,
        source_document_id=source.document_id,
        source_url=source.url,
        text_sha256=_sha(text),
        unchanged_from_original=unchanged,
        similarity_to_original=sim,
    )


def build_articles(
    document_id: int, original: VersionSource | None, current: VersionSource | None
) -> tuple[list[ArticleRecord], list[ArticleVersionRecord], list[str]]:
    warnings: list[str] = []
    originals = {a.key: a for a in original.articles()} if original else {}
    currents = {a.key: a for a in current.articles()} if current else {}
    ordered_keys = list(currents) + [k for k in originals if k not in currents]
    articles: list[ArticleRecord] = []
    versions: list[ArticleVersionRecord] = []

    for key in ordered_keys:
        cur = currents.get(key)
        orig = originals.get(key)
        base = cur or orig
        assert base is not None
        from_annex = cur is None and original is not None and original.use_annex_articles
        articles.append(_record(document_id, base, annex_reset=from_annex))

        cur_from: date | None = None
        changed = True
        if cur is not None and current is not None:
            note = _latest_dated_note(cur)
            sim = similarity(strip_notes(orig.text), strip_notes(cur.text)) if orig else None
            unchanged = (
                orig is not None
                and note is None
                and cur.status == "vigente"
                and sim is not None
                and sim >= SIMILARITY_THRESHOLD
            )
            changed = not unchanged
            if note is not None:
                cur_from = note.by.bo_date
            elif unchanged and original is not None:
                cur_from = original.fecha_boletin
            else:
                cur_from = current.fecha_boletin
                if orig is not None:
                    warnings.append(
                        f"{key}: current text differs from original but has no dated note "
                        f"(similarity {sim:.2f})"
                    )
            versions.append(
                _version(
                    document_id,
                    cur,
                    "current",
                    current,
                    cur_from,
                    None,
                    note,
                    unchanged if orig is not None else None,
                    sim,
                )
            )

        if orig is not None and original is not None:
            until: date | None = None
            if cur is not None:
                until = cur_from if changed else None
            elif current is not None:
                warnings.append(f"{key}: present in original, missing in current")
            versions.append(
                _version(
                    document_id,
                    orig,
                    "original",
                    original,
                    original.fecha_boletin,
                    until,
                    None,
                    None,
                )
            )

    return articles, versions, warnings
