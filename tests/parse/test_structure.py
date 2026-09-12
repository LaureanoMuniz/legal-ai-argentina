from legal_ai.parse.structure import parse_text

LCT_LIKE = [
    "INFOLEG",
    "REGIMEN DE CONTRATO DE TRABAJO",
    "LEY N° 20.744 - TEXTO ORDENADO POR DECRETO 390/1976",
    "Bs. As., 13/5/1976",
    "Ver Antecedentes Normativos",
    "LEY DE CONTRATO DE TRABAJO.",
    "TITULO I",
    "Disposiciones Generales",
    "Artículo 1° — Fuentes de regulación.",
    "El contrato de trabajo y la relación de trabajo se rige:",
    "a) Por esta ley.",
    "Art. 2° — Ámbito de aplicación.",
    "La vigencia de esta ley quedará condicionada.",
    "(Artículo sustituido por art. 88 de la Ley N° 27.742 B.O. 8/7/2024. Vigencia: a partir del día siguiente.)",
    "TITULO II",
    "Del Contrato de Trabajo en General",
    "CAPITULO I",
    "Del contrato y la relación de trabajo",
    "Art. 21. —Contrato de trabajo.",
    "Habrá contrato de trabajo, cualquiera sea su forma o denominación.",
    "Art. 28. — (Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026. Vigencia: a partir de su publicación en el Boletín Oficial.)",
    "Art. 29. — Mediación. Intermediación.",
    "Los trabajadores serán considerados empleados directos.",
    "Art. 29 BIS. — El empleador que ocupe",
    "trabajadores a través de una empresa de servicios eventuales.",
    "La indemnización se acumulará a la establecida en el",
    "artículo 245.",
    "Art. 277. — Pago en juicio.",
    "Todo pago que deba realizarse en los juicios laborales.",
    "Antecedentes Normativos",
    "- Artículo 2º sustituido por art. 65 del Decreto N° 70/2023 B.O. 21/12/2023;",
]


def test_front_matter_stops_at_first_marker():
    parsed = parse_text(LCT_LIKE)
    assert parsed.front_matter.splitlines()[0] == "INFOLEG"
    assert parsed.front_matter.splitlines()[-1] == "LEY DE CONTRATO DE TRABAJO."
    assert "Ver Antecedentes Normativos" in parsed.front_matter


def test_articles_hierarchy_and_bodies():
    parsed = parse_text(LCT_LIKE)
    keys = [a.key for a in parsed.articles]
    assert keys == ["1", "2", "21", "28", "29", "29bis", "277"]
    first = parsed.article("1")
    assert first is not None
    assert first.heading == "Fuentes de regulación"
    assert (
        first.text == "El contrato de trabajo y la relación de trabajo se rige:\na) Por esta ley."
    )
    assert [(s.kind, s.number, s.name) for s in first.sections] == [
        ("TITULO", "I", "Disposiciones Generales")
    ]
    art21 = parsed.article("21")
    assert art21 is not None
    assert [(s.kind, s.number, s.name) for s in art21.sections] == [
        ("TITULO", "II", "Del Contrato de Trabajo en General"),
        ("CAPITULO", "I", "Del contrato y la relación de trabajo"),
    ]
    assert art21.ordinal == 3


def test_notes_and_status():
    parsed = parse_text(LCT_LIKE)
    art2 = parsed.article("2")
    assert art2 is not None and art2.status == "vigente"
    assert art2.notes[0].kind == "sustituido" and art2.notes[0].by.numero == "27742"
    art28 = parsed.article("28")
    assert art28 is not None and art28.status == "derogado"
    assert art28.text.startswith("(Artículo derogado por art. 207")


def test_cross_reference_line_is_body_not_header():
    parsed = parse_text(LCT_LIKE)
    bis = parsed.article("29bis")
    assert bis is not None
    assert bis.text.endswith("La indemnización se acumulará a la establecida en el\nartículo 245.")
    assert parsed.article("245") is None


def test_antecedentes_lines_captured_and_not_parsed_as_articles():
    parsed = parse_text(LCT_LIKE)
    assert parsed.antecedentes_lines == [
        "- Artículo 2º sustituido por art. 65 del Decreto N° 70/2023 B.O. 21/12/2023;"
    ]
    assert "numbering gap 29 → 277" in parsed.warnings


