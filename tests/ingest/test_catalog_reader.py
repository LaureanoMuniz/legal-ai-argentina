from datetime import date
from pathlib import Path

from legal_ai.ingest.catalog_reader import (
    InMemoryCatalog,
    NormRow,
    RelationRow,
    iter_norms,
    iter_relations,
)


def test_iter_norms_parses_types_and_nulls(norms_zip: Path):
    rows = list(iter_norms(norms_zip))
    assert len(rows) == 7
    lct = next(r for r in rows if r.id_norma == 25552)
    assert lct.tipo_norma == "Ley"
    assert lct.numero_norma == "20744"
    assert lct.fecha_sancion == date(1974, 9, 5)
    assert lct.fecha_boletin == date(1974, 9, 27)
    assert lct.numero_boletin == 23003
    assert lct.modificada_por == 263
    assert lct.texto_actualizado is not None and lct.texto_actualizado.endswith("/texact.htm")

    bases = next(r for r in rows if r.id_norma == 401266)
    assert bases.texto_actualizado is None
    assert bases.clase_norma is None
    assert bases.pagina_boletin is None

    sn = next(r for r in rows if r.id_norma == 183290)
    assert sn.numero_norma == "S/N"
    assert sn.modificada_por == 0
    assert sn.fecha_sancion is None


def test_iter_relations_parses_ids_and_dates(relations_zip: Path):
    rows = list(iter_relations(relations_zip))
    assert len(rows) == 4
    first = rows[0]
    assert first.id_norma_modificatoria == 401266
    assert first.id_norma_modificada == 25552
    assert first.fecha_boletin == date(1974, 9, 27)
    assert rows[3].fecha_boletin is None


def test_in_memory_catalog_is_re_iterable():
    catalog = InMemoryCatalog(
        norms=[NormRow(id_norma=1, tipo_norma="Ley", numero_norma="1")],
        relations=[
            RelationRow(
                id_norma_modificatoria=2, id_norma_modificada=1, tipo_norma="Ley", nro_norma="1"
            )
        ],
    )
    assert len(list(catalog.norms())) == 1
    assert len(list(catalog.norms())) == 1
    assert len(list(catalog.relations())) == 1
