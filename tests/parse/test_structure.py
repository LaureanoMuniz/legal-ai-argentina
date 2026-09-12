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
