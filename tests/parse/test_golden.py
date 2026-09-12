import hashlib
import json
from pathlib import Path

import pytest

from legal_ai.parse.html_text import decode_html, html_to_lines
from legal_ai.parse.structure import parse_text

FIXTURES = Path("tests/fixtures/infoleg")
GOLDEN = Path("tests/fixtures/golden")


@pytest.mark.parametrize(
    "name", ["25552_current", "229909_original", "95487_original", "64555_original"]
)
def test_parser_matches_golden(name: str):
    golden = json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    parsed = parse_text(html_to_lines(decode_html((FIXTURES / golden["file"]).read_bytes())))
    assert len(parsed.articles) == golden["n_articles"]
    for expected, actual in zip(golden["articles"], parsed.articles, strict=True):
        assert actual.key == expected["key"], (expected["key"], actual.raw_header)
        assert actual.heading == expected["heading"], actual.raw_header
        assert actual.status == expected["status"], actual.raw_header
        assert actual.annex == expected["annex"]
        assert [f"{s.kind} {s.number} {s.name or ''}".strip() for s in actual.sections] == expected[
            "sections"
        ]
        assert len(actual.notes) == expected["n_notes"], actual.raw_header
        assert hashlib.sha256(actual.text.encode("utf-8")).hexdigest() == expected["text_sha256"], (
            actual.raw_header
        )
    assert len(parsed.annexes) == golden["n_annexes"]
    assert len(parsed.antecedentes_lines) == golden["n_antecedentes_lines"]
    assert parsed.warnings == golden["warnings"]


def test_lct_known_facts():
    parsed = parse_text(html_to_lines(decode_html((FIXTURES / "25552/texact.htm").read_bytes())))
    keys = [a.key for a in parsed.articles]
    assert len(keys) == 293
    assert keys[:3] == ["1", "2", "3"] and keys[-1] == "278"
    assert {
        "11bis",
        "17bis",
        "29bis",
        "92bis",
        "92ter",
        "102bis",
        "103bis",
        "104bis",
        "105bis",
        "132bis",
        "189bis",
        "197bis",
        "223bis",
        "245bis",
        "255bis",
    } <= set(keys)
    by_key = {a.key: a for a in parsed.articles}
    assert by_key["92bis"].heading == "Período de prueba"
    assert by_key["245"].heading == "Indemnización por antigüedad o despido"
    assert by_key["28"].status == "derogado"
    assert by_key["28"].notes[0].by.numero == "27802"
    derogados = {a.label for a in parsed.articles if a.status == "derogado"}
    assert derogados == {
        "28",
        "54",
        "61",
        "105 bis",
        "113",
        "173",
        "174",
        "175",
        "176",
        "192",
        "193",
        "216",
        "264",
        "265",
        "266",
        "275",
    }
    assert (
        by_key["105bis"].notes[0].by.tipo == "Decreto"
        and by_key["105bis"].notes[0].by.numero == "773/1996"
    )
    assert (
        sum(
            1
            for a in parsed.articles
            for n in a.notes
            if n.kind == "sustituido" and n.affects_whole_article
        )
        == 75
    )
    assert any(s.kind == "TITULO" for s in by_key["245"].sections)


def test_decree_annex_is_the_lct_body():
    parsed = parse_text(html_to_lines(decode_html((FIXTURES / "229909/norma.htm").read_bytes())))
    assert [a.key for a in parsed.main_articles()] == ["1", "2"]
    annex = parsed.annex_articles()
    assert len(annex) == 277
    assert annex[0].heading == "Fuentes de regulación" and annex[-1].key == "277"
    assert parsed.trailer.startswith("VIDELA.")
