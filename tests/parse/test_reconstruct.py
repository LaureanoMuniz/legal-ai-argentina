from datetime import date

from legal_ai.parse.reconstruct import chain_versions, reconstruct, split_quoted_articles


def docs():
    return [
        {
            "id_norma": 25552,
            "tipo_norma": "Ley",
            "numeros": ["20744"],
            "fecha_boletin": date(1976, 5, 21),
        },
        {
            "id_norma": 93595,
            "tipo_norma": "Ley",
            "numeros": ["25877"],
            "fecha_boletin": date(2004, 3, 19),
        },
        {
            "id_norma": 401266,
            "tipo_norma": "Ley",
            "numeros": ["27742"],
            "fecha_boletin": date(2024, 7, 8),
        },
    ]


def versions():
    return [
        {
            "id": "25552:92bis@original",
            "article_id": "25552:92bis",
            "document_id": 25552,
            "version_kind": "original",
            "text": "Texto de 1995.",
            "effective_from": date(1995, 3, 28),
            "effective_until": date(2024, 7, 8),
            "status": "vigente",
        },
        {
            "id": "25552:92bis@current",
            "article_id": "25552:92bis",
            "document_id": 25552,
            "version_kind": "current",
            "text": "Texto de 2024.",
            "effective_from": date(2024, 7, 8),
            "effective_until": None,
            "status": "vigente",
        },
        {
            "id": "93595:2@original",
            "article_id": "93595:2",
            "document_id": 93595,
            "version_kind": "original",
            "text": 'Sustitúyese el artículo 92 bis de la Ley de Contrato de Trabajo Nº 20.744 (t.o. 1976) y sus modificatorias, por el siguiente: "Artículo 92 bis. — El contrato de trabajo por tiempo indeterminado se entenderá celebrado a prueba durante los primeros tres (3) meses."',
            "effective_from": date(2004, 3, 19),
            "effective_until": None,
            "status": "vigente",
        },
        {
            "id": "401266:91@original",
            "article_id": "401266:91",
            "document_id": 401266,
            "version_kind": "original",
            "text": "Sustitúyese el artículo 92 bis de la ley 20.744 (t.o. 1976) y sus modificatorias por el siguiente:\nArtículo 92 bis: Período de prueba. Texto de 2024.",
            "effective_from": date(2024, 7, 8),
            "effective_until": None,
            "status": "vigente",
        },
    ]


def test_reconstruct_finds_substitutions_targeting_laws_in_corpus():
    rec = reconstruct(docs(), versions())
    assert [(r.article_key, r.effective_from, r.source_numero) for r in rec] == [
        ("92bis", date(2004, 3, 19), "25877"),
        ("92bis", date(2024, 7, 8), "27742"),
    ]
    assert rec[0].text.startswith("El contrato de trabajo por tiempo indeterminado")
    assert rec[1].text == "Período de prueba. Texto de 2024."


def test_chain_versions_inserts_intermediate_and_fixes_ranges():
    vs = versions()
    added = chain_versions(vs, reconstruct(docs(), vs), {"25552:92bis", "93595:2", "401266:91"})
    assert [a["id"] for a in added] == ["25552:92bis@2004-03-19"]
    assert added[0] not in vs
    mid = added[0]
    assert mid["version_kind"] == "reconstructed" and mid["status"] == "historico"
    assert mid["effective_from"] == date(2004, 3, 19) and mid["effective_until"] == date(2024, 7, 8)
    original = next(v for v in vs if v["id"] == "25552:92bis@original")
    assert original["effective_until"] == date(2004, 3, 19)


def test_split_quoted_articles_handles_several():
    pieces = split_quoted_articles(
        "Artículo 16. — Texto dieciséis.\nArtículo 69. — Texto sesenta y nueve."
    )
    assert pieces == [("16", "Texto dieciséis."), ("69", "Texto sesenta y nueve.")]
