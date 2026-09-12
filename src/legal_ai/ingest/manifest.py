from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from legal_ai.ingest.catalog_reader import Catalog, NormRow


class Seed(BaseModel):
    tipo: str
    numero: int
    why: str
    sancion_year: int | None = None


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

    def ids(self) -> list[int]:
        return [n.id_norma for n in self.norms]


class SeedNotFoundError(Exception):
    pass


class AmbiguousSeedError(Exception):
    pass


def _matches(seed: Seed, row: NormRow) -> bool:
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


def _find_seeds(manifest: CorpusManifest, catalog: Catalog) -> dict[int, ResolvedNorm]:
    candidates: dict[int, list[NormRow]] = {i: [] for i in range(len(manifest.seeds))}
    for row in catalog.norms():
        for i, seed in enumerate(manifest.seeds):
            if _matches(seed, row):
                candidates[i].append(row)
    resolved: dict[int, ResolvedNorm] = {}
    for i, seed in enumerate(manifest.seeds):
        rows = candidates[i]
        if not rows:
            raise SeedNotFoundError(f"{seed.tipo} {seed.numero} no está en el catálogo")
        if len(rows) > 1:
            ids = ", ".join(str(r.id_norma) for r in sorted(rows, key=lambda r: r.id_norma))
            raise AmbiguousSeedError(
                f"{seed.tipo} {seed.numero} coincide con varias normas ({ids}); agregá sancion_year"
            )
        row = rows[0]
        resolved[row.id_norma] = _to_resolved(row, "seed", 0)
    return resolved


def _expand_once(
    frontier: set[int],
    known: dict[int, ResolvedNorm],
    catalog: Catalog,
    tipos: list[str] | None,
    depth: int,
) -> dict[int, ResolvedNorm]:
    parent_of: dict[int, int] = {}
    for rel in catalog.relations():
        if rel.id_norma_modificada in frontier and rel.id_norma_modificatoria not in known:
            parent_of.setdefault(rel.id_norma_modificatoria, rel.id_norma_modificada)
    if not parent_of:
        return {}
    added: dict[int, ResolvedNorm] = {}
    for row in catalog.norms():
        parent = parent_of.get(row.id_norma)
        if parent is not None and (tipos is None or row.tipo_norma in tipos):
            added[row.id_norma] = _to_resolved(row, f"modifies:{parent}", depth)
    return added


def resolve_corpus(
    manifest: CorpusManifest, catalog: Catalog, catalog_date: date
) -> ResolvedCorpus:
    known = _find_seeds(manifest, catalog)
    frontier = set(known)
    if manifest.expand.modificatorias_de_seeds:
        for depth in range(1, manifest.expand.max_depth + 1):
            added = _expand_once(frontier, known, catalog, manifest.expand.tipos, depth)
            if not added:
                break
            known.update(added)
            frontier = set(added)
    norms = sorted(known.values(), key=lambda n: (n.depth, n.id_norma))
    return ResolvedCorpus(
        name=manifest.name, catalog_date=catalog_date, resolved_at=datetime.now(UTC), norms=norms
    )


def write_resolved(corpus: ResolvedCorpus, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(corpus.model_dump_json(indent=2), encoding="utf-8")


def read_resolved(path: Path) -> ResolvedCorpus:
    return ResolvedCorpus.model_validate_json(path.read_text(encoding="utf-8"))
