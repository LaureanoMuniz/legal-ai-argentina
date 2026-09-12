from legal_ai.index.chunking import build_chunks, choose_version, context_prefix, split_text

DOC = {
    "id_norma": 25552,
    "tipo_norma": "Ley",
    "numeros": ["20744"],
    "titulo_sumario": "LEY DE CONTRATO DE TRABAJO",
}
ART = {
    "id": "25552:245",
    "label": "245",
    "heading": "Indemnización por antigüedad o despido",
    "annex": None,
    "sections": [
        {"kind": "TITULO", "number": "XII", "name": "De la extinción del contrato de trabajo"},
        {"kind": "CAPITULO", "number": "IV", "name": "De la extinción del contrato por despido"},
    ],
}
CUR = {
    "id": "25552:245@current",
    "version_kind": "current",
    "status": "vigente",
    "text": "En los casos de despido dispuesto por el empleador sin justa causa.",
    "effective_from": "2026-03-06",
}
ORIG = {
    "id": "25552:245@original",
    "version_kind": "original",
    "status": "vigente",
    "text": "Texto original.",
    "effective_from": "1976-05-21",
}


def test_context_prefix_reads_like_a_citation():
    assert context_prefix(DOC, ART, CUR) == (
        "Ley 20744 — Ley De Contrato De Trabajo · TITULO XII De la extinción del contrato de trabajo "
        "› CAPITULO IV De la extinción del contrato por despido · Art. 245 — Indemnización por antigüedad o despido. "
        "Vigente desde 2026-03-06."
    )


def test_context_prefix_without_sections_or_heading_or_date():
    art = {**ART, "heading": None, "sections": []}
    assert (
        context_prefix(DOC, art, {**CUR, "effective_from": None})
        == "Ley 20744 — Ley De Contrato De Trabajo · Art. 245."
    )


def test_choose_version_prefers_current_then_original_and_skips_derogated():
    both = choose_version([ORIG, CUR])
    only_original = choose_version([ORIG])
    assert both is not None and both["id"] == "25552:245@current"
    assert only_original is not None and only_original["id"] == "25552:245@original"
    assert choose_version([ORIG, {**CUR, "status": "derogado", "text": ""}]) is None
    assert choose_version([{**ORIG, "text": ""}]) is None


def test_build_chunks_single_chunk_with_embed_text():
    [chunk] = build_chunks(DOC, ART, [ORIG, CUR])
    assert chunk.id == "25552:245@current#0" and chunk.chunk_index == 0
    assert (
        chunk.version_id == "25552:245@current"
        and chunk.article_id == "25552:245"
        and chunk.document_id == 25552
    )
    assert chunk.embed_text == chunk.context_prefix + "\n" + CUR["text"]
    assert chunk.token_estimate == max(1, len(chunk.embed_text) // 4)


def test_build_chunks_skips_annex_articles():
    assert build_chunks(DOC, {**ART, "annex": "ANEXO I"}, [CUR]) == []


def test_split_text_cuts_at_incisos_and_respects_limit():
    lines = ["Encabezado del artículo:"] + [
        f"{chr(97 + i)}) inciso número {i} " + "x" * 400 for i in range(8)
    ]
    text = "\n".join(lines)
    pieces = split_text(text, max_chars=1000)
    assert len(pieces) >= 4
    assert all(len(p) <= 1000 for p in pieces)
    assert "".join(p.replace("\n", "") for p in pieces) == text.replace("\n", "")
    assert all(
        p.startswith(("Encabezado", "a)", "b)", "c)", "d)", "e)", "f)", "g)", "h)")) for p in pieces
    )


def test_split_text_long_single_line_falls_back_to_sentences():
    text = " ".join(f"Oración número {i} termina acá." for i in range(60))
    pieces = split_text(text, max_chars=300)
    assert len(pieces) > 1 and all(len(p) <= 300 for p in pieces)
    assert " ".join(pieces) == text


def test_build_chunks_long_article_yields_indexed_chunks():
    long_cur = {**CUR, "text": "\n".join(f"{chr(97 + i)}) " + "palabra " * 200 for i in range(6))}
    chunks = build_chunks(DOC, ART, [long_cur])
    assert [c.chunk_index for c in chunks] == list(range(len(chunks))) and len(chunks) >= 3
    assert all(c.context_prefix == chunks[0].context_prefix for c in chunks)
    assert chunks[1].id == "25552:245@current#1"