DECREE_LIKE = [
    "TRABAJO",
    "DECRETO N° 390",
    "Bs. As., 13/5/76",
    "VISTO lo dispuesto por el artículo 5° de la Ley N° 21.297,",
    "EL PRESIDENTE DE LA NACION ARGENTINA,",
    "DECRETA:",
    "Artículo 1° — Apruébase el texto ordenado del Régimen de Contrato de Trabajo.",
    "Art. 2° — Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese.",
    "VIDELA.",
    "Horacio T. Liendo.",
    "Anexo",
    "TEXTO ORDENADO DEL REGIMEN DE CONTRATO DE TRABAJO",
    "TITULO I",
    "Disposiciones Generales",
    "Artículo 1° — Fuentes de regulación. — El contrato de trabajo se rige:",
    "a) por esta ley;",
    "Art. 2° — Ámbito de aplicación. — La vigencia de esta ley quedará condicionada.",
]


def test_annex_restarts_numbering_and_separates_articles():
    parsed = parse_text(DECREE_LIKE)
    assert [a.key for a in parsed.main_articles()] == ["1", "2"]
    assert [a.key for a in parsed.annex_articles()] == ["1", "2"]
    assert parsed.trailer == "VIDELA.\nHoracio T. Liendo."
    assert parsed.front_matter.splitlines()[-1] == "DECRETA:"
    annex_first = parsed.annex_articles()[0]
    assert annex_first.annex == "ANEXO"
    assert annex_first.heading == "Fuentes de regulación"
    assert annex_first.text == "El contrato de trabajo se rige:\na) por esta ley;"
    assert [(s.kind, s.name) for s in annex_first.sections] == [
        ("TITULO", "Disposiciones Generales")
    ]
    assert [x.label for x in parsed.annexes] == ["ANEXO"]
    assert parsed.annexes[0].text == "TEXTO ORDENADO DEL REGIMEN DE CONTRATO DE TRABAJO"
    assert not any("cross-reference" in w for w in parsed.warnings)


RESOLUTION_LIKE = [
    "Ministerio de Trabajo, Empleo y Seguridad Social",
    "SALARIOS",
    "Resolución 384/2004",
    "Bs. As., 31/5/2004",
    "VISTO el Expediente Nº 1.089.526/2004,",
    "CONSIDERANDO:",
    "Que el artículo 245 de la Ley Nº 20.744 (t.o. 1976) impone la obligación de fijar topes.",
    "Por ello,",
    "RESUELVE:",
    "Artículo 1º — Establécese que los topes indemnizatorios previstos por el artículo 245 se incrementan.",
    "Art. 2º — La medida dispuesta en el artículo anterior es de carácter transitorio.",
    "Art. 3º — Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese.",
    "Carlos A. Tomada.",
    "ANEXO",
    "CONVENIO 130/75 COMERCIO",
    "PROMEDIO $ 1.200 TOPE $ 3.600",
]


def test_resolution_preamble_articles_and_table_annex():
    parsed = parse_text(RESOLUTION_LIKE)
    assert "CONSIDERANDO:" in parsed.front_matter
    assert [a.key for a in parsed.articles] == ["1", "2", "3"]
    assert parsed.articles[0].heading is None
    assert (
        parsed.articles[0].text
        == "Establécese que los topes indemnizatorios previstos por el artículo 245 se incrementan."
    )
    assert parsed.trailer == "Carlos A. Tomada."
    assert parsed.annexes[0].text == "CONVENIO 130/75 COMERCIO\nPROMEDIO $ 1.200 TOPE $ 3.600"


def test_duplicate_key_is_kept_with_warning():
    parsed = parse_text(["Art. 5. — Uno.", "Texto.", "Art. 5. — Dos.", "Texto dos."])
    assert [a.key for a in parsed.articles] == ["5", "5#2"]
    assert "duplicate article 5" in parsed.warnings


MODIFYING_LAW = [
    "LEY 25.877",
    "ARTICULO 18. — Sustitúyese el artículo 245 de la Ley Nº 20.744 (t.o. 1976) por el siguiente:",
    "Artículo 245. — Indemnización por antigüedad o despido. En los casos de despido dispuesto por el empleador sin justa causa.",
    "La base salarial no podrá exceder el equivalente de tres (3) veces el importe mensual.",
    "ARTICULO 19. — Sustitúyese el artículo 3º de la Ley Nº 23.546 y su modificatoria, por el siguiente:",
    "Artículo 3º — Quienes reciban la comunicación del artículo anterior estarán obligados a responder.",
    "ARTICULO 20. — Sustitúyense los artículos 4º y 5º de la Ley Nº 23.546 por los siguientes:",
    "Artículo 4º — En el plazo de quince (15) días a contar desde la recepción.",
    "Artículo 5º — Las partes están obligadas a negociar de buena fe.",
    "ARTICULO 21. — Incorpóranse en la Ley Nº 14.250 los siguientes artículos:",
    "Capítulo III – Ambitos de Negociación Colectiva.",
    "Título preliminar de la negociación.",
    "Consideraciones generales sobre los ámbitos.",
    "Reglas de articulación entre convenios.",
    "Artículo 21. — Los convenios colectivos tendrán los siguientes ámbitos:",
    "— Convenio nacional, regional o de otro ámbito territorial.",
    "Artículo 22. — La representación de los trabajadores en la negociación.",
    "ARTICULO 22. — Cuando por un conflicto de trabajo alguna de las partes decidiera la adopción de medidas.",
    "ARTICULO 23. — Comuníquese al Poder Ejecutivo.",
]


