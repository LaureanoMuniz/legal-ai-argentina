from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from legal_ai.ingest.catalog_reader import Catalog, NormRow


class SeedRef(BaseModel):
    tipo: str
    numero: int
    sancion_year: int | None = None


class Seed(BaseModel):
    tipo: str
    numero: int
    why: str
    sancion_year: int | None = None
    original_from: SeedRef | None = None
    expand_tipos: list[str] | None = None
    """Tipos que se aceptan al expandir ESTA semilla; None usa el filtro global."""


class Expand(BaseModel):
    modificatorias_de_seeds: bool = True
    max_depth: int = 1
    tipos: list[str] | None = None


class CorpusManifest(BaseModel):
    name: str
    description: str
    seeds: list[Seed]
    expand: Expand = Field(default_factory=Expand)


def load_manifest(path: Path) -> CorpusManifest:
    with path.open(encoding="utf-8") as fh:
        return CorpusManifest.model_validate(yaml.safe_load(fh))


class ResolvedNorm(BaseModel):
    id_norma: int
    tipo_norma: str
    numero_norma: str
    fecha_boletin: date | None
    titulo_sumario: str | None
    url_original: str | None
    url_actualizado: str | None
    reason: str
    depth: int


class ResolvedCorpus(BaseModel):
    name: str
    catalog_date: date
    resolved_at: datetime
    norms: list[ResolvedNorm]
    original_sources: dict[int, int] = Field(default_factory=dict)

    def ids(self) -> list[int]:
        return [n.id_norma for n in self.norms]


class SeedNotFoundError(Exception):
    pass


class AmbiguousSeedError(Exception):
    pass


def _matches(seed: Seed | SeedRef, row: NormRow) -> bool:
    if row.tipo_norma != seed.tipo or row.numero_norma != str(seed.numero):
        return False
    if seed.sancion_year is None:
        return True
    return row.fecha_sancion is not None and row.fecha_sancion.year == seed.sancion_year


def _to_resolved(row: NormRow, reason: str, depth: int) -> ResolvedNorm:
    return ResolvedNorm(
        id_norma=row.id_norma,
        tipo_norma=row.tipo_norma,
        numero_norma=row.numero_norma,
        fecha_boletin=row.fecha_boletin,
        titulo_sumario=row.titulo_sumario,
        url_original=row.texto_original,
        url_actualizado=row.texto_actualizado,
        reason=reason,
        depth=depth,
    )


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


def _expand_once(
    frontier: set[int],
    known: dict[int, ResolvedNorm],
    catalog: Catalog,
    tipos: list[str] | None,
    depth: int,
    tipos_por_padre: dict[int, list[str]] | None = None,
) -> dict[int, ResolvedNorm]:
    parent_of: dict[int, int] = {}
    for rel in catalog.relations():
        if rel.id_norma_modificada in frontier and rel.id_norma_modificatoria not in known:
            parent_of.setdefault(rel.id_norma_modificatoria, rel.id_norma_modificada)
    if not parent_of:
        return {}
    per_parent = tipos_por_padre or {}
    added: dict[int, ResolvedNorm] = {}
    for row in catalog.norms():
        parent = parent_of.get(row.id_norma)
        if parent is None:
            continue
        allowed = per_parent.get(parent, tipos)
        if allowed is None or row.tipo_norma in allowed:
            added[row.id_norma] = _to_resolved(row, f"modifies:{parent}", depth)
    return added


def _seed_ids(manifest: CorpusManifest, known: dict[int, ResolvedNorm]) -> dict[int, Seed]:
    out: dict[int, Seed] = {}
    for norm_id, norm in known.items():
        for seed in manifest.seeds:
            if norm.tipo_norma == seed.tipo and norm.numero_norma == str(seed.numero):
                out[norm_id] = seed
    return out


def resolve_corpus(
    manifest: CorpusManifest, catalog: Catalog, catalog_date: date
) -> ResolvedCorpus:
    known, sources = _find_seeds(manifest, catalog)
    frontier = set(known)
    tipos_por_padre = {
        norm_id: seed.expand_tipos
        for norm_id, seed in _seed_ids(manifest, known).items()
        if seed.expand_tipos is not None
    }
    if manifest.expand.modificatorias_de_seeds:
        for depth in range(1, manifest.expand.max_depth + 1):
            added = _expand_once(
                frontier, known, catalog, manifest.expand.tipos, depth, tipos_por_padre
            )
            if not added:
                break
            known.update(added)
            frontier = set(added)
    norms = sorted(known.values(), key=lambda n: (n.depth, n.id_norma))
    return ResolvedCorpus(
        name=manifest.name,
        catalog_date=catalog_date,
        resolved_at=datetime.now(UTC),
        norms=norms,
        original_sources=sources,
    )


def write_resolved(corpus: ResolvedCorpus, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")


def read_resolved(path: Path) -> ResolvedCorpus:
    return ResolvedCorpus.model_validate_json(path.read_text(encoding="utf-8"))
