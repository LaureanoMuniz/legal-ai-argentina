import csv
import io
import zipfile
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, model_validator

from legal_ai.ingest.catalog import CatalogSnapshot
from legal_ai.ingest.layout import RawLayout

csv.field_size_limit(1 << 30)


def _drop_empty(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if v != ""}
    return data


class NormRow(BaseModel):
    id_norma: int
    tipo_norma: str
    numero_norma: str
    clase_norma: str | None = None
    organismo_origen: str | None = None
    fecha_sancion: date | None = None
    numero_boletin: int | None = None
    fecha_boletin: date | None = None
    pagina_boletin: int | None = None
    titulo_resumido: str | None = None
    titulo_sumario: str | None = None
    texto_resumido: str | None = None
    observaciones: str | None = None
    texto_original: str | None = None
    texto_actualizado: str | None = None
    modificada_por: int = 0
    modifica_a: int = 0

    @model_validator(mode="before")
    @classmethod
    def _clean(cls, data: Any) -> Any:
        return _drop_empty(data)


class RelationRow(BaseModel):
    id_norma_modificatoria: int
    id_norma_modificada: int
    tipo_norma: str
    nro_norma: str
    fecha_boletin: date | None = None

    @model_validator(mode="before")
    @classmethod
    def _clean(cls, data: Any) -> Any:
        return _drop_empty(data)


def _iter_csv_rows(zip_path: Path) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(zip_path) as zf:
        inner = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(inner) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            yield from csv.DictReader(text)


def iter_norms(zip_path: Path) -> Iterator[NormRow]:
    for row in _iter_csv_rows(zip_path):
        yield NormRow.model_validate(row)


def iter_relations(zip_path: Path) -> Iterator[RelationRow]:
    for row in _iter_csv_rows(zip_path):
        yield RelationRow.model_validate(row)


class Catalog(Protocol):
    def norms(self) -> Iterable[NormRow]: ...

    def relations(self) -> Iterable[RelationRow]: ...


class ZipCatalog:
    def __init__(self, snapshot: CatalogSnapshot, layout: RawLayout) -> None:
        self.snapshot = snapshot
        self.layout = layout

    def norms(self) -> Iterable[NormRow]:
        return iter_norms(self.snapshot.path_for("normas", self.layout))

    def relations(self) -> Iterable[RelationRow]:
        return iter_relations(self.snapshot.path_for("modificatorias", self.layout))


class InMemoryCatalog:
    def __init__(self, norms: list[NormRow], relations: list[RelationRow]) -> None:
        self._norms = norms
        self._relations = relations

    def norms(self) -> Iterable[NormRow]:
        return list(self._norms)

    def relations(self) -> Iterable[RelationRow]:
        return list(self._relations)
