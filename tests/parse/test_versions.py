from datetime import date

from legal_ai.parse.structure import parse_text
from legal_ai.parse.versions import VersionSource, build_articles

ORIGINAL = parse_text(
    [
        "Anexo",
        "TITULO I",
        "Disposiciones Generales",
        "Artículo 1° — Fuentes de regulación. — El contrato se rige por esta ley.",
        "Art. 2° — Ámbito. — La vigencia quedará condicionada a la reglamentación.",
        "Art. 28. — Auxiliares del trabajador. — Si el trabajador estuviese autorizado a servirse de auxiliares.",
        "Art. 92. — Prueba. — La carga de la prueba corresponde al empleador.",
    ]
)
CURRENT = parse_text(
    [
        "TITULO I",
        "Disposiciones Generales",
        "Artículo 1° — Fuentes de regulación.",
        "El contrato se rige por esta ley.",
        "Art. 2° — Ámbito.",
        "La vigencia quedará condicionada a las leyes especiales.",
        "(Artículo sustituido por art. 88 de la Ley N° 27.742 B.O. 8/7/2024. Vigencia: a partir del día siguiente.)",
        "Art. 28. — (Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026.)",
        "Art. 92. — Prueba.",
        "La carga de la prueba corresponde al empleador.",
        "Art. 92 bis. — Período de prueba.",
        "El contrato se entenderá celebrado a prueba durante seis meses.",
        "(Artículo sustituido por art. 91 de la Ley N° 27.742 B.O. 8/7/2024.)",
    ]
)


def build():
    return build_articles(
        25552,
        original=VersionSource(
            parsed=ORIGINAL,
            document_id=229909,
            fecha_boletin=date(1976, 5, 21),
            url="http://o",
            use_annex_articles=True,
        ),
        current=VersionSource(
            parsed=CURRENT, document_id=25552, fecha_boletin=date(1974, 9, 27), url="http://c"
        ),
    )


def test_article_records_follow_current_order_and_carry_hierarchy():
    articles, _, _ = build()
    assert [a.id for a in articles] == ["25552:1", "25552:2", "25552:28", "25552:92", "25552:92bis"]
    assert articles[4].label == "92 bis" and articles[4].heading == "Período de prueba"
    assert articles[0].sections[0].name == "Disposiciones Generales"
    assert all(a.annex is None for a in articles)


def test_unchanged_article_has_two_versions_sharing_dates():
    _, versions, _ = build()
    by_id = {v.id: v for v in versions}
    original, current = by_id["25552:1@original"], by_id["25552:1@current"]
    assert original.text == current.text == "El contrato se rige por esta ley."
    assert original.effective_from == date(1976, 5, 21) and original.effective_until is None
    assert current.effective_from == date(1976, 5, 21)
    assert current.unchanged_from_original is True
    assert original.source_document_id == 229909 and current.source_document_id == 25552


def test_substituted_article_closes_original_and_dates_current():
    _, versions, _ = build()
    by_id = {v.id: v for v in versions}
    assert by_id["25552:2@original"].effective_until == date(2024, 7, 8)
    current = by_id["25552:2@current"]
    assert current.effective_from == date(2024, 7, 8)
    assert current.unchanged_from_original is False
    assert (
        current.modification_kind,
        current.modified_by_tipo,
        current.modified_by_numero,
        current.modified_by_article,
    ) == ("sustituido", "Ley", "27742", "88")
    assert current.text == "La vigencia quedará condicionada a las leyes especiales."
    assert "(Artículo sustituido" in current.text_with_notes


def test_derogated_article():
    _, versions, _ = build()
    by_id = {v.id: v for v in versions}
    assert by_id["25552:28@original"].effective_until == date(2026, 3, 6)
    current = by_id["25552:28@current"]
    assert (
        current.status == "derogado"
        and current.text == ""
        and current.effective_from == date(2026, 3, 6)
    )


def test_article_only_in_current_has_single_version():
    _, versions, _ = build()
    ids = {v.id for v in versions}
    assert "25552:92bis@current" in ids and "25552:92bis@original" not in ids


def test_missing_in_current_warns():
    original = parse_text(["Art. 1. — Uno.", "Texto uno.", "Art. 2. — Dos.", "Texto dos."])
    current = parse_text(["Art. 1. — Uno.", "Texto uno."])
    _, versions, warnings = build_articles(
        7,
        original=VersionSource(
            parsed=original, document_id=7, fecha_boletin=date(2000, 1, 1), url=None
        ),
        current=VersionSource(
            parsed=current, document_id=7, fecha_boletin=date(2000, 1, 1), url=None
        ),
    )
    assert "2: present in original, missing in current" in warnings
    assert any(v.id == "7:2@original" and v.effective_until is None for v in versions)


def test_changed_without_note_warns_and_uses_document_date():
    original = parse_text(["Art. 1. — Uno.", "Texto viejo."])
    current = parse_text(["Art. 1. — Uno.", "Texto nuevo."])
    _, versions, warnings = build_articles(
        7,
        original=VersionSource(
            parsed=original, document_id=7, fecha_boletin=date(2000, 1, 1), url=None
        ),
        current=VersionSource(
            parsed=current, document_id=7, fecha_boletin=date(2001, 6, 1), url=None
        ),
    )
    current_v = next(v for v in versions if v.id == "7:1@current")
    assert current_v.effective_from == date(2001, 6, 1)
    assert "1: current text differs from original but has no dated note" in warnings


def test_only_original_available():
    original = parse_text(
        [
            "ARTICULO 1° — Las indemnizaciones se incrementarán.",
            "ARTICULO 2° — Comuníquese al Poder Ejecutivo Nacional.",
        ]
    )
    articles, versions, warnings = build_articles(
        64555,
        original=VersionSource(
            parsed=original, document_id=64555, fecha_boletin=date(2000, 10, 11), url=None
        ),
        current=None,
    )
    assert [a.id for a in articles] == ["64555:1", "64555:2"]
    assert [v.version_kind for v in versions] == ["original", "original"]
    assert versions[0].effective_from == date(2000, 10, 11) and versions[0].effective_until is None
    assert warnings == []
