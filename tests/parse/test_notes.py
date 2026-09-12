from datetime import date

from legal_ai.parse.notes import parse_by_clause, parse_notes, strip_notes

SUSTITUIDO = (
    "El contrato de trabajo por tiempo indeterminado se entenderá celebrado a prueba durante los "
    "primeros seis (6) meses. (Artículo sustituido por art. 91 de la Ley N° 27.742 B.O. 8/7/2024. "
    "Vigencia: a partir del día siguiente al de su publicación en el Boletín Oficial de la República Argentina.)"
)


def test_parse_by_clause_full():
    by = parse_by_clause(
        "art. 91 de la Ley N° 27.742 B.O. 8/7/2024. Vigencia: a partir del día siguiente."
    )
    assert by.tipo == "Ley"
    assert by.numero == "27742"
    assert by.article == "91"
    assert by.bo_date == date(2024, 7, 8)
    assert by.vigencia == "a partir del día siguiente"


def test_parse_by_clause_decree_with_year_and_no_vigencia():
    by = parse_by_clause("art. 1° del Decreto N° 731/2024 B.O. 14/8/2024")
    assert (by.tipo, by.numero, by.article, by.bo_date, by.vigencia) == (
        "Decreto",
        "731/2024",
        "1",
        date(2024, 8, 14),
        None,
    )


def test_parse_by_clause_without_article():
    by = parse_by_clause("Ley Nº 25.877 B.O. 19/3/2004")
    assert (by.tipo, by.numero, by.article, by.bo_date) == ("Ley", "25877", None, date(2004, 3, 19))


def test_parse_notes_sustituido():
    notes = parse_notes(SUSTITUIDO)
    assert len(notes) == 1
    note = notes[0]
    assert note.kind == "sustituido"
    assert note.scope == "articulo"
    assert note.affects_whole_article
    assert note.by.numero == "27742" and note.by.bo_date == date(2024, 7, 8)
    assert note.raw.startswith("(Artículo sustituido por")


def test_parse_notes_derogado_with_link_spacing():
    text = "(Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026. Vigencia: a partir de su publicación en el Boletín Oficial.)"
    [note] = parse_notes(text)
    assert note.kind == "derogado" and note.scope == "articulo"
    assert (
        note.by.numero == "27802"
        and note.by.article == "207"
        and note.by.bo_date == date(2026, 3, 6)
    )


def test_parse_notes_inciso_and_parrafo_are_partial():
    text = (
        "a) Texto del inciso. (Inciso a) sustituido por art. 3° de la Ley N° 26.088 B.O. 24/4/2006) "
        "Último párrafo. (Último párrafo incorporado por art. 2° de la Ley N° 25.345 B.O. 17/11/2000)"
    )
    notes = parse_notes(text)
    assert [(n.kind, n.scope, n.scope_detail) for n in notes] == [
        ("sustituido", "inciso", "a)"),
        ("incorporado", "parrafo", "último"),
    ]
    assert not any(n.affects_whole_article for n in notes)


def test_parse_notes_incorporado_split_across_lines():
    text = "Texto.\n(Artículo incorporado por art. 57 de\nla Ley\nNº 27.802 B.O. 6/3/2026.\nVigencia: a partir de su publicación en el\nBoletín Oficial.)"
    [note] = parse_notes(text)
    assert note.kind == "incorporado" and note.by.numero == "27802" and note.by.article == "57"


def test_parse_notes_ignores_ordinary_parentheses():
    assert parse_notes("durante los primeros seis (6) meses (t.o. 1976) sin nota") == []


def test_strip_notes():
    assert strip_notes(SUSTITUIDO) == (
        "El contrato de trabajo por tiempo indeterminado se entenderá celebrado a prueba durante los "
        "primeros seis (6) meses."
    )
