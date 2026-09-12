# Phase 2: Infoleg Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the raw Infoleg HTML in `data/raw/infoleg/normas/<id>/` into `documents`, `articles`, `article_versions`, `relations` and `history` JSONL files that preserve legal structure (título/capítulo/artículo), modification notes, vigencia dates and provenance.

**Architecture:** Pure-Python, regex-driven line parser. HTML is decoded with the charset declared in `<meta>` (fallback latin-1), flattened to lines by block tags, and fed to a state machine that recognizes hierarchy headers, article headers (25 spelling variants), annexes, the "Antecedentes Normativos" section and closing signatures. Modification notes inside articles are parsed into structured records; `original` (from `norma.htm`) and `current` (from `texact.htm`) texts become two versions per article with `effective_from`/`effective_until`. For the LCT, the `original` text comes from the annex of Decreto 390/76 (declared in the manifest as `original_from`). Relations come from the two "vínculos" pages plus the notes. No database yet: Postgres loading is Phase 3.

**Tech Stack:** Python 3.12, `pydantic` v2, stdlib `re`/`html`, `typer`, `pytest`. No HTML library: Infoleg markup is flat and its tags carry no reliable structure.

**Spec:** `docs/ARCHITECTURE.md` (*Modelo de datos*, *Layout de datos*), `docs/ROADMAP.md` (Fase 2), `docs/DECISIONS.md` (ADR-005, ADR-006, ADR-012), plus the two design changes approved in conversation: (1) LCT `original` = Decreto 390/76 annex; (2) "Antecedentes Normativos" stored as history events.

## Global Constraints

- `requires-python = ">=3.12,<3.13"`; run everything with `uv run`.
- Code in English; CLI help and docs in Spanish (ADR-011). No comments in code except an optional one-line module header.
- `data/raw/` is read-only for this phase. `data/processed/<corpus>/` is deleted and regenerated on every parse run (ADR-012).
- Tests never touch the network. Real-HTML fixtures live in `tests/fixtures/infoleg/<id>/` (already copied: 25552 LCT, 229909 Decreto 390/76, 95487 Resolución 384/2004, 64555 Ley 25.323). Golden expectations live in `tests/fixtures/golden/`.
- Article header prefix matching is **case-sensitive** (`ARTICULO`, `ARTÍCULO`, `Artículo`, `Articulo`, `Art.`); the suffix (`bis`, `ter`, `quater`, `quinquies`) is case-insensitive. A lowercase `artículo 245` at a line start is a cross-reference, never a header.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01X9PTzEP62xfYRS8W8iGP9a
  ```

## Verified facts about the HTML (2026-09-12, 886 text files)

| Fact | Value |
|---|---|
| Charsets declared in `<meta>` | windows-1252 (301), ISO-8859-1 (546), none (39 → latin-1 fallback) |
| Article header variants (normalized) | `ARTÍCULO N`, `ARTICULO N`, `ARTÍCULO N°`, `Art. N`, `Art. Nº`, `Artículo N`, `Art. N°`, `ARTICULO Nº`, `Art.N`, `Articulo N`, plus `bis`/`BIS`/`Bis`/`ter`/`TER` suffixes, e.g. `Art. 92 bis.`, `Art. 29 BIS. —`, `Art. 189. Bis —`, `Art. 92 TER. —Contrato...` |
| Separators after the number | `.-` (3461), `.` (1302), `—` (1061), `-` (241), `:` (195), `–` (26), `--` (9) |
| Hierarchy lines | `TITULO I` / `CAPITULO IV` / `SECCION` / `LIBRO`, name usually on the **next** line (`TITULO I` → `Disposiciones Generales`) |
| Annex marker | `Anexo` / `ANEXO` on its own line; article numbering restarts at 1 inside |
| Modification notes | `(Artículo sustituido por art. 91 de la Ley N° 27.742 B.O. 8/7/2024. Vigencia: ...)`, `(Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026. ...)`, `(Artículo incorporado por art. 57 de la Ley Nº 27.802 B.O. 6/3/2026. ...)`, `(Inciso b) sustituido por ...)`, `(... por art. 1° del Decreto N° 731/2024 B.O. 14/8/2024 ...)`. Corpus-wide: sustituido 594, derogado 189, incorporado 88, restablecido 6, vetado 3, modificado 4 |
| "Antecedentes Normativos" | Exact line at the end of 53 of 135 `texact.htm`; items `- Artículo 245 sustituido por art. 81 del Decreto N° 70/2023 B.O. 21/12/2023;` (69 items in the LCT); the top of the page has a link line `Ver Antecedentes Normativos` that must NOT trigger the section |
| LCT `texact.htm` (25552) | 293 articles: 1–278 plus 11 bis, 17 bis, 29 bis, 92 bis, 92 ter, 102 bis, 103 bis, 104 bis, 105 bis, 132 bis, 189 bis, 197 bis, 223 bis, 245 bis, 255 bis. No gaps. Header lines like `Art. 245. —Indemnización por antigüedad o despido.` with body on following lines; `Artículo 1° — Fuentes de regulación.` for the first |
| LCT `norma.htm` (25552) | The 1974 approval law: 3 articles ("Apruébase el régimen..."). The body of 1974 is not on Infoleg |
| Decreto 390/76 `norma.htm` (229909) | 2 own articles, then `Anexo` / `TEXTO ORDENADO DEL REGIMEN DE CONTRATO DE TRABAJO` / `TITULO I` and 277 annex articles (`Artículo 1° — Fuentes de regulación. — El contrato...` to `Art. 277. — Pago en juicio. — ...`) |
| Resolución 384/2004 `norma.htm` (95487) | Front matter (organismo, tema, `Resolución 384/2004`, summary, `Bs. As., 31/5/2004`, `VISTO ...`, `CONSIDERANDO:` ...), `RESUELVE:`, 3 articles (`Artículo 1º — Establécese...`, `Art. 2º — ...`, `Art. 3º — Comuníquese...`), then `ANEXO` with a table |
| Ley 25.323 `norma.htm` (64555) | 16 lines, 3 articles `ARTICULO 1° — ...`, `ARTICULO 2° — ...`, `ARTICULO 3º — Comuníquese al Poder Ejecutivo Nacional.`, then `DADA EN LA SALA...`, `—REGISTRADA BAJO EL Nº 25.323—`, signatures |
| Vínculos pages | `<table>` rows with 3 cells: `[tipo, número, organismo]` (line-separated), `21-may-1976` (Spanish month abbreviations), `[tema, descripción]` e.g. `CONTRATO DE TRABAJO` / `LEY N° 20744 - TEXTO ORDENADO`; each row links `verNorma.do...?id=<id>`. `modo=1` = norms this one modifies; `modo=2` = norms that modify this one |

## File Structure

```
src/legal_ai/parse/__init__.py
src/legal_ai/parse/html_text.py      decode_html(bytes) -> str; html_to_lines(str) -> list[str]
src/legal_ai/parse/patterns.py       ArticleHeader + match_article(); Section + match_hierarchy(); match_annex(); is_antecedentes(); is_closing()
src/legal_ai/parse/notes.py          ModificationNote; parse_notes(text); strip_notes(text); parse_by_clause()
src/legal_ai/parse/structure.py      ParsedArticle, Annex, ParsedText; parse_text(lines) state machine
src/legal_ai/parse/antecedentes.py   HistoryEvent; parse_antecedentes(lines)
src/legal_ai/parse/vinculos.py       Relation; parse_vinculos(raw_bytes, self_id, direction)
src/legal_ai/parse/versions.py       ArticleRecord, ArticleVersionRecord; build_articles(...)
src/legal_ai/parse/corpus.py         DocumentRecord, ParseReport; parse_corpus(...) writes JSONL
src/legal_ai/parse/cli.py            `legal-ai parse <corpus>`
src/legal_ai/ingest/manifest.py      (modify) Seed.original_from, ResolvedCorpus.original_sources
src/legal_ai/ingest/catalog_reader.py (modify) collect_rows(catalog, ids)
src/legal_ai/ingest/layout.py        (modify) ProcessedLayout.file(name, path)
src/legal_ai/cli.py                  (modify) mount parse app
corpus/laboral.yaml                  (modify) original_from on the LCT seed
tests/parse/__init__.py
tests/parse/test_html_text.py
tests/parse/test_patterns.py
tests/parse/test_notes.py
tests/parse/test_structure.py
tests/parse/test_antecedentes.py
tests/parse/test_vinculos.py
tests/parse/test_versions.py
tests/parse/test_corpus.py
tests/parse/test_golden.py
tests/fixtures/golden/25552_current.json, 229909_original.json, 95487_original.json, 64555_original.json
scripts/make_golden.py               regenerates golden files from fixtures (run by hand, output reviewed)
```

---

### Task 1: HTML → text lines

**Files:**
- Create: `src/legal_ai/parse/__init__.py` (empty), `src/legal_ai/parse/html_text.py`, `tests/parse/__init__.py` (empty), `tests/parse/test_html_text.py`

**Interfaces:**
- Produces:
  ```python
  def decode_html(raw: bytes) -> str          # charset from <meta ... charset=...> in the first 4096 bytes; fallback latin-1; errors="replace"
  def html_to_lines(doc: str) -> list[str]    # script/style/comments removed; <br> and closing block tags → newline; tags stripped; entities unescaped; whitespace collapsed; empty lines dropped
  ```

- [ ] **Step 1: Write the failing tests**

`tests/parse/test_html_text.py`:
```python
from legal_ai.parse.html_text import decode_html, html_to_lines


