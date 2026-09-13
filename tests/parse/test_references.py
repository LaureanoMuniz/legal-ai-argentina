from legal_ai.parse.references import extract_references


def test_extracts_same_law_and_named_law_references():
    versions = [
        {
            "article_id": "25552:178",
            "document_id": 25552,
            "version_kind": "current",
            "text": "dará lugar al pago de una indemnización igual a la prevista en el artículo 182 de esta ley.",
        },
        {
            "article_id": "25552:248",
            "document_id": 25552,
            "version_kind": "current",
            "text": "una indemnización igual a la prevista en el artículo 247 de esta ley, los arts. 249 y 250 no aplican.",
        },
        {
            "article_id": "64555:1",
            "document_id": 64555,
            "version_kind": "original",
            "text": "Las indemnizaciones previstas por la Ley 20.744, artículo 245 se incrementarán; ver artículo 7 de la Ley 25.013 y el artículo 2 de la presente ley.",
        },
        {
            "article_id": "25552:245",
            "document_id": 25552,
            "version_kind": "current",
            "text": "sin justa causa (artículo 245).",
        },
    ]
    ids = {
        "25552:178",
        "25552:182",
        "25552:247",
        "25552:248",
        "25552:249",
        "25552:250",
        "64555:1",
        "64555:2",
        "25552:245",
        "53159:7",
    }
    laws = {"20744": 25552, "25013": 53159}
    refs = {
        (r.source_article_id, r.target_article_id) for r in extract_references(versions, ids, laws)
    }
    assert ("25552:178", "25552:182") in refs
    assert (
        ("25552:248", "25552:247") in refs
        and ("25552:248", "25552:249") in refs
        and ("25552:248", "25552:250") in refs
    )
    assert ("64555:1", "64555:2") in refs and ("64555:1", "53159:7") in refs
    assert ("25552:245", "25552:245") not in refs
