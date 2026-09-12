import pytest

from legal_ai.parse.patterns import (
    is_antecedentes,
    is_closing,
    match_annex,
    match_article,
    match_hierarchy,
)


@pytest.mark.parametrize(
    "line,number,suffix,heading,body",
    [
        ("Art. 92 bis. — Período de prueba.", 92, "bis", "Período de prueba", ""),
        ("Art. 29 BIS. — El empleador que ocupe", 29, "bis", None, "El empleador que ocupe"),
        ("Art. 189. Bis — Empresa de la familia.", 189, "bis", "Empresa de la familia", ""),
        (
            "Art. 92 TER. —Contrato de Trabajo a tiempo parcial.",
            92,
            "ter",
            "Contrato de Trabajo a tiempo parcial",
            "",
        ),
        (
            "Artículo 1° — Fuentes de regulación. — El contrato de trabajo se rige:",
            1,
            None,
            "Fuentes de regulación",
            "El contrato de trabajo se rige:",
        ),
        (
            "Art. 245. —Indemnización por antigüedad o despido.",
            245,
            None,
            "Indemnización por antigüedad o despido",
            "",
        ),
        ("Art. 29. — Mediación. Intermediación.", 29, None, "Mediación. Intermediación", ""),
        (
            "ARTICULO 1º.- Apruébase el régimen del contrato de trabajo.",
            1,
            None,
            None,
            "Apruébase el régimen del contrato de trabajo.",
        ),
        (
            "ARTÍCULO 3°: Las disposiciones de los artículos 15 y 22 serán de aplicación.",
            3,
            None,
            None,
            "Las disposiciones de los artículos 15 y 22 serán de aplicación.",
        ),
        (
            "Artículo 1º — Establécese que los topes indemnizatorios previstos por el artículo 245 de la Ley Nº 20.744 (t.o. 1976) se incrementan.",
            1,
            None,
            None,
            "Establécese que los topes indemnizatorios previstos por el artículo 245 de la Ley Nº 20.744 (t.o. 1976) se incrementan.",
        ),
        (
            "Art. 3º — Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese.",
            3,
            None,
            None,
            "Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese.",
        ),
        ("Art.4 - Concepto de trabajo.", 4, None, "Concepto de trabajo", ""),
        ("Art. 132 BIS.", 132, "bis", None, ""),
        (
            "Art. 28. — (Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026.)",
            28,
            None,
            None,
            "(Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026.)",
        ),
    ],
)
def test_match_article_variants(line, number, suffix, heading, body):
    header = match_article(line)
    assert header is not None, line
    assert (header.number, header.suffix, header.heading, header.body) == (
        number,
        suffix,
        heading,
        body,
    )
    assert header.raw == line


def test_article_label_and_key():
    header = match_article("Art. 92 bis. — Período de prueba.")
    assert header is not None
    assert header.label == "92 bis"
    assert header.key == "92bis"
    plain = match_article("Art. 245. —Indemnización.")
    assert plain is not None and plain.label == "245" and plain.key == "245"


@pytest.mark.parametrize(
    "line",
    [
        "artículo 245 de la Ley N° 20.744",
        "Artículo 44 de la Ley N° 25.345 derogado por art. 56",
        "Artículos 173 a 176 quedan derogados.",
        "Los artículos 15, 22 y 29 serán de aplicación.",
        "Art. de fe",
        "ARTICULOS TRANSITORIOS",
    ],
)
def test_match_article_rejects_cross_references(line):
    assert match_article(line) is None


@pytest.mark.parametrize(
    "line,kind,number,name",
    [
        ("TITULO I", "TITULO", "I", None),
        ("TÍTULO XII", "TITULO", "XII", None),
        ("CAPITULO IV", "CAPITULO", "IV", None),
        ("CAPÍTULO II - De los sujetos", "CAPITULO", "II", "De los sujetos"),
        ("SECCION 3: Del pago", "SECCION", "3", "Del pago"),
        ("LIBRO PRIMERO", "LIBRO", "PRIMERO", None),
    ],
)
def test_match_hierarchy(line, kind, number, name):
    section = match_hierarchy(line)
    assert section is not None
    assert (section.kind, section.number, section.name) == (kind, number, name)


def test_match_hierarchy_rejects_prose():
    assert match_hierarchy("TITULO II de la Ley 20.744 establece que el contrato...") is None
    assert match_hierarchy("Disposiciones Generales") is None


def test_match_annex():
    assert match_annex("ANEXO") == "ANEXO"
    assert match_annex("Anexo") == "ANEXO"
    assert match_annex("ANEXO I") == "ANEXO I"
    assert match_annex("ANEXO A - Escala salarial") == "ANEXO A"
    assert match_annex("Los anexos forman parte de la presente.") is None


def test_markers():
    assert is_antecedentes("Antecedentes Normativos")
    assert not is_antecedentes("Ver Antecedentes Normativos")
    assert is_closing(
        "Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese."
    )
    assert is_closing("Comuníquese al Poder Ejecutivo Nacional.")
    assert not is_closing("El empleador deberá comunicar el despido por escrito.")
