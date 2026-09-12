from legal_ai.parse.html_text import decode_html, html_to_lines


def test_decode_uses_declared_charset():
    raw = (
        b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252">'
        b"</head><body>Art\xedculo 1\xb0 \x97 Per\xedodo</body></html>"
    )
    assert "Artículo 1° — Período" in decode_html(raw)


def test_decode_falls_back_to_latin1_without_meta():
    raw = b"<html><body>Sanci\xf3n</body></html>"
    assert "Sanción" in decode_html(raw)


def test_decode_never_raises_on_bad_bytes():
    raw = b'<meta charset="utf-8"><body>\xff\xfe</body>'
    assert isinstance(decode_html(raw), str)


def test_html_to_lines_splits_on_blocks_and_breaks():
    doc = (
        "<html><head><script>var x = 1;</script><style>p{}</style></head><body>"
        "<!-- comment --><p align='justify'><b>Art. 92 bis.</b> — <span>Período de prueba.</span></p>"
        "<p>El contrato&nbsp;de trabajo<br>a) hasta ocho (8) meses;<br><br>b) hasta un a&ntilde;o.</p>"
        "<div>  TITULO   I  </div><table><tr><td>Celda</td></tr></table></body></html>"
    )
    assert html_to_lines(doc) == [
        "Art. 92 bis. — Período de prueba.",
        "El contrato de trabajo",
        "a) hasta ocho (8) meses;",
        "b) hasta un año.",
        "TITULO I",
        "Celda",
    ]


def test_html_to_lines_keeps_inline_tags_on_one_line():
    doc = (
        "<p>Art. 28. — <span style='font-style: italic'>(Artículo derogado por art. 207 de la </span>"
        "<a href='x'>Ley Nº 27.802</a><span> B.O. 6/3/2026.)</span></p>"
    )
    assert html_to_lines(doc) == [
        "Art. 28. — (Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026.)"
    ]