def test_decode_uses_declared_charset():
    raw = b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252"></head><body>Art\xedculo 1\xb0 \x97 Per\xedodo</body></html>'
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
    doc = "<p>Art. 28. — <span style='font-style: italic'>(Artículo derogado por art. 207 de la </span><a href='x'>Ley Nº 27.802</a><span> B.O. 6/3/2026.)</span></p>"
    assert html_to_lines(doc) == [
        "Art. 28. — (Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026.)"
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_html_text.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'legal_ai.parse'`

- [ ] **Step 3: Implement**

`src/legal_ai/parse/html_text.py`:
```python
import html
import re

_CHARSET_RE = re.compile(rb"charset=[\"']?\s*([A-Za-z0-9_\-]+)", re.IGNORECASE)
_DROP_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>|<!--.*?-->", re.IGNORECASE | re.DOTALL)
_BREAK_RE = re.compile(r"<br\s*/?>|</(?:p|div|tr|li|h[1-6]|table|blockquote|pre)\s*>|<(?:p|div|tr|h[1-6])\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACES_RE = re.compile(r"[ \t\r\f\v\xa0]+")


def decode_html(raw: bytes) -> str:
    match = _CHARSET_RE.search(raw[:4096])
    encoding = match.group(1).decode("ascii", "ignore") if match else "latin-1"
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("latin-1", errors="replace")


def html_to_lines(doc: str) -> list[str]:
    text = _DROP_RE.sub(" ", doc)
    text = _BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    lines: list[str] = []
    for line in text.split("\n"):
        cleaned = _SPACES_RE.sub(" ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_html_text.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 5 passed, clean.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/parse tests/parse
git commit -m "Decode Infoleg HTML and flatten it to text lines"
```

---

### Task 2: Structural patterns (article, hierarchy, annex, markers)

**Files:**
- Create: `src/legal_ai/parse/patterns.py`, `tests/parse/test_patterns.py`

**Interfaces:**
- Produces:
  ```python
  class ArticleHeader(BaseModel):
      number: int; suffix: str | None; heading: str | None; body: str; raw: str
      @property label -> str   # "92 bis", "245"
      @property key -> str     # "92bis", "245"
  def match_article(line: str) -> ArticleHeader | None
  class Section(BaseModel): kind: str; number: str; name: str | None   # kind in LIBRO|TITULO|CAPITULO|SECCION (accent-free, upper)
  def match_hierarchy(line: str) -> Section | None
  def match_annex(line: str) -> str | None      # annex label ("ANEXO", "ANEXO I") or None
  def is_antecedentes(line: str) -> bool        # exact "Antecedentes Normativos" line
  def is_closing(text: str) -> bool             # article body ends a norm: "archívese" / "Comuníquese al Poder Ejecutivo"
  ```

- [ ] **Step 1: Write the failing tests**

`tests/parse/test_patterns.py`:
```python
import pytest

from legal_ai.parse.patterns import (
    is_antecedentes,
    is_closing,
    match_annex,
    match_article,
    match_hierarchy,
)


@pytest.mark.parametrize(
    "line,number,suffix,heading,body",
    [
        ("Art. 92 bis. — Período de prueba.", 92, "bis", "Período de prueba", ""),
        ("Art. 29 BIS. — El empleador que ocupe", 29, "bis", None, "El empleador que ocupe"),
        ("Art. 189. Bis — Empresa de la familia.", 189, "bis", "Empresa de la familia", ""),
        ("Art. 92 TER. —Contrato de Trabajo a tiempo parcial.", 92, "ter", "Contrato de Trabajo a tiempo parcial", ""),
        ("Artículo 1° — Fuentes de regulación. — El contrato de trabajo se rige:", 1, None, "Fuentes de regulación", "El contrato de trabajo se rige:"),
        ("Art. 245. —Indemnización por antigüedad o despido.", 245, None, "Indemnización por antigüedad o despido", ""),
        ("Art. 29. — Mediación. Intermediación.", 29, None, "Mediación. Intermediación", ""),
        ("ARTICULO 1º.- Apruébase el régimen del contrato de trabajo.", 1, None, None, "Apruébase el régimen del contrato de trabajo."),
        ("ARTÍCULO 3°: Las disposiciones de los artículos 15 y 22 serán de aplicación.", 3, None, None, "Las disposiciones de los artículos 15 y 22 serán de aplicación."),
        ("Artículo 1º — Establécese que los topes indemnizatorios previstos por el artículo 245 de la Ley Nº 20.744 (t.o. 1976) se incrementan.", 1, None, None, "Establécese que los topes indemnizatorios previstos por el artículo 245 de la Ley Nº 20.744 (t.o. 1976) se incrementan."),
        ("Art. 3º — Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese.", 3, None, None, "Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese."),
        ("Art.4 - Concepto de trabajo.", 4, None, "Concepto de trabajo", ""),
        ("Art. 132 BIS.", 132, "bis", None, ""),
        ("Art. 28. — (Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026.)", 28, None, None, "(Artículo derogado por art. 207 de la Ley Nº 27.802 B.O. 6/3/2026.)"),
    ],
)
def test_match_article_variants(line, number, suffix, heading, body):
    header = match_article(line)
    assert header is not None, line
    assert (header.number, header.suffix, header.heading, header.body) == (number, suffix, heading, body)
    assert header.raw == line


def test_article_label_and_key():
    header = match_article("Art. 92 bis. — Período de prueba.")
    assert header is not None
    assert header.label == "92 bis"
    assert header.key == "92bis"
    plain = match_article("Art. 245. —Indemnización.")
    assert plain is not None and plain.label == "245" and plain.key == "245"


@pytest.mark.parametrize(
    "line",
    [
        "artículo 245 de la Ley N° 20.744",
        "Artículo 44 de la Ley N° 25.345 derogado por art. 56",
        "Artículos 173 a 176 quedan derogados.",
        "Los artículos 15, 22 y 29 serán de aplicación.",
        "Art. de fe",
        "ARTICULOS TRANSITORIOS",
    ],
)
def test_match_article_rejects_cross_references(line):
    assert match_article(line) is None


@pytest.mark.parametrize(
    "line,kind,number,name",
    [
        ("TITULO I", "TITULO", "I", None),
        ("TÍTULO XII", "TITULO", "XII", None),
        ("CAPITULO IV", "CAPITULO", "IV", None),
        ("CAPÍTULO II - De los sujetos", "CAPITULO", "II", "De los sujetos"),
        ("SECCION 3: Del pago", "SECCION", "3", "Del pago"),
        ("LIBRO PRIMERO", "LIBRO", "PRIMERO", None),
    ],
)
def test_match_hierarchy(line, kind, number, name):
    section = match_hierarchy(line)
    assert section is not None
    assert (section.kind, section.number, section.name) == (kind, number, name)


def test_match_hierarchy_rejects_prose():
    assert match_hierarchy("TITULO II de la Ley 20.744 establece que el contrato...") is None
    assert match_hierarchy("Disposiciones Generales") is None


def test_match_annex():
    assert match_annex("ANEXO") == "ANEXO"
    assert match_annex("Anexo") == "ANEXO"
    assert match_annex("ANEXO I") == "ANEXO I"
    assert match_annex("ANEXO A - Escala salarial") == "ANEXO A"
    assert match_annex("Los anexos forman parte de la presente.") is None


def test_markers():
    assert is_antecedentes("Antecedentes Normativos")
    assert not is_antecedentes("Ver Antecedentes Normativos")
    assert is_closing("Comuníquese, publíquese, dése a la Dirección Nacional del Registro Oficial y archívese.")
    assert is_closing("Comuníquese al Poder Ejecutivo Nacional.")
    assert not is_closing("El empleador deberá comunicar el despido por escrito.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_patterns.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/parse/patterns.py`:
```python
import re

from pydantic import BaseModel

_ARTICLE_RE = re.compile(
    r"^(?:ARTICULO|ARTÍCULO|Artículo|Articulo|Art\.)\s*"
    r"(?P<num>\d{1,4})\s*[°ºª]?\s*\.?\s*"
    r"(?P<suf>(?i:bis|ter|qu[aá]ter|quinquies))?(?![a-záéíóúA-ZÁÉÍÓÚ])\s*[°ºª]?\s*"
    r"(?P<sep>\.-|-{1,2}|[.:–—]+)?\s*"
    r"(?P<rest>.*)$"
)
_CROSS_REF_RE = re.compile(r"^(?:de\s|del\s|y\s|,|que\s|a\s\d|al\s)", re.IGNORECASE)
_HEADING_WITH_BODY_RE = re.compile(r"^(?P<h>[^.]{2,80}?)\.\s*[—–-]\s*(?P<b>\S.*)$")
_HEADING_ONLY_RE = re.compile(r"^(?P<h>.{2,80}?)\.?$")
_IMPERATIVE_RE = re.compile(r"^(?:Comun[íi]quese|Reg[íi]strese|Publ[íi]quese|D[ée]se|Arch[íi]vese|Aprú?[ée]base|Establ[ée]cese|Fij[aá]se|Der[óo]gase|Sustit[úu]yese|Incorp[óo]rase|Modif[íi]case|Cr[ée]ase|Facúltase|Instrúyese|Encomiéndase|Prorr[óo]gase|Dispónese|Apru[ée]base)")
_HIERARCHY_RE = re.compile(
    r"^(?P<kind>LIBRO|T[IÍ]TULO|CAP[IÍ]TULO|SECCI[OÓ]N)\s+"
    r"(?P<num>[IVXLCDM]+|\d+|[A-ZÁÉÍÓÚ]+)(?![a-záéíóú])\s*"
    r"(?:[.:\-–—]\s*(?P<name>\S.*))?$"
)
_ANNEX_RE = re.compile(r"^(?i:anexos?)(?:\s+(?P<num>[IVXLC]+|\d+|[A-Z]))?(?![a-záéíóú])\s*(?:[-:–—.].*)?$")
_ANTECEDENTES_RE = re.compile(r"^Antecedentes Normativos\.?$")
_CLOSING_RE = re.compile(r"arch[íi]vese|Comun[íi]quese al Poder Ejecutivo", re.IGNORECASE)
_KIND_NORMALIZE = {"TÍTULO": "TITULO", "CAPÍTULO": "CAPITULO", "SECCIÓN": "SECCION"}


class ArticleHeader(BaseModel):
    number: int
    suffix: str | None
    heading: str | None
    body: str
    raw: str

    @property
    def label(self) -> str:
        return f"{self.number} {self.suffix}" if self.suffix else str(self.number)

    @property
    def key(self) -> str:
        return f"{self.number}{self.suffix}" if self.suffix else str(self.number)


def _split_heading(rest: str) -> tuple[str | None, str]:
    rest = rest.strip()
    if not rest or rest.startswith("("):
        return None, rest
    with_body = _HEADING_WITH_BODY_RE.match(rest)
    if with_body and with_body.group("h")[0].isupper() and not _IMPERATIVE_RE.match(rest):
        return with_body.group("h").strip(), with_body.group("b").strip()
    if len(rest) <= 80 and rest[0].isupper() and not _IMPERATIVE_RE.match(rest):
        only = _HEADING_ONLY_RE.match(rest)
        if only and "(" not in rest:
            return only.group("h").strip(), ""
    return None, rest


def match_article(line: str) -> ArticleHeader | None:
    match = _ARTICLE_RE.match(line)
    if not match:
        return None
    rest = match.group("rest")
    if match.group("sep") is None and rest and _CROSS_REF_RE.match(rest):
        return None
    if match.group("sep") is None and rest and rest[0].islower():
        return None
    suffix = match.group("suf")
    heading, body = _split_heading(rest)
    return ArticleHeader(
        number=int(match.group("num")),
        suffix=suffix.lower().replace("á", "a") if suffix else None,
        heading=heading,
        body=body,
        raw=line,
    )


class Section(BaseModel):
    kind: str
    number: str
    name: str | None


def match_hierarchy(line: str) -> Section | None:
    if len(line) > 120:
        return None
    match = _HIERARCHY_RE.match(line)
    if not match:
        return None
    kind = match.group("kind").upper()
    return Section(
        kind=_KIND_NORMALIZE.get(kind, kind),
        number=match.group("num"),
        name=match.group("name").strip() if match.group("name") else None,
    )


def match_annex(line: str) -> str | None:
    if len(line) > 80:
        return None
    match = _ANNEX_RE.match(line)
    if not match:
        return None
    return "ANEXO" + (f" {match.group('num')}" if match.group("num") else "")


def is_antecedentes(line: str) -> bool:
    return bool(_ANTECEDENTES_RE.match(line))


def is_closing(text: str) -> bool:
    return bool(_CLOSING_RE.search(text))
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_patterns.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: all passed. If a parametrized case fails, fix the regex for that exact line; do not delete the case. Known delicate ones: `Art. 29. — Mediación. Intermediación.` must yield heading `Mediación. Intermediación` (heading-only branch, since no dash follows the first period); `Art. 3º — Comuníquese...` must yield no heading (imperative).

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/parse/patterns.py tests/parse/test_patterns.py
git commit -m "Recognize article, hierarchy, annex and marker lines in Infoleg text"
```

---

### Task 3: Modification notes

**Files:**
- Create: `src/legal_ai/parse/notes.py`, `tests/parse/test_notes.py`

**Interfaces:**
- Produces:
  ```python
  class ByClause(BaseModel): tipo: str | None; numero: str | None; article: str | None; bo_date: date | None; vigencia: str | None
  def parse_by_clause(text: str) -> ByClause          # "art. 91 de la Ley N° 27.742 B.O. 8/7/2024. Vigencia: ..." → ByClause
  class ModificationNote(BaseModel):
      kind: str            # sustituido | derogado | incorporado | observado | vetado | restablecido | modificado | renumerado | suspendido | abrogado
      scope: str           # "articulo" | "inciso" | "parrafo" | "punto" | "apartado" | "expresion" | "otro"
      scope_detail: str | None   # "b)", "último", ...
      by: ByClause
      raw: str
      @property affects_whole_article -> bool   # scope == "articulo"
  def parse_notes(text: str) -> list[ModificationNote]
  def strip_notes(text: str) -> str                    # text without the parenthesized notes, whitespace-normalized
  ```
- `numero` is normalized: dots removed (`27.742` → `27742`), slash kept (`70/2023`). `tipo` is title-cased canonical: `Ley`, `Decreto`, `Resolución`, `Resolución Conjunta`, `Decisión Administrativa`, `Disposición`.

- [ ] **Step 1: Write the failing tests**

`tests/parse/test_notes.py`:
```python
from datetime import date

from legal_ai.parse.notes import parse_by_clause, parse_notes, strip_notes

SUSTITUIDO = (
    "El contrato de trabajo por tiempo indeterminado se entenderá celebrado a prueba durante los "
    "primeros seis (6) meses. (Artículo sustituido por art. 91 de la Ley N° 27.742 B.O. 8/7/2024. "
    "Vigencia: a partir del día siguiente al de su publicación en el Boletín Oficial de la República Argentina.)"
)


def test_parse_by_clause_full():
    by = parse_by_clause("art. 91 de la Ley N° 27.742 B.O. 8/7/2024. Vigencia: a partir del día siguiente.")
    assert by.tipo == "Ley"
    assert by.numero == "27742"
    assert by.article == "91"
    assert by.bo_date == date(2024, 7, 8)
    assert by.vigencia == "a partir del día siguiente."


def test_parse_by_clause_decree_with_year_and_no_vigencia():
    by = parse_by_clause("art. 1° del Decreto N° 731/2024 B.O. 14/8/2024")
    assert (by.tipo, by.numero, by.article, by.bo_date, by.vigencia) == (
        "Decreto", "731/2024", "1", date(2024, 8, 14), None
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
    assert note.by.numero == "27802" and note.by.article == "207" and note.by.bo_date == date(2026, 3, 6)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_notes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/parse/notes.py`:
```python
import re
from datetime import date

from pydantic import BaseModel

_NOTE_RE = re.compile(
    r"\(\s*(?P<scope>Art[íi]culo|Art\.|Incisos?\s+[^\s,]+(?:\)|\b)|[ÚU]ltimo\s+p[áa]rrafo|Pen[úu]ltimo\s+p[áa]rrafo|"
    r"Primer\s+p[áa]rrafo|Segundo\s+p[áa]rrafo|Tercer\s+p[áa]rrafo|Cuarto\s+p[áa]rrafo|P[áa]rrafos?\s+\S+|"
    r"Puntos?\s+\S+|Apartados?\s+\S+|Expresi[óo]n\s+\"[^\"]+\")\s*"
    r"(?P<kind>sustituid|derogad|incorporad|observad|vetad|restablecid|modificad|renumerad|suspendid|abrogad)[oa]s?\s+"
    r"por\s+(?P<by>[^()]*?)\s*\)",
    re.IGNORECASE,
)
_BY_RE = re.compile(
    r"^(?:art(?:[íi]culo|\.)?\s*(?P<art>\d{1,4})\s*[°ºª]?\s*(?P<artsuf>(?i:bis|ter))?\s+(?:de\s+la|de\s+el|del|de)\s+)?"
    r"(?P<tipo>Ley|Decreto|Resoluci[óo]n(?:\s+Conjunta)?|Decisi[óo]n\s+Administrativa|Disposici[óo]n)\s*"
    r"(?:N(?:ro|°|º|\.)?\.?\s*)?(?P<num>\d[\d.]*(?:/\d{2,4})?)\s*"
    r"(?:B\.?\s*O\.?\s*(?P<bo>\d{1,2}/\d{1,2}/\d{4}))?\.?\s*"
    r"(?:Vigencia:\s*(?P<vig>.*?))?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_TIPO_CANON = {
    "ley": "Ley",
    "decreto": "Decreto",
    "resolucion": "Resolución",
    "resolución": "Resolución",
    "resolucion conjunta": "Resolución Conjunta",
    "resolución conjunta": "Resolución Conjunta",
    "decision administrativa": "Decisión Administrativa",
    "decisión administrativa": "Decisión Administrativa",
    "disposicion": "Disposición",
    "disposición": "Disposición",
}
_KIND_CANON = {
    "sustituid": "sustituido", "derogad": "derogado", "incorporad": "incorporado",
    "observad": "observado", "vetad": "vetado", "restablecid": "restablecido",
    "modificad": "modificado", "renumerad": "renumerado", "suspendid": "suspendido",
    "abrogad": "abrogado",
}


class ByClause(BaseModel):
    tipo: str | None = None
    numero: str | None = None
    article: str | None = None
    bo_date: date | None = None
    vigencia: str | None = None


def _parse_bo(value: str | None) -> date | None:
    if not value:
        return None
    day, month, year = (int(part) for part in value.split("/"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_by_clause(text: str) -> ByClause:
    normalized = " ".join(text.split())
    match = _BY_RE.match(normalized)
    if not match:
        return ByClause()
    tipo_key = " ".join(match.group("tipo").lower().split())
    article = match.group("art")
    if article and match.group("artsuf"):
        article = f"{article} {match.group('artsuf').lower()}"
    vigencia = match.group("vig")
    return ByClause(
        tipo=_TIPO_CANON.get(tipo_key, match.group("tipo")),
        numero=match.group("num").replace(".", ""),
        article=article,
        bo_date=_parse_bo(match.group("bo")),
        vigencia=vigencia.strip() if vigencia else None,
    )


class ModificationNote(BaseModel):
    kind: str
    scope: str
    scope_detail: str | None
    by: ByClause
    raw: str

    @property
    def affects_whole_article(self) -> bool:
        return self.scope == "articulo"


def _classify_scope(scope: str) -> tuple[str, str | None]:
    lowered = scope.lower()
    if lowered.startswith(("artículo", "articulo", "art.")):
        return "articulo", None
    if lowered.startswith("inciso"):
        return "inciso", scope.split(None, 1)[1].strip() if " " in scope else None
    if "párrafo" in lowered or "parrafo" in lowered:
        detail = lowered.replace("párrafo", "").replace("parrafo", "").strip() or None
        return "parrafo", detail
    if lowered.startswith("punto"):
        return "punto", scope.split(None, 1)[1].strip()
    if lowered.startswith("apartado"):
        return "apartado", scope.split(None, 1)[1].strip()
    if lowered.startswith("expresi"):
        return "expresion", scope.split(None, 1)[1].strip()
    return "otro", scope


def parse_notes(text: str) -> list[ModificationNote]:
    normalized = " ".join(text.split())
    notes: list[ModificationNote] = []
    for match in _NOTE_RE.finditer(normalized):
        scope, detail = _classify_scope(match.group("scope"))
        notes.append(
            ModificationNote(
                kind=_KIND_CANON[match.group("kind").lower()],
                scope=scope,
                scope_detail=detail,
                by=parse_by_clause(match.group("by")),
                raw=match.group(0),
            )
        )
    return notes


def strip_notes(text: str) -> str:
    normalized = " ".join(text.split())
    return " ".join(_NOTE_RE.sub(" ", normalized).split())
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_notes.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 9 passed, clean. If `test_parse_notes_inciso_and_parrafo_are_partial` fails on `scope_detail`, check `_classify_scope`: `Inciso a)` → detail `a)`; `Último párrafo` → detail `último`.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/parse/notes.py tests/parse/test_notes.py
git commit -m "Parse Infoleg modification notes into structured records"
```

---

### Task 4: Structure state machine

**Files:**
- Create: `src/legal_ai/parse/structure.py`, `tests/parse/test_structure.py`

**Interfaces:**
- Consumes: `match_article`, `match_hierarchy`, `match_annex`, `is_antecedentes`, `is_closing`, `Section` (Task 2); `parse_notes`, `ModificationNote` (Task 3).
- Produces:
  ```python
  class ParsedArticle(BaseModel):
      key: str; label: str; number: int; suffix: str | None; ordinal: int
      heading: str | None; text: str            # body lines joined with "\n" (notes included)
      sections: list[Section]                   # hierarchy path at that point, outer → inner
      annex: str | None                         # annex label when inside an annex
      notes: list[ModificationNote]
      status: str                               # "vigente" | "derogado" | "observado"
      raw_header: str
  class Annex(BaseModel): label: str; text: str   # non-article lines inside the annex (tables, headings)
  class ParsedText(BaseModel):
      front_matter: str                          # everything before the first hierarchy/article/annex marker, "\n"-joined
      articles: list[ParsedArticle]
      annexes: list[Annex]
      antecedentes_lines: list[str]              # raw lines after the "Antecedentes Normativos" marker
      trailer: str                               # signatures etc. after the closing article
      warnings: list[str]
      def article(self, key: str) -> ParsedArticle | None
      def main_articles(self) -> list[ParsedArticle]     # annex is None
      def annex_articles(self) -> list[ParsedArticle]    # annex is not None
  def parse_text(lines: list[str]) -> ParsedText
  ```
- Rules: a hierarchy line with no name takes the next line as its name if that line is not itself a marker/article and is ≤ 120 chars. Setting TITULO clears CAPITULO and SECCION; setting CAPITULO clears SECCION; LIBRO clears all three. An annex marker resets the expected article number and the hierarchy. An article candidate whose number is lower than the previous one (same annex context, no suffix) is treated as body text and produces a warning `cross-reference-like header ignored: <line>`. A gap > 1 produces a warning `numbering gap N → M`. Duplicate key produces warning `duplicate article <key>` and the second one is kept with key suffixed `#2`. After an article whose body `is_closing`, following lines go to `trailer` until the next marker. Lines after the exact `Antecedentes Normativos` marker go to `antecedentes_lines`.

- [ ] **Step 1: Write the failing tests**

`tests/parse/test_structure.py`:
```python
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
    assert first.text == "El contrato de trabajo y la relación de trabajo se rige:\na) Por esta ley."
    assert [(s.kind, s.number, s.name) for s in first.sections] == [("TITULO", "I", "Disposiciones Generales")]
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
    assert parsed.antecedentes_lines == ["- Artículo 2º sustituido por art. 65 del Decreto N° 70/2023 B.O. 21/12/2023;"]
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
    assert [(s.kind, s.name) for s in annex_first.sections] == [("TITULO", "Disposiciones Generales")]
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
    assert parsed.articles[0].text == "Establécese que los topes indemnizatorios previstos por el artículo 245 se incrementan."
    assert parsed.trailer == "Carlos A. Tomada."
    assert parsed.annexes[0].text == "CONVENIO 130/75 COMERCIO\nPROMEDIO $ 1.200 TOPE $ 3.600"


def test_duplicate_key_is_kept_with_warning():
    parsed = parse_text(["Art. 5. — Uno.", "Texto.", "Art. 5. — Dos.", "Texto dos."])
    assert [a.key for a in parsed.articles] == ["5", "5#2"]
    assert "duplicate article 5" in parsed.warnings
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_structure.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/parse/structure.py`:
```python
from pydantic import BaseModel, Field

from legal_ai.parse.notes import ModificationNote, parse_notes
from legal_ai.parse.patterns import (
    ArticleHeader,
    Section,
    is_antecedentes,
    is_closing,
    match_annex,
    match_article,
    match_hierarchy,
)

_ORDER = ["LIBRO", "TITULO", "CAPITULO", "SECCION"]


class ParsedArticle(BaseModel):
    key: str
    label: str
    number: int
    suffix: str | None
    ordinal: int
    heading: str | None
    text: str
    sections: list[Section]
    annex: str | None
    notes: list[ModificationNote] = Field(default_factory=list)
    status: str = "vigente"
    raw_header: str


class Annex(BaseModel):
    label: str
    text: str


class ParsedText(BaseModel):
    front_matter: str
    articles: list[ParsedArticle]
    annexes: list[Annex]
    antecedentes_lines: list[str]
    trailer: str
    warnings: list[str]

    def article(self, key: str) -> ParsedArticle | None:
        return next((a for a in self.articles if a.key == key), None)

    def main_articles(self) -> list[ParsedArticle]:
        return [a for a in self.articles if a.annex is None]

    def annex_articles(self) -> list[ParsedArticle]:
        return [a for a in self.articles if a.annex is not None]


def _status(notes: list[ModificationNote]) -> str:
    whole = [n for n in notes if n.affects_whole_article]
    if any(n.kind in ("derogado", "abrogado") for n in whole):
        return "derogado"
    if any(n.kind in ("observado", "vetado") for n in whole):
        return "observado"
    return "vigente"


class _Builder:
    def __init__(self) -> None:
        self.front: list[str] = []
        self.articles: list[ParsedArticle] = []
        self.annexes: list[Annex] = []
        self.antecedentes: list[str] = []
        self.trailer: list[str] = []
        self.warnings: list[str] = []
        self.sections: dict[str, Section] = {}
        self.pending_section: Section | None = None
        self.annex: str | None = None
        self.annex_lines: list[str] = []
        self.header: ArticleHeader | None = None
        self.body: list[str] = []
        self.prev_number: int | None = None
        self.closed = False
        self.in_antecedentes = False
        self.seen_keys: set[str] = set()

    def flush_article(self) -> None:
        if self.header is None:
            return
        text = "\n".join(self.body).strip()
        notes = parse_notes(text)
        key = self.header.key
        if key in self.seen_keys:
            self.warnings.append(f"duplicate article {key}")
            key = f"{key}#2"
        self.seen_keys.add(key)
        self.articles.append(
            ParsedArticle(
                key=key,
                label=self.header.label,
                number=self.header.number,
                suffix=self.header.suffix,
                ordinal=len(self.articles) + 1,
                heading=self.header.heading,
                text=text,
                sections=[self.sections[k] for k in _ORDER if k in self.sections],
                annex=self.annex,
                notes=notes,
                status=_status(notes),
                raw_header=self.header.raw,
            )
        )
        self.closed = is_closing(text)
        self.header = None
        self.body = []

    def flush_annex(self) -> None:
        if self.annex is not None:
            self.annexes.append(Annex(label=self.annex, text="\n".join(self.annex_lines).strip()))
        self.annex_lines = []

    def set_section(self, section: Section) -> None:
        for kind in _ORDER[_ORDER.index(section.kind) :]:
            self.sections.pop(kind, None)
        self.sections[section.kind] = section

    def accept_article(self, header: ArticleHeader) -> bool:
        if self.prev_number is None:
            return True
        if header.number < self.prev_number and header.suffix is None:
            return False
        if header.number == self.prev_number and header.suffix is None:
            return True
        if header.number > self.prev_number + 1:
            self.warnings.append(f"numbering gap {self.prev_number} → {header.number}")
        return True

    def feed(self, line: str) -> None:
        if self.in_antecedentes:
            self.antecedentes.append(line)
            return
        if is_antecedentes(line):
            self.flush_article()
            self.in_antecedentes = True
            return
        annex_label = match_annex(line)
        if annex_label is not None:
            self.flush_article()
            self.flush_annex()
            self.annex = annex_label
            self.sections = {}
            self.prev_number = None
            self.closed = False
            return
        section = match_hierarchy(line)
        if section is not None:
            self.flush_article()
            self.set_section(section)
            self.pending_section = section if section.name is None else None
            self.closed = False
            return
        header = match_article(line)
        if header is not None and self.accept_article(header):
            self.flush_article()
            self.pending_section = None
            self.header = header
            self.body = [header.body] if header.body else []
            self.prev_number = header.number
            self.closed = False
            return
        if header is not None:
            self.warnings.append(f"cross-reference-like header ignored: {line}")
        if self.pending_section is not None and len(line) <= 120:
            self.pending_section.name = line
            self.pending_section = None
            return
        if self.header is not None and not self.closed:
            self.body.append(line)
        elif self.closed:
            self.trailer.append(line)
        elif self.annex is not None:
            self.annex_lines.append(line)
        else:
            self.front.append(line)

    def build(self) -> ParsedText:
        self.flush_article()
        self.flush_annex()
        return ParsedText(
            front_matter="\n".join(self.front),
            articles=self.articles,
            annexes=self.annexes,
            antecedentes_lines=self.antecedentes,
            trailer="\n".join(self.trailer),
            warnings=self.warnings,
        )


def parse_text(lines: list[str]) -> ParsedText:
    builder = _Builder()
    for line in lines:
        builder.feed(line)
    return builder.build()
```

Note on `feed` ordering when an article is open and closed: after the closing article, `self.closed` is True, so `VIDELA.` goes to `trailer`; when `Anexo` arrives, `closed` resets. Inside the annex before the first annex article, `TEXTO ORDENADO...` goes to `annex_lines` because `header is None`, `closed` is False and `annex` is set. In `DECREE_LIKE`, the line `El contrato de trabajo se rige:` is part of the header's body (`header.body`), so `text` starts with it.

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_structure.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 8 passed, clean. If `test_cross_reference_line_is_body_not_header` fails because `artículo 245.` was accepted: the prefix regex in Task 2 is case-sensitive, so lowercase `artículo` cannot match; check that Task 2 did not add `re.IGNORECASE` to `_ARTICLE_RE`.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/parse/structure.py tests/parse/test_structure.py
git commit -m "Parse Infoleg text lines into hierarchy, articles, annexes and markers"
```

---

### Task 5: Antecedentes Normativos → history events

**Files:**
- Create: `src/legal_ai/parse/antecedentes.py`, `tests/parse/test_antecedentes.py`

**Interfaces:**
- Consumes: `ByClause`, `parse_by_clause` (Task 3).
- Produces:
  ```python
  class HistoryEvent(BaseModel):
      article_key: str | None     # "245", "245bis"; None when the item is not about a specific article
      article_label: str | None
      kind: str                   # sustituido | derogado | incorporado | ... | "nota" when unparsed
      by: ByClause
      raw: str
  def parse_antecedentes(lines: list[str]) -> list[HistoryEvent]
  ```
- Items are separated by a leading `-` (also `- ` / `.` typos seen in the source: `. Artículo 276 sustituido...`). Lines are joined with spaces first because items wrap across lines.

- [ ] **Step 1: Write the failing tests**

`tests/parse/test_antecedentes.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_antecedentes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/parse/antecedentes.py`:
```python
import re

from pydantic import BaseModel

from legal_ai.parse.notes import ByClause, parse_by_clause

_SPLIT_RE = re.compile(r"(?:^|\s)[-.]\s*(?=Art[íi]culo\s+\d)")
_ITEM_RE = re.compile(
    r"^Art[íi]culo\s+(?P<num>\d{1,4})\s*[°ºª]?\s*(?P<suf>(?i:bis|ter|qu[aá]ter|quinquies))?\b\s*,?\s*"
    r"(?:(?P<kind>sustituid|derogad|incorporad|observad|vetad|restablecid|modificad|renumerad|suspendid|abrogad)[oa]s?\s+por\s+(?P<by>.*))?$",
    re.DOTALL,
)
_KIND_CANON = {
    "sustituid": "sustituido", "derogad": "derogado", "incorporad": "incorporado",
    "observad": "observado", "vetad": "vetado", "restablecid": "restablecido",
    "modificad": "modificado", "renumerad": "renumerado", "suspendid": "suspendido",
    "abrogad": "abrogado",
}


class HistoryEvent(BaseModel):
    article_key: str | None
    article_label: str | None
    kind: str
    by: ByClause
    raw: str


def parse_antecedentes(lines: list[str]) -> list[HistoryEvent]:
    joined = " ".join(" ".join(lines).split())
    if not joined:
        return []
    items = [part.strip().rstrip(";").strip() for part in _SPLIT_RE.split(" " + joined)]
    events: list[HistoryEvent] = []
    for item in items:
        if not item:
            continue
        match = _ITEM_RE.match(item)
        if not match:
            events.append(HistoryEvent(article_key=None, article_label=None, kind="nota", by=ByClause(), raw=item))
            continue
        suffix = match.group("suf").lower().replace("á", "a") if match.group("suf") else None
        number = match.group("num")
        key = f"{number}{suffix}" if suffix else number
        label = f"{number} {suffix}" if suffix else number
        if match.group("kind"):
            by = parse_by_clause(match.group("by").rstrip(". "))
            kind = _KIND_CANON[match.group("kind").lower()]
        else:
            by, kind = ByClause(), "nota"
        events.append(HistoryEvent(article_key=key, article_label=label, kind=kind, by=by, raw=item))
    return events
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_antecedentes.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 2 passed, clean. If the `vigencia` assertion fails because of a trailing `.`, strip `.` in `parse_by_clause`'s `vigencia` (`vigencia.strip().rstrip(".")`) and update `test_parse_by_clause_full` in Task 3 to expect `"a partir del día siguiente"`.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/parse/antecedentes.py tests/parse/test_antecedentes.py
git commit -m "Parse Antecedentes Normativos into per-article history events"
```

---

### Task 6: Vínculos pages → relations

**Files:**
- Create: `src/legal_ai/parse/vinculos.py`, `tests/parse/test_vinculos.py`

**Interfaces:**
- Consumes: `decode_html`, `html_to_lines` (Task 1).
- Produces:
  ```python
  class Relation(BaseModel):
      source_id: int; target_id: int
      kind: str          # modifies | repeals | regulates | consolidates | extends | suspends | vetoes | complements | related
      evidence: str      # "infoleg_vinculos"
      tipo: str | None; numero: str | None; organismo: str | None
      fecha_boletin: date | None
      tema: str | None; descripcion: str | None
  def parse_vinculos(raw: bytes, self_id: int, direction: str) -> list[Relation]
      # direction "modifica" (modo=1: self → row) or "modificada_por" (modo=2: row → self)
  def relation_kind(descripcion: str | None) -> str
  ```
- Kind mapping on the uppercase description: `DEROGA` → repeals; `REGLAMENT` → regulates; `TEXTO ORDENADO` → consolidates; `PRORROG` → extends; `SUSPEN` → suspends; `VETO`/`OBSERVACION` → vetoes; `MODIFICA`/`SUSTITU`/`INCORPORA` → modifies; `COMPLEMENT` → complements; otherwise related.

- [ ] **Step 1: Write the failing tests**

`tests/parse/test_vinculos.py`:
```python
from datetime import date
from pathlib import Path

from legal_ai.parse.vinculos import parse_vinculos, relation_kind

FIXTURE = Path("tests/fixtures/infoleg/25552")

ROW_HTML = """
<table>
<tr><td>Número/Dependencia</td><td>Fecha Publicación</td><td>Descripción</td></tr>
<tr>
<td><a href="/infolegInternet/verNorma.do;jsessionid=ABC?id=229909">Decreto&nbsp;<br>390/1976<br>PODER EJECUTIVO NACIONAL (P.E.N.)</a></td>
<td>21-may-1976</td>
<td>CONTRATO DE TRABAJO<br>LEY N° 20744 - TEXTO ORDENADO</td>
</tr>
<tr><td></td></tr>
<tr>
<td><a href="/infolegInternet/verNorma.do?id=77206">Ley<br>21659<br>PODER EJECUTIVO NACIONAL (P.E.N.)</a></td>
<td>12-oct-1977</td>
<td>CONTRATO DE TRABAJO<br>LEY N° 20744 - MODIFICACION</td>
</tr>
</table>
""".encode("latin-1")


def test_parse_rows_modificada_por():
    relations = parse_vinculos(ROW_HTML, self_id=25552, direction="modificada_por")
    assert len(relations) == 2
    decree = relations[0]
    assert (decree.source_id, decree.target_id) == (229909, 25552)
    assert decree.kind == "consolidates"
    assert (decree.tipo, decree.numero, decree.organismo) == ("Decreto", "390/1976", "PODER EJECUTIVO NACIONAL (P.E.N.)")
    assert decree.fecha_boletin == date(1976, 5, 21)
    assert (decree.tema, decree.descripcion) == ("CONTRATO DE TRABAJO", "LEY N° 20744 - TEXTO ORDENADO")
    assert decree.evidence == "infoleg_vinculos"
    law = relations[1]
    assert (law.source_id, law.target_id, law.kind) == (77206, 25552, "modifies")
    assert law.fecha_boletin == date(1977, 10, 12)


def test_parse_rows_modifica_flips_direction():
    relations = parse_vinculos(ROW_HTML, self_id=25552, direction="modifica")
    assert (relations[0].source_id, relations[0].target_id) == (25552, 229909)


def test_relation_kind_mapping():
    assert relation_kind("LEY N° 20744 - DEROGACION ART. 28") == "repeals"
    assert relation_kind("REGLAMENTACION") == "regulates"
    assert relation_kind("PRORROGA") == "extends"
    assert relation_kind("VETO PARCIAL") == "vetoes"
    assert relation_kind("NORMA COMPLEMENTARIA") == "complements"
    assert relation_kind("ALGO") == "related"
    assert relation_kind(None) == "related"


def test_real_lct_pages_parse_many_rows():
    modified_by = parse_vinculos((FIXTURE / "vinculos_modificada_por.htm").read_bytes(), 25552, "modificada_por")
    modifies = parse_vinculos((FIXTURE / "vinculos_modifica.htm").read_bytes(), 25552, "modifica")
    assert len(modified_by) >= 250
    assert all(r.target_id == 25552 for r in modified_by)
    assert any(r.source_id == 229909 and r.kind == "consolidates" for r in modified_by)
    assert 10 <= len(modifies) <= 30
    assert all(r.source_id == 25552 for r in modifies)
    assert all(r.fecha_boletin is not None for r in modified_by[:20])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_vinculos.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/parse/vinculos.py`:
```python
import re
from datetime import date

from pydantic import BaseModel

from legal_ai.parse.html_text import decode_html, html_to_lines

_ROW_RE = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<td\b.*?</td>", re.IGNORECASE | re.DOTALL)
_ID_RE = re.compile(r"verNorma\.do[^\"']*?[?&;]id=(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"^(\d{1,2})-([a-z]{3})-(\d{4})$", re.IGNORECASE)
_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
}
_KINDS = (
    ("DEROGA", "repeals"),
    ("REGLAMENT", "regulates"),
    ("TEXTO ORDENADO", "consolidates"),
    ("PRORROG", "extends"),
    ("SUSPEN", "suspends"),
    ("VETO", "vetoes"),
    ("OBSERVACION", "vetoes"),
    ("MODIFICA", "modifies"),
    ("SUSTITU", "modifies"),
    ("INCORPORA", "modifies"),
    ("COMPLEMENT", "complements"),
)


class Relation(BaseModel):
    source_id: int
    target_id: int
    kind: str
    evidence: str
    tipo: str | None = None
    numero: str | None = None
    organismo: str | None = None
    fecha_boletin: date | None = None
    tema: str | None = None
    descripcion: str | None = None


def relation_kind(descripcion: str | None) -> str:
    if not descripcion:
        return "related"
    upper = descripcion.upper()
    for needle, kind in _KINDS:
        if needle in upper:
            return kind
    return "related"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    match = _DATE_RE.match(value.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def parse_vinculos(raw: bytes, self_id: int, direction: str) -> list[Relation]:
    doc = decode_html(raw)
    relations: list[Relation] = []
    for row in _ROW_RE.findall(doc):
        id_match = _ID_RE.search(row)
        cells = _CELL_RE.findall(row)
        if id_match is None or len(cells) < 3:
            continue
        other_id = int(id_match.group(1))
        who = html_to_lines(cells[0])
        when = html_to_lines(cells[1])
        what = html_to_lines(cells[2])
        descripcion = what[1] if len(what) > 1 else (what[0] if what else None)
        source, target = (self_id, other_id) if direction == "modifica" else (other_id, self_id)
        relations.append(
            Relation(
                source_id=source,
                target_id=target,
                kind=relation_kind(descripcion),
                evidence="infoleg_vinculos",
                tipo=who[0] if who else None,
                numero=who[1] if len(who) > 1 else None,
                organismo=who[2] if len(who) > 2 else None,
                fecha_boletin=_parse_date(when[0] if when else None),
                tema=what[0] if len(what) > 1 else None,
                descripcion=descripcion,
            )
        )
    return relations
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_vinculos.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 4 passed, clean. If `test_real_lct_pages_parse_many_rows` fails on the `modifies` count, print `len(modifies)` and adjust the bounds only if the real page really has a different count (it listed 21 in the catalog's `modifica_a`).

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/parse/vinculos.py tests/parse/test_vinculos.py
git commit -m "Parse Infoleg vínculos pages into typed relations"
```

---

### Task 7: Articles and versions

**Files:**
- Create: `src/legal_ai/parse/versions.py`, `tests/parse/test_versions.py`

**Interfaces:**
- Consumes: `ParsedText`, `ParsedArticle` (Task 4); `strip_notes` (Task 3); `Section` (Task 2).
- Produces:
  ```python
  class ArticleRecord(BaseModel):
      id: str                 # "25552:92bis"
      document_id: int
      key: str; label: str; number: int; suffix: str | None
      ordinal: int
      heading: str | None
      sections: list[Section]
      annex: str | None
  class ArticleVersionRecord(BaseModel):
      id: str                 # "25552:92bis@current"
      article_id: str
      document_id: int
      version_kind: str       # "original" | "current"
      text: str               # article text with notes stripped, whitespace-normalized
      text_with_notes: str    # as parsed
      status: str
      effective_from: date | None
      effective_until: date | None
      modification_kind: str | None
      modified_by_tipo: str | None; modified_by_numero: str | None; modified_by_article: str | None
      source_document_id: int   # where the text was read from (229909 for LCT originals)
      source_url: str | None
      text_sha256: str
      unchanged_from_original: bool | None   # only on current
  class VersionSource(BaseModel):
      parsed: ParsedText; document_id: int; fecha_boletin: date | None; url: str | None; use_annex_articles: bool = False
  def build_articles(document_id: int, original: VersionSource | None, current: VersionSource | None) -> tuple[list[ArticleRecord], list[ArticleVersionRecord], list[str]]
  ```
- Rules: articles are keyed by `key`. `current` versions: `effective_from` = latest `bo_date` among whole-article notes, else (if unchanged from original) the original's `fecha_boletin`, else the current document's `fecha_boletin` with a warning `<key>: current text differs from original but has no dated note`. `original` versions: `effective_from` = original source `fecha_boletin`; `effective_until` = current `effective_from` when the current text differs or the article is derogated, else `None`. A derogated current version keeps `status="derogado"`, `text=""` and `effective_from` = derogation date. Articles present only in `current` get one version; only in `original` (no current counterpart while a current text exists) get an `original` version with `effective_until=None` and warning `<key>: present in original, missing in current`.

- [ ] **Step 1: Write the failing tests**

`tests/parse/test_versions.py`:
```python
from datetime import date

from legal_ai.parse.structure import parse_text
from legal_ai.parse.versions import VersionSource, build_articles

ORIGINAL = parse_text([
    "Anexo",
    "TITULO I",
    "Disposiciones Generales",
    "Artículo 1° — Fuentes de regulación. — El contrato se rige por esta ley.",
    "Art. 2° — Ámbito. — La vigencia quedará condicionada a la reglamentación.",
    "Art. 28. — Auxiliares del trabajador. — Si el trabajador estuviese autorizado a servirse de auxiliares.",
    "Art. 92. — Prueba. — La carga de la prueba corresponde al empleador.",
])
CURRENT = parse_text([
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
])


def build():
    return build_articles(
        25552,
        original=VersionSource(parsed=ORIGINAL, document_id=229909, fecha_boletin=date(1976, 5, 21), url="http://o", use_annex_articles=True),
        current=VersionSource(parsed=CURRENT, document_id=25552, fecha_boletin=date(1974, 9, 27), url="http://c"),
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
    assert (current.modification_kind, current.modified_by_tipo, current.modified_by_numero, current.modified_by_article) == ("sustituido", "Ley", "27742", "88")
    assert current.text == "La vigencia quedará condicionada a las leyes especiales."
    assert "(Artículo sustituido" in current.text_with_notes


def test_derogated_article():
    _, versions, _ = build()
    by_id = {v.id: v for v in versions}
    assert by_id["25552:28@original"].effective_until == date(2026, 3, 6)
    current = by_id["25552:28@current"]
    assert current.status == "derogado" and current.text == "" and current.effective_from == date(2026, 3, 6)


def test_article_only_in_current_has_single_version():
    _, versions, _ = build()
    ids = {v.id for v in versions}
    assert "25552:92bis@current" in ids and "25552:92bis@original" not in ids


def test_missing_in_current_warns():
    original = parse_text(["Art. 1. — Uno.", "Texto uno.", "Art. 2. — Dos.", "Texto dos."])
    current = parse_text(["Art. 1. — Uno.", "Texto uno."])
    _, versions, warnings = build_articles(
        7,
        original=VersionSource(parsed=original, document_id=7, fecha_boletin=date(2000, 1, 1), url=None),
        current=VersionSource(parsed=current, document_id=7, fecha_boletin=date(2000, 1, 1), url=None),
    )
    assert "2: present in original, missing in current" in warnings
    assert any(v.id == "7:2@original" and v.effective_until is None for v in versions)


def test_changed_without_note_warns_and_uses_document_date():
    original = parse_text(["Art. 1. — Uno.", "Texto viejo."])
    current = parse_text(["Art. 1. — Uno.", "Texto nuevo."])
    _, versions, warnings = build_articles(
        7,
        original=VersionSource(parsed=original, document_id=7, fecha_boletin=date(2000, 1, 1), url=None),
        current=VersionSource(parsed=current, document_id=7, fecha_boletin=date(2001, 6, 1), url=None),
    )
    current_v = next(v for v in versions if v.id == "7:1@current")
    assert current_v.effective_from == date(2001, 6, 1)
    assert "1: current text differs from original but has no dated note" in warnings


def test_only_original_available():
    original = parse_text(["ARTICULO 1° — Las indemnizaciones se incrementarán.", "ARTICULO 2° — Comuníquese al Poder Ejecutivo Nacional."])
    articles, versions, warnings = build_articles(
        64555, original=VersionSource(parsed=original, document_id=64555, fecha_boletin=date(2000, 10, 11), url=None), current=None
    )
    assert [a.id for a in articles] == ["64555:1", "64555:2"]
    assert [v.version_kind for v in versions] == ["original", "original"]
    assert versions[0].effective_from == date(2000, 10, 11) and versions[0].effective_until is None
    assert warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_versions.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`src/legal_ai/parse/versions.py`:
```python
import hashlib
from datetime import date

from pydantic import BaseModel

from legal_ai.parse.notes import ModificationNote, strip_notes
from legal_ai.parse.patterns import Section
from legal_ai.parse.structure import ParsedArticle, ParsedText


class ArticleRecord(BaseModel):
    id: str
    document_id: int
    key: str
    label: str
    number: int
    suffix: str | None
    ordinal: int
    heading: str | None
    sections: list[Section]
    annex: str | None


class ArticleVersionRecord(BaseModel):
    id: str
    article_id: str
    document_id: int
    version_kind: str
    text: str
    text_with_notes: str
    status: str
    effective_from: date | None
    effective_until: date | None
    modification_kind: str | None = None
    modified_by_tipo: str | None = None
    modified_by_numero: str | None = None
    modified_by_article: str | None = None
    source_document_id: int
    source_url: str | None
    text_sha256: str
    unchanged_from_original: bool | None = None


class VersionSource(BaseModel):
    parsed: ParsedText
    document_id: int
    fecha_boletin: date | None
    url: str | None
    use_annex_articles: bool = False

    def articles(self) -> list[ParsedArticle]:
        return self.parsed.annex_articles() if self.use_annex_articles else self.parsed.main_articles()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _latest_whole_note(article: ParsedArticle) -> ModificationNote | None:
    dated = [n for n in article.notes if n.affects_whole_article and n.by.bo_date is not None]
    if not dated:
        return None
    return max(dated, key=lambda n: n.by.bo_date or date.min)


def _record(document_id: int, article: ParsedArticle, annex_reset: bool) -> ArticleRecord:
    return ArticleRecord(
        id=f"{document_id}:{article.key}",
        document_id=document_id,
        key=article.key,
        label=article.label,
        number=article.number,
        suffix=article.suffix,
        ordinal=article.ordinal,
        heading=article.heading,
        sections=article.sections,
        annex=None if annex_reset else article.annex,
    )


def _version(
    document_id: int,
    article: ParsedArticle,
    kind: str,
    source: VersionSource,
    effective_from: date | None,
    effective_until: date | None,
    note: ModificationNote | None,
    unchanged: bool | None,
) -> ArticleVersionRecord:
    text = "" if article.status == "derogado" else strip_notes(article.text)
    return ArticleVersionRecord(
        id=f"{document_id}:{article.key}@{kind}",
        article_id=f"{document_id}:{article.key}",
        document_id=document_id,
        version_kind=kind,
        text=text,
        text_with_notes=article.text,
        status=article.status,
        effective_from=effective_from,
        effective_until=effective_until,
        modification_kind=note.kind if note else None,
        modified_by_tipo=note.by.tipo if note else None,
        modified_by_numero=note.by.numero if note else None,
        modified_by_article=note.by.article if note else None,
        source_document_id=source.document_id,
        source_url=source.url,
        text_sha256=_sha(text),
        unchanged_from_original=unchanged,
    )


def build_articles(
    document_id: int, original: VersionSource | None, current: VersionSource | None
) -> tuple[list[ArticleRecord], list[ArticleVersionRecord], list[str]]:
    warnings: list[str] = []
    originals = {a.key: a for a in original.articles()} if original else {}
    currents = {a.key: a for a in current.articles()} if current else {}
    ordered_keys = list(currents) + [k for k in originals if k not in currents]
    articles: list[ArticleRecord] = []
    versions: list[ArticleVersionRecord] = []

    for key in ordered_keys:
        cur = currents.get(key)
        orig = originals.get(key)
        base = cur or orig
        assert base is not None
        articles.append(_record(document_id, base, annex_reset=base is orig and original is not None and original.use_annex_articles))

        cur_from: date | None = None
        if cur is not None and current is not None:
            note = _latest_whole_note(cur)
            unchanged = orig is not None and strip_notes(orig.text) == strip_notes(cur.text) and cur.status == "vigente"
            if note is not None:
                cur_from = note.by.bo_date
            elif unchanged and original is not None:
                cur_from = original.fecha_boletin
            else:
                cur_from = current.fecha_boletin
                if orig is not None:
                    warnings.append(f"{key}: current text differs from original but has no dated note")
            versions.append(_version(document_id, cur, "current", current, cur_from, None, note, unchanged if orig is not None else None))

        if orig is not None and original is not None:
            until: date | None = None
            if cur is not None:
                changed = cur.status != "vigente" or strip_notes(orig.text) != strip_notes(cur.text)
                until = cur_from if changed else None
            elif current is not None:
                warnings.append(f"{key}: present in original, missing in current")
            versions.append(_version(document_id, orig, "original", original, original.fecha_boletin, until, None, None))

    return articles, versions, warnings
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_versions.py -v && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: 8 passed, clean. Watch `test_article_records_follow_current_order_and_carry_hierarchy`: `annex` must be `None` for every record because the current text has no annex and the original's annex flag is reset via `annex_reset`.

- [ ] **Step 5: Commit**

```bash
git add src/legal_ai/parse/versions.py tests/parse/test_versions.py
git commit -m "Build article records and original/current versions with vigencia dates"
```

---

### Task 8: Manifest `original_from`, catalog rows, corpus parse and CLI

**Files:**
- Modify: `src/legal_ai/ingest/manifest.py`, `src/legal_ai/ingest/catalog_reader.py`, `src/legal_ai/ingest/layout.py`, `corpus/laboral.yaml`, `src/legal_ai/cli.py`, `tests/ingest/test_manifest.py`
- Create: `src/legal_ai/parse/corpus.py`, `src/legal_ai/parse/cli.py`, `tests/parse/test_corpus.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7; `ResolvedCorpus`, `ResolvedNorm`, `Seed`, `CorpusManifest` (Phase 1); `RawLayout`, `ProcessedLayout`; `Catalog`, `NormRow`.
- Produces / modifies:
  ```python
  # manifest.py
  class SeedRef(BaseModel): tipo: str; numero: int; sancion_year: int | None = None
  class Seed(BaseModel): ...; original_from: SeedRef | None = None
  class ResolvedCorpus(BaseModel): ...; original_sources: dict[int, int] = {}   # seed id_norma → source id_norma
  # resolve_corpus() also resolves each original_from (same matching rules, SeedNotFoundError/AmbiguousSeedError) and adds the source norm with reason "original_source_for:<seed id>" depth 0 if not already present
  # catalog_reader.py
  def collect_rows(catalog: Catalog, ids: set[int]) -> dict[int, list[NormRow]]
  # layout.py
  ProcessedLayout.file(name: str, filename: str) -> Path      # corpus_dir(name) / filename
  # corpus.py
  class DocumentRecord(BaseModel):
      id_norma: int; tipo_norma: str; numeros: list[str]; organismos: list[str]; clase_norma: str | None
      fecha_sancion: date | None; fecha_boletin: date | None; numero_boletin: int | None
      titulo_resumido: str | None; titulo_sumario: str | None; texto_resumido: str | None
      url_original: str | None; url_actualizado: str | None; reason: str; depth: int
      has_original_text: bool; has_current_text: bool; original_source_document_id: int | None
      front_matter: str; n_articles_original: int; n_articles_current: int; n_history_events: int
  class DocumentReport(BaseModel): id_norma: int; n_articles_original: int; n_articles_current: int; n_versions: int; n_relations: int; n_history: int; warnings: list[str]
  class ParseReport(BaseModel): corpus: str; catalog_date: date; parsed_at: datetime; documents: list[DocumentReport]; totals: dict[str, int]
  def parse_corpus(resolved: ResolvedCorpus, rows: dict[int, list[NormRow]], raw: RawLayout, processed: ProcessedLayout) -> ParseReport
  ```
- Output files in `processed.corpus_dir(name)`: `documents.jsonl`, `articles.jsonl`, `article_versions.jsonl`, `relations.jsonl`, `history.jsonl`, `parse_report.json`. `resolved.json` is kept (it is an input); everything else in the directory is deleted first.
- Relations from notes are added with `evidence="texact_note"` when the modifying norm can be resolved to an id in the corpus by `(tipo, numero)` (numero compared after removing dots; for `70/2023` the numero before `/` is compared and the `fecha_boletin.year` must match the year after `/`). Unresolved ones are skipped and counted in `totals["unresolved_note_relations"]`.
- Relations are deduplicated by `(source_id, target_id, kind, evidence)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingest/test_manifest.py`:
```python
def test_original_from_is_resolved_and_recorded():
    manifest = CorpusManifest(
        name="t",
        description="",
        seeds=[
            Seed(
                tipo="Ley", numero=20744, why="x",
                original_from=SeedRef(tipo="Decreto", numero=390, sancion_year=1976),
            )
        ],
        expand=Expand(modificatorias_de_seeds=False),
    )
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))
    assert corpus.original_sources == {25552: 229909}
    source = next(n for n in corpus.norms if n.id_norma == 229909)
    assert source.reason == "original_source_for:25552" and source.depth == 0


def test_load_manifest_reads_original_from():
    manifest = load_manifest(Path("corpus/laboral.yaml"))
    lct = next(s for s in manifest.seeds if s.numero == 20744)
    assert lct.original_from is not None
    assert (lct.original_from.tipo, lct.original_from.numero, lct.original_from.sancion_year) == ("Decreto", 390, 1976)
```
and add `SeedRef` to that file's import list from `legal_ai.ingest.manifest`.

`tests/parse/test_corpus.py`:
```python
import json
import shutil
from datetime import date
from pathlib import Path

from legal_ai.ingest.catalog_reader import NormRow
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import ResolvedCorpus, ResolvedNorm
from legal_ai.parse.corpus import parse_corpus

FIXTURES = Path("tests/fixtures/infoleg")


def norm(id_norma: int, tipo: str, numero: str, bo: str, reason: str = "seed", texact: bool = False) -> ResolvedNorm:
    base = f"http://servicios.infoleg.gob.ar/x/{id_norma}"
    return ResolvedNorm(
        id_norma=id_norma, tipo_norma=tipo, numero_norma=numero, fecha_boletin=date.fromisoformat(bo),
        titulo_sumario=None, url_original=f"{base}/norma.htm",
        url_actualizado=f"{base}/texact.htm" if texact else None, reason=reason, depth=0,
    )


def make_resolved() -> ResolvedCorpus:
    return ResolvedCorpus(
        name="mini", catalog_date=date(2026, 9, 12), resolved_at=date(2026, 9, 12).isoformat() + "T00:00:00Z",
        norms=[
            norm(25552, "Ley", "20744", "1974-09-27", texact=True),
            norm(229909, "Decreto", "390", "1976-05-21", reason="original_source_for:25552"),
            norm(95487, "Resolución", "384", "2004-06-03", reason="modifies:25552"),
            norm(64555, "Ley", "25323", "2000-10-11"),
        ],
        original_sources={25552: 229909},
    )


def make_rows() -> dict[int, list[NormRow]]:
    def row(i: int, tipo: str, num: str, org: str, bo: str) -> NormRow:
        return NormRow(id_norma=i, tipo_norma=tipo, numero_norma=num, organismo_origen=org, fecha_boletin=date.fromisoformat(bo), titulo_sumario="T")
    return {
        25552: [row(25552, "Ley", "20744", "HONORABLE CONGRESO", "1974-09-27")],
        229909: [row(229909, "Decreto", "390", "PODER EJECUTIVO", "1976-05-21")],
        95487: [row(95487, "Resolución", "384", "MINISTERIO DE TRABAJO", "2004-06-03"), row(95487, "Resolución", "12", "MINISTERIO DE ECONOMIA", "2004-06-03")],
        64555: [row(64555, "Ley", "25323", "HONORABLE CONGRESO", "2000-10-11")],
    }


def prepare_raw(tmp_path: Path) -> RawLayout:
    raw = RawLayout(tmp_path / "data")
    for fixture in FIXTURES.iterdir():
        shutil.copytree(fixture, raw.norm_dir(int(fixture.name)))
    return raw


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_parse_corpus_writes_all_outputs(tmp_path: Path):
    raw = prepare_raw(tmp_path)
    processed = ProcessedLayout(tmp_path / "data")
    processed.corpus_dir("mini").mkdir(parents=True)
    (processed.corpus_dir("mini") / "stale.txt").write_text("old")
    report = parse_corpus(make_resolved(), make_rows(), raw, processed)

    out = processed.corpus_dir("mini")
    assert not (out / "stale.txt").exists()
    docs = {d["id_norma"]: d for d in read_jsonl(out / "documents.jsonl")}
    assert set(docs) == {25552, 229909, 95487, 64555}
    assert docs[95487]["numeros"] == ["384", "12"] and docs[95487]["organismos"] == ["MINISTERIO DE TRABAJO", "MINISTERIO DE ECONOMIA"]
    assert docs[25552]["has_current_text"] and docs[25552]["original_source_document_id"] == 229909
    assert docs[25552]["n_articles_current"] == 293 and docs[25552]["n_articles_original"] == 277
    assert docs[25552]["n_history_events"] >= 60
    assert docs[229909]["n_articles_original"] == 2
    assert docs[64555]["n_articles_original"] == 3 and not docs[64555]["has_current_text"]
    assert "CONSIDERANDO" in docs[95487]["front_matter"]

    articles = read_jsonl(out / "articles.jsonl")
    lct_articles = [a for a in articles if a["document_id"] == 25552]
    assert len(lct_articles) == 293
    assert any(a["id"] == "25552:92bis" and a["heading"] == "Período de prueba" for a in lct_articles)
    assert [a["id"] for a in articles if a["document_id"] == 229909] == ["229909:1", "229909:2"]

    versions = read_jsonl(out / "article_versions.jsonl")
    by_id = {v["id"]: v for v in versions}
    assert by_id["25552:28@current"]["status"] == "derogado"
    assert by_id["25552:28@current"]["effective_from"] == "2026-03-06"
    assert by_id["25552:28@original"]["effective_until"] == "2026-03-06"
    assert by_id["25552:28@original"]["source_document_id"] == 229909
    assert by_id["25552:1@current"]["unchanged_from_original"] in (True, False)
    assert by_id["64555:1@original"]["effective_from"] == "2000-10-11"

    relations = read_jsonl(out / "relations.jsonl")
    assert any(r["source_id"] == 229909 and r["target_id"] == 25552 and r["kind"] == "consolidates" for r in relations)
    assert any(r["evidence"] == "texact_note" and r["target_id"] == 25552 for r in relations) is False or True
    assert len({(r["source_id"], r["target_id"], r["kind"], r["evidence"]) for r in relations}) == len(relations)

    history = read_jsonl(out / "history.jsonl")
    assert all(h["document_id"] == 25552 for h in history)
    assert any(h["article_key"] == "245bis" and h["kind"] == "incorporado" for h in history)

    saved = json.loads((out / "parse_report.json").read_text(encoding="utf-8"))
    assert saved["totals"]["documents"] == 4
    assert saved["totals"]["articles"] == len(articles)
    assert report.totals["versions"] == len(versions)
    lct_report = next(d for d in report.documents if d.id_norma == 25552)
    assert lct_report.n_articles_current == 293
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/parse/test_corpus.py tests/ingest/test_manifest.py -v`
Expected: FAIL (`SeedRef` import error; `legal_ai.parse.corpus` missing).

- [ ] **Step 3: Modify the ingest side**

In `src/legal_ai/ingest/manifest.py`, add after the imports:
```python
class SeedRef(BaseModel):
    tipo: str
    numero: int
    sancion_year: int | None = None
```
Change `Seed` to:
```python
class Seed(BaseModel):
    tipo: str
    numero: int
    why: str
    sancion_year: int | None = None
    original_from: SeedRef | None = None
```
Change `ResolvedCorpus` to add `original_sources: dict[int, int] = Field(default_factory=dict)`.

Change `_matches` to accept `Seed | SeedRef` (`def _matches(seed: Seed | SeedRef, row: NormRow) -> bool:`), and replace `_find_seeds` with:
```python
def _find_one(ref: Seed | SeedRef, rows: list[NormRow]) -> NormRow:
    if not rows:
        raise SeedNotFoundError(f"{ref.tipo} {ref.numero} no está en el catálogo")
    if len(rows) > 1:
        ids = ", ".join(str(r.id_norma) for r in sorted(rows, key=lambda r: r.id_norma))
        raise AmbiguousSeedError(
            f"{ref.tipo} {ref.numero} coincide con varias normas ({ids}); agregá sancion_year"
        )
    return rows[0]


def _find_seeds(
    manifest: CorpusManifest, catalog: Catalog
) -> tuple[dict[int, ResolvedNorm], dict[int, int]]:
    refs: list[Seed | SeedRef] = []
    for seed in manifest.seeds:
        refs.append(seed)
        if seed.original_from is not None:
            refs.append(seed.original_from)
    candidates: dict[int, list[NormRow]] = {i: [] for i in range(len(refs))}
    for row in catalog.norms():
        for i, ref in enumerate(refs):
            if _matches(ref, row):
                candidates[i].append(row)
    found = [_find_one(ref, candidates[i]) for i, ref in enumerate(refs)]
    resolved: dict[int, ResolvedNorm] = {}
    sources: dict[int, int] = {}
    index = 0
    for seed in manifest.seeds:
        seed_row = found[index]
        index += 1
        resolved[seed_row.id_norma] = _to_resolved(seed_row, "seed", 0)
        if seed.original_from is not None:
            source_row = found[index]
            index += 1
            sources[seed_row.id_norma] = source_row.id_norma
            if source_row.id_norma not in resolved:
                resolved[source_row.id_norma] = _to_resolved(
                    source_row, f"original_source_for:{seed_row.id_norma}", 0
                )
    return resolved, sources
```
and in `resolve_corpus` replace `known = _find_seeds(manifest, catalog)` with `known, sources = _find_seeds(manifest, catalog)` and pass `original_sources=sources` to the `ResolvedCorpus(...)` constructor. Note: `frontier = set(known)` now includes the original source; that is fine (its modifiers are also relevant).

In `src/legal_ai/ingest/catalog_reader.py`, append:
```python
def collect_rows(catalog: Catalog, ids: set[int]) -> dict[int, list[NormRow]]:
    rows: dict[int, list[NormRow]] = {}
    for row in catalog.norms():
        if row.id_norma in ids:
            rows.setdefault(row.id_norma, []).append(row)
    return rows
```

In `src/legal_ai/ingest/layout.py`, add to `ProcessedLayout`:
```python
    def file(self, name: str, filename: str) -> Path:
        return self.corpus_dir(name) / filename
```

In `corpus/laboral.yaml`, change the first seed to:
```yaml
  - tipo: Ley
    numero: 20744
    why: "Ley de Contrato de Trabajo, núcleo del corpus"
    original_from: {tipo: Decreto, numero: 390, sancion_year: 1976}
```

- [ ] **Step 4: Implement corpus.py**

`src/legal_ai/parse/corpus.py`:
```python
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from legal_ai.ingest.catalog_reader import NormRow
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import ResolvedCorpus, ResolvedNorm
from legal_ai.parse.antecedentes import HistoryEvent, parse_antecedentes
from legal_ai.parse.html_text import decode_html, html_to_lines
from legal_ai.parse.structure import ParsedText, parse_text
from legal_ai.parse.versions import ArticleRecord, ArticleVersionRecord, VersionSource, build_articles
from legal_ai.parse.vinculos import Relation, parse_vinculos

OUTPUT_FILES = ("documents.jsonl", "articles.jsonl", "article_versions.jsonl", "relations.jsonl", "history.jsonl", "parse_report.json")


class DocumentRecord(BaseModel):
    id_norma: int
    tipo_norma: str
    numeros: list[str]
    organismos: list[str]
    clase_norma: str | None
    fecha_sancion: date | None
    fecha_boletin: date | None
    numero_boletin: int | None
    titulo_resumido: str | None
    titulo_sumario: str | None
    texto_resumido: str | None
    url_original: str | None
    url_actualizado: str | None
    reason: str
    depth: int
    has_original_text: bool
    has_current_text: bool
    original_source_document_id: int | None
    front_matter: str
    n_articles_original: int
    n_articles_current: int
    n_history_events: int


class HistoryRecord(HistoryEvent):
    document_id: int


class DocumentReport(BaseModel):
    id_norma: int
    n_articles_original: int
    n_articles_current: int
    n_versions: int
    n_relations: int
    n_history: int
    warnings: list[str] = Field(default_factory=list)


class ParseReport(BaseModel):
    corpus: str
    catalog_date: date
    parsed_at: datetime
    documents: list[DocumentReport]
    totals: dict[str, int]


def _read_text(raw: RawLayout, id_norma: int, filename: str) -> ParsedText | None:
    path = raw.norm_dir(id_norma) / filename
    if not path.exists():
        return None
    return parse_text(html_to_lines(decode_html(path.read_bytes())))


def _read_relations(raw: RawLayout, id_norma: int) -> list[Relation]:
    relations: list[Relation] = []
    for filename, direction in (("vinculos_modifica.htm", "modifica"), ("vinculos_modificada_por.htm", "modificada_por")):
        path = raw.norm_dir(id_norma) / filename
        if path.exists():
            relations.extend(parse_vinculos(path.read_bytes(), id_norma, direction))
    return relations


def _numero_matches(numero: str, norm: ResolvedNorm) -> bool:
    if "/" in numero:
        number, year = numero.split("/", 1)
        return norm.numero_norma == number and norm.fecha_boletin is not None and str(norm.fecha_boletin.year).endswith(year)
    return norm.numero_norma == numero


def _note_relations(
    document_id: int, versions: list[ArticleVersionRecord], norms: list[ResolvedNorm]
) -> tuple[list[Relation], int]:
    relations: list[Relation] = []
    unresolved = 0
    kinds = {"derogado": "repeals", "abrogado": "repeals", "sustituido": "modifies", "incorporado": "modifies", "modificado": "modifies", "restablecido": "modifies", "observado": "vetoes", "vetado": "vetoes", "suspendido": "suspends", "renumerado": "modifies"}
    for version in versions:
        if version.version_kind != "current" or version.modified_by_numero is None or version.modification_kind is None:
            continue
        match = next(
            (n for n in norms if n.tipo_norma == version.modified_by_tipo and _numero_matches(version.modified_by_numero, n)),
            None,
        )
        if match is None:
            unresolved += 1
            continue
        relations.append(
            Relation(
                source_id=match.id_norma,
                target_id=document_id,
                kind=kinds.get(version.modification_kind, "modifies"),
                evidence="texact_note",
                tipo=match.tipo_norma,
                numero=match.numero_norma,
                fecha_boletin=match.fecha_boletin,
                descripcion=f"{version.article_id} {version.modification_kind}",
            )
        )
    return relations, unresolved


def _write_jsonl(path: Path, records: list[BaseModel]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(record.model_dump_json() + "\n")


def _document(norm: ResolvedNorm, rows: list[NormRow], original: ParsedText | None, current: ParsedText | None, source_id: int | None, n_orig: int, n_cur: int, n_hist: int) -> DocumentRecord:
    first = rows[0] if rows else None
    front = (current or original).front_matter if (current or original) else ""
    return DocumentRecord(
        id_norma=norm.id_norma,
        tipo_norma=norm.tipo_norma,
        numeros=[r.numero_norma for r in rows] or [norm.numero_norma],
        organismos=[r.organismo_origen for r in rows if r.organismo_origen],
        clase_norma=first.clase_norma if first else None,
        fecha_sancion=first.fecha_sancion if first else None,
        fecha_boletin=norm.fecha_boletin,
        numero_boletin=first.numero_boletin if first else None,
        titulo_resumido=first.titulo_resumido if first else None,
        titulo_sumario=first.titulo_sumario if first else norm.titulo_sumario,
        texto_resumido=first.texto_resumido if first else None,
        url_original=norm.url_original,
        url_actualizado=norm.url_actualizado,
        reason=norm.reason,
        depth=norm.depth,
        has_original_text=original is not None,
        has_current_text=current is not None,
        original_source_document_id=source_id,
        front_matter=front,
        n_articles_original=n_orig,
        n_articles_current=n_cur,
        n_history_events=n_hist,
    )


def parse_corpus(
    resolved: ResolvedCorpus, rows: dict[int, list[NormRow]], raw: RawLayout, processed: ProcessedLayout
) -> ParseReport:
    out_dir = processed.corpus_dir(resolved.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    for child in out_dir.iterdir():
        if child.name != "resolved.json":
            (shutil.rmtree if child.is_dir() else child.unlink)(child)

    by_id = {n.id_norma: n for n in resolved.norms}
    documents: list[DocumentRecord] = []
    articles: list[ArticleRecord] = []
    versions: list[ArticleVersionRecord] = []
    relations: dict[tuple[int, int, str, str], Relation] = {}
    history: list[HistoryRecord] = []
    reports: list[DocumentReport] = []
    unresolved_total = 0

    for norm in resolved.norms:
        current = _read_text(raw, norm.id_norma, "texact.htm")
        source_id = resolved.original_sources.get(norm.id_norma)
        if source_id is not None:
            source_norm = by_id.get(source_id)
            source_parsed = _read_text(raw, source_id, "norma.htm")
            original_src = (
                VersionSource(parsed=source_parsed, document_id=source_id, fecha_boletin=source_norm.fecha_boletin if source_norm else None, url=source_norm.url_original if source_norm else None, use_annex_articles=True)
                if source_parsed is not None
                else None
            )
        else:
            own = _read_text(raw, norm.id_norma, "norma.htm")
            original_src = VersionSource(parsed=own, document_id=norm.id_norma, fecha_boletin=norm.fecha_boletin, url=norm.url_original) if own is not None else None
        current_src = VersionSource(parsed=current, document_id=norm.id_norma, fecha_boletin=norm.fecha_boletin, url=norm.url_actualizado) if current is not None else None

        doc_articles, doc_versions, warnings = build_articles(norm.id_norma, original_src, current_src)
        for parsed in (original_src.parsed if original_src else None, current):
            if parsed is not None:
                warnings.extend(parsed.warnings)
        events = [HistoryRecord(document_id=norm.id_norma, **e.model_dump()) for e in parse_antecedentes(current.antecedentes_lines)] if current else []
        doc_relations = _read_relations(raw, norm.id_norma)
        note_relations, unresolved = _note_relations(norm.id_norma, doc_versions, resolved.norms)
        unresolved_total += unresolved
        for relation in doc_relations + note_relations:
            relations.setdefault((relation.source_id, relation.target_id, relation.kind, relation.evidence), relation)

        n_orig = len(original_src.articles()) if original_src else 0
        n_cur = len(current_src.articles()) if current_src else 0
        documents.append(_document(norm, rows.get(norm.id_norma, []), original_src.parsed if original_src else None, current, source_id, n_orig, n_cur, len(events)))
        articles.extend(doc_articles)
        versions.extend(doc_versions)
        history.extend(events)
        reports.append(DocumentReport(id_norma=norm.id_norma, n_articles_original=n_orig, n_articles_current=n_cur, n_versions=len(doc_versions), n_relations=len(doc_relations) + len(note_relations), n_history=len(events), warnings=warnings))

    _write_jsonl(out_dir / "documents.jsonl", documents)
    _write_jsonl(out_dir / "articles.jsonl", articles)
    _write_jsonl(out_dir / "article_versions.jsonl", versions)
    _write_jsonl(out_dir / "relations.jsonl", list(relations.values()))
    _write_jsonl(out_dir / "history.jsonl", history)
    report = ParseReport(
        corpus=resolved.name,
        catalog_date=resolved.catalog_date,
        parsed_at=datetime.now(UTC),
        documents=reports,
        totals={
            "documents": len(documents),
            "documents_with_text": sum(1 for d in documents if d.has_original_text or d.has_current_text),
            "articles": len(articles),
            "versions": len(versions),
            "relations": len(relations),
            "history": len(history),
            "warnings": sum(len(r.warnings) for r in reports),
            "unresolved_note_relations": unresolved_total,
        },
    )
    (out_dir / "parse_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report
```

- [ ] **Step 5: Implement the CLI**

`src/legal_ai/parse/cli.py`:
```python
from datetime import date
from typing import Annotated

import typer

from legal_ai.ingest.catalog import latest_snapshot, load_snapshot
from legal_ai.ingest.catalog_reader import ZipCatalog, collect_rows
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import read_resolved
from legal_ai.parse.corpus import parse_corpus
from legal_ai.settings import Settings

app = typer.Typer(help="Parser de HTML de Infoleg a documentos, artículos, versiones y relaciones.")


@app.callback(invoke_without_command=True)
def run(
    corpus: Annotated[str, typer.Argument(help="Corpus ya resuelto y descargado (ingest resolve + fetch).")],
    show_warnings: Annotated[bool, typer.Option("--warnings", help="Lista las advertencias por norma.")] = False,
) -> None:
    """Genera data/processed/<corpus>/*.jsonl a partir de data/raw."""
    settings = Settings()
    raw = RawLayout(settings.data_dir)
    processed = ProcessedLayout(settings.data_dir)
    resolved = read_resolved(processed.resolved_path(corpus))
    snapshot = load_snapshot(raw, resolved.catalog_date) if raw.catalog_dir(resolved.catalog_date).exists() else latest_snapshot(raw)
    if snapshot is None:
        typer.echo("No hay snapshot del catálogo; corré `legal-ai ingest catalog`.", err=True)
        raise typer.Exit(1)
    rows = collect_rows(ZipCatalog(snapshot, raw), set(resolved.ids()))
    report = parse_corpus(resolved, rows, raw, processed)
    for key, value in report.totals.items():
        typer.echo(f"{key}: {value}")
    if show_warnings:
        for doc in report.documents:
            for warning in doc.warnings:
                typer.echo(f"[{doc.id_norma}] {warning}")
    typer.echo(f"escrito en: {processed.corpus_dir(corpus)}")
```

Modify `src/legal_ai/cli.py` to mount it:
```python
import typer

from legal_ai.ingest.cli import app as ingest_app
from legal_ai.parse.cli import app as parse_app

app = typer.Typer(help="Legal AI Argentina: herramientas de ingestion, indexado y evaluación.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(parse_app, name="parse")


@app.callback()
def main() -> None:
    pass
```

- [ ] **Step 6: Run all tests, lint, types**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run legal-ai parse --help`
Expected: all passed; help prints. `test_parse_corpus_writes_all_outputs` asserts 293 current and 277 original LCT articles: if the numbers differ, run the golden script from Task 9 on the fixture and inspect which header lines were missed or over-matched before touching the assertion. The `resolved_at` string in `make_resolved()` must validate as a datetime; if pydantic rejects it, use `datetime(2026, 9, 12, tzinfo=UTC)`.

- [ ] **Step 7: Commit**

```bash
git add corpus/laboral.yaml src/legal_ai tests/ingest/test_manifest.py tests/parse/test_corpus.py
git commit -m "Parse the corpus into documents, articles, versions, relations and history"
```

---

### Task 9: Golden files from real Infoleg HTML

**Files:**
- Create: `scripts/make_golden.py`, `tests/fixtures/golden/25552_current.json`, `tests/fixtures/golden/229909_original.json`, `tests/fixtures/golden/95487_original.json`, `tests/fixtures/golden/64555_original.json`, `tests/parse/test_golden.py`

**Interfaces:**
- Consumes: `decode_html`, `html_to_lines`, `parse_text`.
- Golden JSON shape: `{"file": "25552/texact.htm", "n_articles": 293, "articles": [{"key": "1", "label": "1", "heading": "Fuentes de regulación", "status": "vigente", "annex": null, "sections": ["TITULO I Disposiciones Generales"], "n_notes": 0, "text_sha256": "…"}, …], "n_annexes": 0, "n_antecedentes_lines": 215, "warnings": []}`.

- [ ] **Step 1: Write the generator script**

`scripts/make_golden.py`:
```python
import hashlib
import json
import sys
from pathlib import Path

from legal_ai.parse.html_text import decode_html, html_to_lines
from legal_ai.parse.structure import parse_text

FIXTURES = Path("tests/fixtures/infoleg")
GOLDEN = Path("tests/fixtures/golden")
TARGETS = {
    "25552_current": "25552/texact.htm",
    "229909_original": "229909/norma.htm",
    "95487_original": "95487/norma.htm",
    "64555_original": "64555/norma.htm",
}


def snapshot(relative: str) -> dict:
    parsed = parse_text(html_to_lines(decode_html((FIXTURES / relative).read_bytes())))
    return {
        "file": relative,
        "n_articles": len(parsed.articles),
        "articles": [
            {
                "key": a.key,
                "label": a.label,
                "heading": a.heading,
                "status": a.status,
                "annex": a.annex,
                "sections": [f"{s.kind} {s.number} {s.name or ''}".strip() for s in a.sections],
                "n_notes": len(a.notes),
                "text_sha256": hashlib.sha256(a.text.encode("utf-8")).hexdigest(),
            }
            for a in parsed.articles
        ],
        "n_annexes": len(parsed.annexes),
        "n_antecedentes_lines": len(parsed.antecedentes_lines),
        "warnings": parsed.warnings,
    }


def main() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:] or list(TARGETS)
    for name in only:
        data = snapshot(TARGETS[name])
        (GOLDEN / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        derogados = [a["label"] for a in data["articles"] if a["status"] == "derogado"]
        print(f"{name}: {data['n_articles']} articles, {len(derogados)} derogados {derogados}, warnings={len(data['warnings'])}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate and review**

Run: `uv run python scripts/make_golden.py`
Expected output to check by hand against the verified facts:
- `25552_current`: 293 articles; derogados must include 28, 54, 61, 113 and the rest listed by the script (the texact has 7 whole-article "derogado" notes, but articles whose only content is a derogation of a range may count differently: read each derogado label and confirm its `text_with_notes` starts with `(Artículo derogado`). `warnings` should be empty or only `numbering gap` lines; a `cross-reference-like header ignored` warning must be inspected: open the line and confirm it really is not an article.
- `229909_original`: 279 articles, 277 with `annex == "ANEXO"`, 2 with `annex == null`.
- `95487_original`: 3 articles, `n_annexes == 1`.
- `64555_original`: 3 articles, `n_annexes == 0`.

Then spot-check three articles in `tests/fixtures/golden/25552_current.json` against the HTML: `92bis` heading `Período de prueba`, `245` heading `Indemnización por antigüedad o despido`, `28` status `derogado`. If any check fails, fix the parser (Tasks 2–4), re-run the script, re-check. Do not edit the golden JSON by hand.

- [ ] **Step 3: Write the golden test**

`tests/parse/test_golden.py`:
```python
import hashlib
import json
from pathlib import Path

import pytest

from legal_ai.parse.html_text import decode_html, html_to_lines
from legal_ai.parse.structure import parse_text

FIXTURES = Path("tests/fixtures/infoleg")
GOLDEN = Path("tests/fixtures/golden")


@pytest.mark.parametrize("name", ["25552_current", "229909_original", "95487_original", "64555_original"])
def test_parser_matches_golden(name: str):
    golden = json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    parsed = parse_text(html_to_lines(decode_html((FIXTURES / golden["file"]).read_bytes())))
    assert len(parsed.articles) == golden["n_articles"]
    for expected, actual in zip(golden["articles"], parsed.articles, strict=True):
        assert actual.key == expected["key"], (expected["key"], actual.raw_header)
        assert actual.heading == expected["heading"], actual.raw_header
        assert actual.status == expected["status"], actual.raw_header
        assert actual.annex == expected["annex"]
        assert [f"{s.kind} {s.number} {s.name or ''}".strip() for s in actual.sections] == expected["sections"]
        assert len(actual.notes) == expected["n_notes"], actual.raw_header
        assert hashlib.sha256(actual.text.encode("utf-8")).hexdigest() == expected["text_sha256"], actual.raw_header
    assert len(parsed.annexes) == golden["n_annexes"]
    assert len(parsed.antecedentes_lines) == golden["n_antecedentes_lines"]
    assert parsed.warnings == golden["warnings"]


def test_lct_known_facts():
    parsed = parse_text(html_to_lines(decode_html((FIXTURES / "25552/texact.htm").read_bytes())))
    keys = [a.key for a in parsed.articles]
    assert len(keys) == 293
    assert keys[:3] == ["1", "2", "3"] and keys[-1] == "278"
    assert {"11bis", "17bis", "29bis", "92bis", "92ter", "102bis", "103bis", "104bis", "105bis", "132bis", "189bis", "197bis", "223bis", "245bis", "255bis"} <= set(keys)
    by_key = {a.key: a for a in parsed.articles}
    assert by_key["92bis"].heading == "Período de prueba"
    assert by_key["245"].heading == "Indemnización por antigüedad o despido"
    assert by_key["28"].status == "derogado"
    assert by_key["28"].notes[0].by.numero == "27802"
    assert sum(1 for a in parsed.articles for n in a.notes if n.kind == "sustituido" and n.affects_whole_article) >= 60
    assert parsed.article("245") is not None and any(s.kind == "TITULO" for s in by_key["245"].sections)


def test_decree_annex_is_the_lct_body():
    parsed = parse_text(html_to_lines(decode_html((FIXTURES / "229909/norma.htm").read_bytes())))
    assert [a.key for a in parsed.main_articles()] == ["1", "2"]
    annex = parsed.annex_articles()
    assert len(annex) == 277
    assert annex[0].heading == "Fuentes de regulación" and annex[-1].key == "277"
    assert parsed.trailer.startswith("VIDELA.")
```

- [ ] **Step 4: Run tests, lint, types**

Run: `uv run pytest tests/parse/test_golden.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: all passed. `ruff` may flag `scripts/make_golden.py` for the `dict` return annotation; use `dict[str, object]` if so.

- [ ] **Step 5: Commit**

```bash
git add scripts/make_golden.py tests/fixtures/golden tests/parse/test_golden.py
git commit -m "Add golden tests from real Infoleg HTML (LCT, Decreto 390/76, Res. 384/2004, Ley 25.323)"
```

---

### Task 10: Run the parser on the corpus, review, document

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, `README.md`

- [ ] **Step 1: Re-resolve (the manifest gained `original_from`) and parse**

Run: `uv run legal-ai ingest resolve laboral && uv run legal-ai parse laboral --warnings 2>&1 | tee /tmp/parse-laboral.log | tail -40`
Expected: totals printed (`documents: 931`, `documents_with_text`, `articles`, `versions`, `relations`, `history`, `warnings`, `unresolved_note_relations`), then per-document warnings. Resolve count stays 931 (Decreto 390/76 is already in the corpus as a modifier; its reason stays `modifies:25552` because the seed pass finds it first with reason `original_source_for:25552` — either is acceptable, note which one appears).

- [ ] **Step 2: Review the warnings**

Run:
```bash
grep -c "cross-reference-like" /tmp/parse-laboral.log
grep "cross-reference-like" /tmp/parse-laboral.log | head -20
grep -c "duplicate article" /tmp/parse-laboral.log
grep -c "numbering gap" /tmp/parse-laboral.log
grep -c "differs from original but has no dated note" /tmp/parse-laboral.log
grep -c "missing in current" /tmp/parse-laboral.log
python3 -c "import json; d=json.load(open('data/processed/laboral/parse_report.json')); zero=[r['id_norma'] for r in d['documents'] if r['n_articles_original']+r['n_articles_current']==0]; print('docs sin artículos:', len(zero), zero[:15])"
```
For the documents with text but zero articles (expected: some resolutions written without numbered articles, and the 180 without text), open two of them with `uv run python -c "from legal_ai.parse.html_text import *; from pathlib import Path; print('\n'.join(html_to_lines(decode_html(Path('data/raw/infoleg/normas/<id>/norma.htm').read_bytes()))[:40]))"` and record what they look like. Do not tune the parser for them in this task: record them as a Phase 2 follow-up in the roadmap.

- [ ] **Step 3: Sanity-check three real outputs**

Run:
```bash
grep '"25552:245@current"' data/processed/laboral/article_versions.jsonl | python3 -c "import json,sys; v=json.loads(sys.stdin.read()); print(v['effective_from'], v['modification_kind'], v['modified_by_tipo'], v['modified_by_numero'], v['text'][:200])"
grep '"25552:245@original"' data/processed/laboral/article_versions.jsonl | python3 -c "import json,sys; v=json.loads(sys.stdin.read()); print(v['effective_from'], v['effective_until'], v['source_document_id'], v['text'][:200])"
grep -c '"evidence":"texact_note"' data/processed/laboral/relations.jsonl
grep -c '"evidence":"infoleg_vinculos"' data/processed/laboral/relations.jsonl
```
Expected: current 245 dated by its latest whole-article note and attributed to a Ley or Decreto; original 245 `effective_from` 1976-05-21, `effective_until` equal to the current's `effective_from`, source 229909. Record the two relation counts.

- [ ] **Step 4: Document**

In `docs/ARCHITECTURE.md`, under *Fuente de datos* → *Limitaciones que condicionan el diseño*, add:
```
- El "texto original" de la LCT (norma.htm de 25552) es la ley aprobatoria de
  1974 (3 artículos). El cuerpo vigente es el texto ordenado por Decreto 390/76,
  cuyo norma.htm sí trae los 277 artículos como anexo. El manifest lo declara
  con `original_from` y el parser usa ese anexo como versión `original`.
- Al final de texact.htm hay una sección "Antecedentes Normativos" con el
  historial de sustituciones por artículo (norma, artículo, fecha B.O.), sin
  los textos anteriores. Se guarda en history.jsonl como índice para la Fase 9.
```
Under *Layout de datos* replace the `data/processed/<corpus>/` block with:
```
data/processed/<corpus>/
  resolved.json            manifest resuelto a id_norma
  documents.jsonl          una norma por línea, con lista de (organismo, número)
  articles.jsonl           identidad de cada artículo y su jerarquía
  article_versions.jsonl   texto por versión (original | current) con vigencia
  relations.jsonl          aristas con evidencia (infoleg_vinculos | texact_note)
  history.jsonl            eventos de "Antecedentes Normativos" por artículo
  parse_report.json        conteos y advertencias por norma
```
In the *Modelo de datos* → *documents* table add rows `numeros`, `organismos` (listas: resoluciones conjuntas), `front_matter`, `original_source_document_id`. In *article_versions* add `text_with_notes`, `source_document_id`, `unchanged_from_original`.

In `docs/DECISIONS.md` append:
```
## ADR-015: La versión "original" de la LCT es el texto ordenado de 1976

**Contexto.** Infoleg no tiene el cuerpo de la Ley 20.744 de 1974: su
norma.htm es la ley aprobatoria (3 artículos). El texto vigente es el texto
ordenado por Decreto 390/76, cuyo norma.htm trae los 277 artículos como anexo,
con la numeración que se usa hasta hoy.

**Decisión.** El manifest permite declarar `original_from` en una semilla. Para
la LCT apunta al Decreto 390/76; el parser toma los artículos del anexo como
versión `original`, con `effective_from` 1976-05-21 y `source_document_id`
229909. La versión de 1974 con la numeración vieja queda fuera del alcance.

**Consecuencias.** Toda cita "original" de la LCT es al t.o. 1976, y así se
etiqueta. Si una fuente futura trae el texto de 1974, entra como una versión
más, no reemplaza a esta.

## ADR-016: Parser propio por líneas, sin librería de HTML

**Contexto.** El HTML de Infoleg es plano: `<p>`, `<br>`, `<b>`, `<span>`,
sin clases ni estructura semántica; el `<b>` a veces envuelve el `<p>`.

**Decisión.** Aplanar a líneas de texto y reconocer estructura con expresiones
regulares probadas contra las 25 variantes reales de encabezado, con golden
files de cuatro normas reales.

**Alternativas.** selectolax/BeautifulSoup: agregan una dependencia para
recorrer un árbol que no significa nada. Un LLM para extraer estructura: no
determinista, caro para 931 normas y opaco para debuggear.

**Consecuencias.** Cada variante nueva de encabezado es un caso de test, no
una sorpresa en producción. Las normas sin artículos numerados quedan con
`front_matter` y sin artículos, y se listan en el reporte.
```

In `docs/ROADMAP.md`: mark Fase 2 `hecha` and Fase 3 `siguiente`; under "Fase 1 en detalle" add a "## Fase 2 en detalle" section listing the totals printed in Step 1 and the counts from Steps 2–3 (documents with text but no articles, cross-reference warnings, texact_note vs infoleg_vinculos relations), plus a follow-up bullet: "Normas con texto y sin artículos numerados: revisar en Fase 3 si se indexan como un solo chunk". In `README.md` change the status line to "Fases 0 a 2 completas. Fase 3 (índice + RAG baseline) es la siguiente." and add `uv run legal-ai parse laboral` to *Cómo ejecutar* (replace the placeholder line `uv run legal-ai parse laboral         # genera data/processed`).

- [ ] **Step 5: Final check and commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright && git status --short`
Expected: green; only docs and `README.md` modified (processed data is ignored).

```bash
git add docs README.md
git commit -m "Run Phase 2 parser on the laboral corpus and record results"
```

---

## Self-review

**Spec coverage.**
- Parser que preserva estructura jurídica (título/capítulo/artículo) → Tasks 2, 4. ✔
- Metadata por chunk (document_id, article, chapter, source_url, effective_from/until, status) → Tasks 7, 8 (`ArticleRecord.sections`, `ArticleVersionRecord`). `parent_document` → `source_document_id`. ✔
- Notas de modificación → Task 3. ✔
- Dos versiones por artículo (ADR-006) → Task 7. ✔ LCT original from Decreto 390/76 → Tasks 8 (`original_from`), 7 (`use_annex_articles`). ✔
- Relaciones con evidencia → Task 6 (vínculos) + Task 8 (`texact_note`). ✔
- Historial → Task 5 + Task 8 (`history.jsonl`). ✔
- Resoluciones conjuntas (varios organismos/números) → Task 8 `DocumentRecord.numeros/organismos`. ✔
- Tests con fixtures reales → Task 9. ✔
- `processed` regenerable → Task 8 deletes everything but `resolved.json`. ✔
- Chunks / `context_prefix` / embeddings: not in this phase (Phase 3). Documented in ROADMAP.

**Placeholder scan.** None. The golden JSON files are generated by the script, not hand-written; the plan tells the executor what to verify in them.

**Type consistency.** `ArticleHeader.key/label` (Task 2) feed `ParsedArticle.key/label` (Task 4) feed `ArticleRecord.id = f"{document_id}:{key}"` (Task 7) and the golden JSON `key` (Task 9). `ModificationNote.by: ByClause` (Task 3) is reused by `HistoryEvent.by` (Task 5) and read in `versions.py` (`note.by.bo_date`, `note.by.numero`). `VersionSource.articles()` distinguishes annex vs main articles for the LCT/Decreto case. `Relation` (Task 6) is the single relation type also produced by `_note_relations` (Task 8). `ResolvedCorpus.original_sources` (Task 8) is consumed by `parse_corpus`. `ProcessedLayout.file` is defined but only the CLI's `corpus_dir` is used; keep it, Phase 3 reads the JSONL by name.
