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


def snapshot(relative: str) -> dict[str, object]:
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
        (GOLDEN / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        articles = data["articles"]
        assert isinstance(articles, list)
        derogados = [a["label"] for a in articles if a["status"] == "derogado"]
        warnings = data["warnings"]
        assert isinstance(warnings, list)
        print(
            f"{name}: {data['n_articles']} articles, {len(derogados)} derogados {derogados}, warnings={len(warnings)}"
        )
        for warning in warnings:
            print(f"   ! {warning}")


if __name__ == "__main__":
    main()