def test_quoted_articles_inside_modifying_law_stay_in_body():
    parsed = parse_text(MODIFYING_LAW)
    assert [a.key for a in parsed.articles] == ["18", "19", "20", "21", "22", "23"]
    art18 = parsed.article("18")
    assert art18 is not None
    assert "Artículo 245. — Indemnización por antigüedad" in art18.text
    assert art18.text.endswith("tres (3) veces el importe mensual.")
    art20 = parsed.article("20")
    assert art20 is not None
    assert "Artículo 4º" in art20.text and "Artículo 5º" in art20.text
    art21 = parsed.article("21")
    assert art21 is not None
    assert "Capítulo III" in art21.text and "Artículo 22. — La representación" in art21.text
    assert all(s.kind != "CAPITULO" for a in parsed.articles for s in a.sections)
    assert not any("cross-reference" in w for w in parsed.warnings)
    assert not any("numbering gap" in w for w in parsed.warnings)


def test_index_table_goes_to_trailer():
    parsed = parse_text(
        [
            "ARTICULO 21.- Con relación a los convenios colectivos.",
            "INDICE DEL ORDENAMIENTO DE LA LEY Nº 14.250",
            "ARTICULO Nº",
            "FUENTE",
            "ARTICULO 1º",
            "artículo 8º de la Ley Nº 25.877",
        ]
    )
    assert [a.key for a in parsed.articles] == ["21"]
    assert parsed.trailer.startswith("INDICE DEL ORDENAMIENTO")
    assert "ARTICULO 1º" in parsed.trailer
    assert parsed.warnings == []


def test_chapter_derogation_propagates_to_sibling_articles():
    parsed = parse_text(
        [
            "CAPITULO VII",
            "Del trabajo",
            "Art. 87. — Uno.",
            "Texto uno.",
            "CAPITULO VIII",
            "De los auxilios",
            "Art. 88. — Auxilios.",
            "Texto ochenta y ocho.",
            "Art. 89. — Peligro.",
            "El trabajador estará obligado. ( Capítulo VIII derogado por art. 26 de la Ley Nº 27.802 B.O. 6/3/2026.)",
            "CAPITULO IX",
            "Otro",
            "Art. 90. — Noventa.",
            "Texto noventa.",
        ]
    )
    status = {a.key: a.status for a in parsed.articles}
    assert status == {"87": "vigente", "88": "derogado", "89": "derogado", "90": "vigente"}
    art88 = parsed.article("88")
    assert art88 is not None and art88.notes[0].by.numero == "27802"


def test_chapter_derogation_outside_its_chapter_is_a_warning_not_a_status():
    parsed = parse_text(
        [
            "CAPITULO VII",
            "De los derechos",
            "Art. 89. — Peligro.",
            "El trabajador estará obligado. ( Capítulo VIII derogado por art. 26 de la Ley Nº 27.802 B.O. 6/3/2026.)",
            "CAPITULO IX",
            "Otro",
            "Art. 90. — Noventa.",
            "Texto noventa.",
        ]
    )
    assert {a.key: a.status for a in parsed.articles} == {"89": "vigente", "90": "vigente"}
    assert parsed.warnings == [
        "capitulo VIII derogation noted at article 89, which is not inside it"
    ]


def test_quoted_articles_without_colon_are_detected_by_style():
    parsed = parse_text(
        [
            "ARTICULO 18. — Incorpóranse en la Ley Nº 14.250 los capítulos que contendrán los artículos que en cada caso se incluyen.",
            "Capítulo III – Ambitos de Negociación Colectiva.",
            "Artículo 21. — Los convenios colectivos tendrán los siguientes ámbitos:",
            "— Convenio nacional.",
            "Artículo 22. — La representación de los trabajadores.",
            "ARTICULO 19. — Sustitúyese el artículo 3º de la Ley Nº 23.546.",
        ]
    )
    assert [a.key for a in parsed.articles] == ["18", "19"]
    assert parsed.warnings == []
