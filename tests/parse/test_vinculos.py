from datetime import date
from pathlib import Path

from legal_ai.parse.vinculos import parse_vinculos, relation_kind

FIXTURE = Path("tests/fixtures/infoleg/25552")

ROW_HTML = """
<table>
<tr><td>Número/Dependencia</td><td>Fecha Publicación</td><td>Descripción</td></tr>
<tr>
<td><a href="/infolegInternet/verNorma.do;jsessionid=ABC?id=229909">Decreto&nbsp;<br>390/1976<br>PODER EJECUTIVO NACIONAL (P.E.N.)</a></td>
<td>21-may-1976</td>
<td>CONTRATO DE TRABAJO<br>LEY N° 20744 - TEXTO ORDENADO</td>
</tr>
<tr><td></td></tr>
<tr>
<td><a href="/infolegInternet/verNorma.do?id=77206">Ley<br>21659<br>PODER EJECUTIVO NACIONAL (P.E.N.)</a></td>
<td>12-oct-1977</td>
<td>CONTRATO DE TRABAJO<br>LEY N° 20744 - MODIFICACION</td>
</tr>
</table>
""".encode("latin-1")


def test_parse_rows_modificada_por():
    relations = parse_vinculos(ROW_HTML, self_id=25552, direction="modificada_por")
    assert len(relations) == 2
    decree = relations[0]
    assert (decree.source_id, decree.target_id) == (229909, 25552)
    assert decree.kind == "consolidates"
    assert (decree.tipo, decree.numero, decree.organismo) == (
        "Decreto",
        "390/1976",
        "PODER EJECUTIVO NACIONAL (P.E.N.)",
    )
    assert decree.fecha_boletin == date(1976, 5, 21)
    assert (decree.tema, decree.descripcion) == (
        "CONTRATO DE TRABAJO",
        "LEY N° 20744 - TEXTO ORDENADO",
    )
    assert decree.evidence == "infoleg_vinculos"
    law = relations[1]
    assert (law.source_id, law.target_id, law.kind) == (77206, 25552, "modifies")
    assert law.fecha_boletin == date(1977, 10, 12)


def test_parse_rows_modifica_flips_direction():
    relations = parse_vinculos(ROW_HTML, self_id=25552, direction="modifica")
    assert (relations[0].source_id, relations[0].target_id) == (25552, 229909)


def test_relation_kind_mapping():
    assert relation_kind("LEY N° 20744 - DEROGACION ART. 28") == "repeals"
    assert relation_kind("REGLAMENTACION") == "regulates"
    assert relation_kind("PRORROGA") == "extends"
    assert relation_kind("VETO PARCIAL") == "vetoes"
    assert relation_kind("NORMA COMPLEMENTARIA") == "complements"
    assert relation_kind("ALGO") == "related"
    assert relation_kind(None) == "related"


def test_real_lct_pages_parse_many_rows():
    modified_by = parse_vinculos(
        (FIXTURE / "vinculos_modificada_por.htm").read_bytes(), 25552, "modificada_por"
    )
    modifies = parse_vinculos((FIXTURE / "vinculos_modifica.htm").read_bytes(), 25552, "modifica")
    assert len(modified_by) >= 250
    assert all(r.target_id == 25552 for r in modified_by)
    assert any(r.source_id == 229909 and r.kind == "consolidates" for r in modified_by)
    assert 10 <= len(modifies) <= 30
    assert all(r.source_id == 25552 for r in modifies)
    assert all(r.fecha_boletin is not None for r in modified_by[:20])
