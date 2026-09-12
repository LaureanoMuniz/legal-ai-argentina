from datetime import date
from pathlib import Path

import pytest

from legal_ai.ingest.catalog_reader import InMemoryCatalog, NormRow, RelationRow
from legal_ai.ingest.manifest import (
    AmbiguousSeedError,
    CorpusManifest,
    Expand,
    Seed,
    SeedNotFoundError,
    SeedRef,
    load_manifest,
    read_resolved,
    resolve_corpus,
    write_resolved,
)
from tests.conftest import FIXTURE_NORMS, FIXTURE_RELATIONS


def make_catalog() -> InMemoryCatalog:
    return InMemoryCatalog(
        norms=[NormRow.model_validate(r) for r in FIXTURE_NORMS],
        relations=[RelationRow.model_validate(r) for r in FIXTURE_RELATIONS],
    )


def test_load_manifest_from_repo_yaml():
    manifest = load_manifest(Path("corpus/laboral.yaml"))
    assert manifest.name == "laboral"
    assert [s.numero for s in manifest.seeds] == [20744, 24013, 25323, 25877, 27742, 27802]
    assert manifest.expand.tipos is None


def test_resolve_seeds_and_expand_depth_1_includes_every_tipo_by_default():
    manifest = CorpusManifest(
        name="t", description="", seeds=[Seed(tipo="Ley", numero=20744, why="x")]
    )
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))
    by_id = {n.id_norma: n for n in corpus.norms}
    assert by_id[999001].tipo_norma == "Resolución"
    assert by_id[999001].reason == "modifies:25552"
    assert corpus.ids() == [25552, 229909, 401266, 999001]


def test_resolve_seeds_and_expand_depth_1_filtered_by_tipo():
    manifest = CorpusManifest(
        name="t",
        description="",
        seeds=[Seed(tipo="Ley", numero=20744, why="x")],
        expand=Expand(tipos=["Ley", "Decreto"]),
    )
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))

    by_id = {n.id_norma: n for n in corpus.norms}
    assert corpus.name == "t"
    assert corpus.catalog_date == date(2026, 9, 12)
    assert by_id[25552].reason == "seed" and by_id[25552].depth == 0
    assert by_id[25552].url_actualizado is not None
    assert by_id[401266].reason == "modifies:25552" and by_id[401266].depth == 1
    assert by_id[229909].tipo_norma == "Decreto"
    assert 999001 not in by_id
    assert corpus.ids() == [25552, 229909, 401266]


def test_seed_that_is_also_modifier_stays_seed():
    manifest = CorpusManifest(
        name="t",
        description="",
        seeds=[Seed(tipo="Ley", numero=20744, why="x"), Seed(tipo="Ley", numero=27742, why="y")],
    )
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))
    bases = next(n for n in corpus.norms if n.id_norma == 401266)
    assert bases.reason == "seed" and bases.depth == 0


def test_expand_disabled_returns_only_seeds():
    manifest = CorpusManifest(
        name="t",
        description="",
        seeds=[Seed(tipo="Ley", numero=20744, why="x")],
        expand=Expand(modificatorias_de_seeds=False),
    )
    assert resolve_corpus(manifest, make_catalog(), date(2026, 9, 12)).ids() == [25552]


def test_missing_seed_raises():
    manifest = CorpusManifest(
        name="t", description="", seeds=[Seed(tipo="Ley", numero=99999, why="x")]
    )
    with pytest.raises(SeedNotFoundError, match="99999"):
        resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))


def test_ambiguous_seed_raises_unless_year_given():
    ambiguous = CorpusManifest(
        name="t", description="", seeds=[Seed(tipo="Ley", numero=1, why="x")]
    )
    with pytest.raises(AmbiguousSeedError, match="1001, 1002"):
        resolve_corpus(ambiguous, make_catalog(), date(2026, 9, 12))

    precise = CorpusManifest(
        name="t",
        description="",
        seeds=[Seed(tipo="Ley", numero=1, why="x", sancion_year=1900)],
        expand=Expand(modificatorias_de_seeds=False),
    )
    assert resolve_corpus(precise, make_catalog(), date(2026, 9, 12)).ids() == [1002]


def test_write_and_read_resolved_roundtrip(tmp_path: Path):
    manifest = CorpusManifest(
        name="t", description="", seeds=[Seed(tipo="Ley", numero=20744, why="x")]
    )
    corpus = resolve_corpus(manifest, make_catalog(), date(2026, 9, 12))
    path = tmp_path / "processed" / "t" / "resolved.json"
    write_resolved(corpus, path)
    assert read_resolved(path) == corpus


def test_original_from_is_resolved_and_recorded():
    manifest = CorpusManifest(
        name="t",
        description="",
        seeds=[
            Seed(
                tipo="Ley",
                numero=20744,
                why="x",
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
    assert (lct.original_from.tipo, lct.original_from.numero, lct.original_from.sancion_year) == (
        "Decreto",
        390,
        1976,
    )
