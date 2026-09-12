from datetime import date

from legal_ai.parse.antecedentes import parse_antecedentes

LINES = [
    "- Artículo 113",
    "sustituido por art. 1° del Decreto",
    "N° 731/2024 B.O. 14/8/2024.",
    "Vigencia: a partir de su",
    "publicación en el BOLETÍN OFICIAL;",
    "- Artículo 2º sustituido por art. 88 de la Ley",
    "N° 27.742 B.O. 8/7/2024.",
    "Vigencia: a partir del día siguiente al de su publicación en el Boletín Oficial;",
    "- Artículo 245, ( Nota Infoleg : Ver - Fondo de cese- art. 96 de la Ley N° 27.742 B.O. 8/7/2024.);",
    "- Artículo 245 bis incorporado por art. 82 del Decreto N° 70/2023 B.O. 21/12/2023;",
    ". Artículo 276 sustituido por art. 4° de la Ley N° 25.561 B.O. 7/1/2002;",
]


def test_parse_antecedentes_items():
    events = parse_antecedentes(LINES)
    assert [(e.article_key, e.kind) for e in events] == [
        ("113", "sustituido"),
        ("2", "sustituido"),
        ("245", "nota"),
        ("245bis", "incorporado"),
        ("276", "sustituido"),
    ]
    first = events[0]
    assert first.article_label == "113"
    assert first.by.tipo == "Decreto" and first.by.numero == "731/2024" and first.by.article == "1"
    assert first.by.bo_date == date(2024, 8, 14)
    assert first.by.vigencia == "a partir de su publicación en el BOLETÍN OFICIAL"
    assert events[3].article_label == "245 bis" and events[3].by.bo_date == date(2023, 12, 21)
    assert events[2].raw.startswith("Artículo 245, ( Nota Infoleg")
    assert events[2].by.numero is None


def test_parse_antecedentes_empty():
    assert parse_antecedentes([]) == []
