import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Table, delete, select
from sqlalchemy.engine import Connection, Engine

from legal_ai.db.schema import (
    article_references,
    article_versions,
    articles,
    documents,
    history,
    relations,
)
from legal_ai.ingest.layout import ProcessedLayout

BATCH = 1000


class LoadReport(BaseModel):
    corpus: str
    documents: int
    articles: int
    versions: int
    relations: int
    history: int
    references: int = 0


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _insert(conn: Connection, table: Table, rows: Iterator[dict[str, Any]]) -> int:
    batch: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH:
            conn.execute(table.insert(), batch)
            total += len(batch)
            batch = []
    if batch:
        conn.execute(table.insert(), batch)
        total += len(batch)
    return total


def _with_corpus(path: Path, corpus: str) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        yield {**row, "corpus": corpus}


def _history_rows(path: Path) -> Iterator[dict[str, Any]]:
    for row in _rows(path):
        by = row.pop("by")
        yield {
            **row,
            "by_tipo": by["tipo"],
            "by_numero": by["numero"],
            "by_article": by["article"],
            "bo_date": by["bo_date"],
            "vigencia": by["vigencia"],
        }


def load_corpus(engine: Engine, processed: ProcessedLayout, corpus: str) -> LoadReport:
    folder = processed.corpus_dir(corpus)
    with engine.begin() as conn:
        ids = [
            r[0]
            for r in conn.execute(select(documents.c.id_norma).where(documents.c.corpus == corpus))
        ]
        if ids:
            conn.execute(delete(documents).where(documents.c.id_norma.in_(ids)))
        conn.execute(delete(relations).where(relations.c.corpus == corpus))
        n_docs = _insert(conn, documents, _with_corpus(folder / "documents.jsonl", corpus))
        n_articles = _insert(conn, articles, _rows(folder / "articles.jsonl"))
        n_versions = _insert(conn, article_versions, _rows(folder / "article_versions.jsonl"))
        n_relations = _insert(conn, relations, _with_corpus(folder / "relations.jsonl", corpus))
        n_history = _insert(conn, history, _history_rows(folder / "history.jsonl"))
        refs_path = folder / "references.jsonl"
        n_references = (
            _insert(conn, article_references, _rows(refs_path)) if refs_path.exists() else 0
        )
    return LoadReport(
        corpus=corpus,
        documents=n_docs,
        articles=n_articles,
        versions=n_versions,
        relations=n_relations,
        history=n_history,
        references=n_references,
    )
