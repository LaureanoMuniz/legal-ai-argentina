import html
import re

_CHARSET_RE = re.compile(rb"charset=[\"']?\s*([A-Za-z0-9_\-]+)", re.IGNORECASE)
_DROP_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>|<!--.*?-->", re.IGNORECASE | re.DOTALL)
_BREAK_RE = re.compile(
    r"<br\s*/?>|</(?:p|div|tr|li|h[1-6]|table|blockquote|pre)\s*>|<(?:p|div|tr|h[1-6])\b[^>]*>",
    re.IGNORECASE,
)
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
