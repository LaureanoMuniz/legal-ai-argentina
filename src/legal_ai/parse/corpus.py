import shutil
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from legal_ai.ingest.catalog_reader import NormRow
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import ResolvedCorpus, ResolvedNorm
from legal_ai.parse.antecedentes import HistoryEvent, parse_antecedentes
from legal_ai.parse.html_text import decode_html, html_to_lines
from legal_ai.parse.reconstruct import chain_versions, reconstruct
from legal_ai.parse.references import extract_references
from legal_ai.parse.structure import ParsedText, parse_text
from legal_ai.parse.versions import (
    ArticleRecord,
    ArticleVersionRecord,
    VersionSource,
    build_articles,
)
from legal_ai.parse.vinculos import Relation, parse_vinculos

_NOTE_KINDS = {
    "derogado": "repeals",
    "abrogado": "repeals",
    "sustituido": "modifies",
    "incorporado": "modifies",
    "modificado": "modifies",
    "restablecido": "modifies",
    "renumerado": "modifies",
    "observado": "vetoes",
    "vetado": "vetoes",
    "suspendido": "suspends",
}


class DocumentRecord(BaseModel):
    id_norma: int
    tipo_norma: str
    numeros: list[str]
    organismos: list[str]
    clase_norma: str | None
    fecha_sancion: date | None
    fecha_boletin: date | None
    numero_boletin: int | None
    titulo_resumido: str | None
    titulo_sumario: str | None
    texto_resumido: str | None
    url_original: str | None
    url_actualizado: str | None
    reason: str
    depth: int
    has_original_text: bool
    has_current_text: bool
    original_source_document_id: int | None
    front_matter: str
    n_articles_original: int
    n_articles_current: int
    n_history_events: int


class HistoryRecord(HistoryEvent):
    document_id: int


class DocumentReport(BaseModel):
    id_norma: int
    n_articles_original: int
    n_articles_current: int
    n_versions: int
    n_relations: int
    n_history: int
    warnings: list[str] = Field(default_factory=list)


class ParseReport(BaseModel):
    corpus: str
    catalog_date: date
    parsed_at: datetime
    documents: list[DocumentReport]
    totals: dict[str, int]


def _read_text(raw: RawLayout, id_norma: int, filename: str) -> ParsedText | None:
    path = raw.norm_dir(id_norma) / filename
    if not path.exists():
        return None
    return parse_text(html_to_lines(decode_html(path.read_bytes())))


def _read_relations(raw: RawLayout, id_norma: int) -> list[Relation]:
    relations: list[Relation] = []
    pages = (
        ("vinculos_modifica.htm", "modifica"),
        ("vinculos_modificada_por.htm", "modificada_por"),
    )
    for filename, direction in pages:
        path = raw.norm_dir(id_norma) / filename
        if path.exists():
            relations.extend(parse_vinculos(path.read_bytes(), id_norma, direction))
    return relations


def _numero_matches(numero: str, norm: ResolvedNorm) -> bool:
    if "/" in numero:
        number, year = numero.split("/", 1)
        return (
            norm.numero_norma == number
            and norm.fecha_boletin is not None
            and str(norm.fecha_boletin.year).endswith(year)
        )
    return norm.numero_norma == numero


def _note_relations(
    document_id: int, versions: list[ArticleVersionRecord], norms: list[ResolvedNorm]
) -> tuple[list[Relation], int]:
    relations: list[Relation] = []
    unresolved = 0
    for version in versions:
        if (
            version.version_kind != "current"
            or version.modified_by_numero is None
            or version.modification_kind is None
        ):
            continue
        match = next(
            (
                n
                for n in norms
                if n.tipo_norma == version.modified_by_tipo
                and _numero_matches(version.modified_by_numero, n)
            ),
            None,
        )
        if match is None:
            unresolved += 1
            continue
        relations.append(
            Relation(
                source_id=match.id_norma,
                target_id=document_id,
                kind=_NOTE_KINDS.get(version.modification_kind, "modifies"),
                evidence="texact_note",
                tipo=match.tipo_norma,
                numero=match.numero_norma,
                fecha_boletin=match.fecha_boletin,
                descripcion=f"{version.article_id} {version.modification_kind}",
            )
        )
    return relations, unresolved


