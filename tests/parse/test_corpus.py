import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from legal_ai.ingest.catalog_reader import NormRow
from legal_ai.ingest.layout import ProcessedLayout, RawLayout
from legal_ai.ingest.manifest import ResolvedCorpus, ResolvedNorm
from legal_ai.parse.corpus import parse_corpus

FIXTURES = Path("tests/fixtures/infoleg")


def norm(
    id_norma: int, tipo: str, numero: str, bo: str, reason: str = "seed", texact: bool = False
) -> ResolvedNorm:
    base = f"http://servicios.infoleg.gob.ar/x/{id_norma}"
    return ResolvedNorm(
        id_norma=id_norma,
        tipo_norma=tipo,
        numero_norma=numero,
        fecha_boletin=date.fromisoformat(bo),
        titulo_sumario=None,
        url_original=f"{base}/norma.htm",
        url_actualizado=f"{base}/texact.htm" if texact else None,
        reason=reason,
        depth=0,
    )


def make_resolved() -> ResolvedCorpus:
    return ResolvedCorpus(
        name="mini",
        catalog_date=date(2026, 9, 12),
        resolved_at=datetime(2026, 9, 12, tzinfo=UTC),
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
        return NormRow(
            id_norma=i,
            tipo_norma=tipo,
            numero_norma=num,
            organismo_origen=org,
            fecha_boletin=date.fromisoformat(bo),
            titulo_sumario="T",
        )

    return {
        25552: [row(25552, "Ley", "20744", "HONORABLE CONGRESO", "1974-09-27")],
        229909: [row(229909, "Decreto", "390", "PODER EJECUTIVO", "1976-05-21")],
        95487: [
            row(95487, "Resolución", "384", "MINISTERIO DE TRABAJO", "2004-06-03"),
            row(95487, "Resolución", "12", "MINISTERIO DE ECONOMIA", "2004-06-03"),
        ],
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
    assert docs[95487]["numeros"] == ["384", "12"] and docs[95487]["organismos"] == [
        "MINISTERIO DE TRABAJO",
        "MINISTERIO DE ECONOMIA",
    ]
    assert docs[25552]["has_current_text"] and docs[25552]["original_source_document_id"] == 229909
    assert docs[25552]["n_articles_current"] == 293 and docs[25552]["n_articles_original"] == 277
    assert docs[25552]["n_history_events"] >= 60
    assert docs[229909]["n_articles_original"] == 2
    assert docs[64555]["n_articles_original"] == 3 and not docs[64555]["has_current_text"]
    assert "CONSIDERANDO" in docs[95487]["front_matter"]

    articles = read_jsonl(out / "articles.jsonl")
    lct_articles = [a for a in articles if a["document_id"] == 25552]
    assert len(lct_articles) == 293
    assert any(
        a["id"] == "25552:92bis" and a["heading"] == "Período de prueba" for a in lct_articles
    )
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
    assert any(
        r["source_id"] == 229909 and r["target_id"] == 25552 and r["kind"] == "consolidates"
        for r in relations
    )
    assert len(
        {(r["source_id"], r["target_id"], r["kind"], r["evidence"]) for r in relations}
    ) == len(relations)

    history = read_jsonl(out / "history.jsonl")
    assert all(h["document_id"] == 25552 for h in history)
    assert any(h["article_key"] == "245bis" and h["kind"] == "incorporado" for h in history)

    saved = json.loads((out / "parse_report.json").read_text(encoding="utf-8"))
    assert saved["totals"]["documents"] == 4
    assert saved["totals"]["articles"] == len(articles)
    assert report.totals["versions"] == len(versions)
    lct_report = next(d for d in report.documents if d.id_norma == 25552)
    assert lct_report.n_articles_current == 293