def _write_jsonl(path: Path, records: Sequence[BaseModel]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(record.model_dump_json() + "\n")


def _document(
    norm: ResolvedNorm,
    rows: list[NormRow],
    original: ParsedText | None,
    current: ParsedText | None,
    source_id: int | None,
    n_orig: int,
    n_cur: int,
    n_hist: int,
) -> DocumentRecord:
    first = rows[0] if rows else None
    text = current or original
    return DocumentRecord(
        id_norma=norm.id_norma,
        tipo_norma=norm.tipo_norma,
        numeros=[r.numero_norma for r in rows] or [norm.numero_norma],
        organismos=[r.organismo_origen for r in rows if r.organismo_origen],
        clase_norma=first.clase_norma if first else None,
        fecha_sancion=first.fecha_sancion if first else None,
        fecha_boletin=norm.fecha_boletin,
        numero_boletin=first.numero_boletin if first else None,
        titulo_resumido=first.titulo_resumido if first else None,
        titulo_sumario=first.titulo_sumario if first else norm.titulo_sumario,
        texto_resumido=first.texto_resumido if first else None,
        url_original=norm.url_original,
        url_actualizado=norm.url_actualizado,
        reason=norm.reason,
        depth=norm.depth,
        has_original_text=original is not None,
        has_current_text=current is not None,
        original_source_document_id=source_id,
        front_matter=text.front_matter if text else "",
        n_articles_original=n_orig,
        n_articles_current=n_cur,
        n_history_events=n_hist,
    )


def _original_source(
    norm: ResolvedNorm, resolved: ResolvedCorpus, raw: RawLayout, by_id: dict[int, ResolvedNorm]
) -> VersionSource | None:
    source_id = resolved.original_sources.get(norm.id_norma)
    if source_id is not None:
        parsed = _read_text(raw, source_id, "norma.htm")
        source_norm = by_id.get(source_id)
        if parsed is None:
            return None
        return VersionSource(
            parsed=parsed,
            document_id=source_id,
            fecha_boletin=source_norm.fecha_boletin if source_norm else None,
            url=source_norm.url_original if source_norm else None,
            use_annex_articles=True,
        )
    own = _read_text(raw, norm.id_norma, "norma.htm")
    if own is None:
        return None
    return VersionSource(
        parsed=own,
        document_id=norm.id_norma,
        fecha_boletin=norm.fecha_boletin,
        url=norm.url_original,
        include_annex=norm.id_norma not in resolved.original_sources.values(),
    )


def parse_corpus(
    resolved: ResolvedCorpus,
    rows: dict[int, list[NormRow]],
    raw: RawLayout,
    processed: ProcessedLayout,
) -> ParseReport:
    out_dir = processed.corpus_dir(resolved.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    for child in out_dir.iterdir():
        if child.name == "resolved.json":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    by_id = {n.id_norma: n for n in resolved.norms}
    documents: list[DocumentRecord] = []
    articles: list[ArticleRecord] = []
    versions: list[ArticleVersionRecord] = []
    relations: dict[tuple[int, int, str, str], Relation] = {}
    history: list[HistoryRecord] = []
    reports: list[DocumentReport] = []
    unresolved_total = 0

    for norm in resolved.norms:
        current = _read_text(raw, norm.id_norma, "texact.htm")
        original_src = _original_source(norm, resolved, raw, by_id)
        current_src = (
            VersionSource(
                parsed=current,
                document_id=norm.id_norma,
                fecha_boletin=norm.fecha_boletin,
                url=norm.url_actualizado,
            )
            if current is not None
            else None
        )
        doc_articles, doc_versions, warnings = build_articles(
            norm.id_norma, original_src, current_src
        )
        for parsed in (original_src.parsed if original_src else None, current):
            if parsed is not None:
                warnings.extend(parsed.warnings)
        events = (
            [
                HistoryRecord(document_id=norm.id_norma, **event.model_dump())
                for event in parse_antecedentes(current.antecedentes_lines)
            ]
            if current is not None
            else []
        )
        doc_relations = _read_relations(raw, norm.id_norma)
        note_relations, unresolved = _note_relations(norm.id_norma, doc_versions, resolved.norms)
        unresolved_total += unresolved
        for relation in doc_relations + note_relations:
            key = (relation.source_id, relation.target_id, relation.kind, relation.evidence)
            relations.setdefault(key, relation)

        n_orig = len(original_src.articles()) if original_src else 0
        n_cur = len(current_src.articles()) if current_src else 0
        source_id = resolved.original_sources.get(norm.id_norma)
        documents.append(
            _document(
                norm,
                rows.get(norm.id_norma, []),
                original_src.parsed if original_src else None,
                current,
                source_id,
                n_orig,
                n_cur,
                len(events),
            )
        )
        articles.extend(doc_articles)
        versions.extend(doc_versions)
        history.extend(events)
        reports.append(
            DocumentReport(
                id_norma=norm.id_norma,
                n_articles_original=n_orig,
                n_articles_current=n_cur,
                n_versions=len(doc_versions),
                n_relations=len(doc_relations) + len(note_relations),
                n_history=len(events),
                warnings=warnings,
            )
        )

    version_dicts = [v.model_dump() for v in versions]
    reconstructed = reconstruct([d.model_dump() for d in documents], version_dicts)
    added = chain_versions(version_dicts, reconstructed, {a.id for a in articles})
    version_dicts.extend(added)
    versions = [ArticleVersionRecord.model_validate(v) for v in version_dicts]
    n_reconstructed = len(added)

    law_by_numero: dict[str, int] = {}
    for d in documents:
        if d.tipo_norma == "Ley":
            for n in d.numeros:
                law_by_numero.setdefault(str(n).replace(".", ""), d.id_norma)
    references = extract_references(version_dicts, {a.id for a in articles}, law_by_numero)

    _write_jsonl(out_dir / "documents.jsonl", documents)
    _write_jsonl(out_dir / "references.jsonl", references)
    _write_jsonl(out_dir / "articles.jsonl", articles)
    _write_jsonl(out_dir / "article_versions.jsonl", versions)
    _write_jsonl(out_dir / "relations.jsonl", list(relations.values()))
    _write_jsonl(out_dir / "history.jsonl", history)
    report = ParseReport(
        corpus=resolved.name,
        catalog_date=resolved.catalog_date,
        parsed_at=datetime.now(UTC),
        documents=reports,
        totals={
            "documents": len(documents),
            "documents_with_text": sum(
                1 for d in documents if d.has_original_text or d.has_current_text
            ),
            "articles": len(articles),
            "versions": len(versions),
            "reconstructed_versions": n_reconstructed,
            "references": len(references),
            "relations": len(relations),
            "history": len(history),
            "warnings": sum(len(r.warnings) for r in reports),
            "unresolved_note_relations": unresolved_total,
        },
    )
    (out_dir / "parse_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report
