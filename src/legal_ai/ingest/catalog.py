import hashlib
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel

from legal_ai.ingest.layout import RawLayout

DATASET_BASE = "https://datos.jus.gob.ar/dataset/d9a963ea-8b1d-4ca3-9dd9-07a4773e8c23/resource"


class CatalogResource(BaseModel):
    name: str
    filename: str
    url: str


CATALOG_RESOURCES: tuple[CatalogResource, ...] = (
    CatalogResource(
        name="normas",
        filename="base-infoleg-normativa-nacional.zip",
        url=f"{DATASET_BASE}/bf0ec116-ad4e-4572-a476-e57167a84403/download/base-infoleg-normativa-nacional.zip",
    ),
    CatalogResource(
        name="modificatorias",
        filename="base-complementaria-infoleg-normas-modificatorias.zip",
        url=f"{DATASET_BASE}/dea3c247-5a5d-408f-a224-39ae0f8eb371/download/base-complementaria-infoleg-normas-modificatorias.zip",
    ),
    CatalogResource(
        name="modificadas",
        filename="base-complementaria-infoleg-normas-modificadas.zip",
        url=f"{DATASET_BASE}/0c4fdafe-f4e8-4ac2-bc2e-acf50c27066d/download/base-complementaria-infoleg-normas-modificadas.zip",
    ),
)

MANIFEST_NAME = "manifest.json"


class SnapshotExistsError(Exception):
    pass


class ResourceRecord(BaseModel):
    name: str
    filename: str
    url: str
    sha256: str
    size_bytes: int


class CatalogSnapshot(BaseModel):
    snapshot_date: date
    fetched_at: datetime
    resources: list[ResourceRecord]

    def path_for(self, name: str, layout: RawLayout) -> Path:
        record = next(r for r in self.resources if r.name == name)
        return layout.catalog_dir(self.snapshot_date) / record.filename


def _stream_to_file(http: httpx.Client, url: str, dest: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with http.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    return digest.hexdigest(), size


def download_catalog(
    layout: RawLayout, http: httpx.Client, snapshot_date: date, *, force: bool = False
) -> CatalogSnapshot:
    target = layout.catalog_dir(snapshot_date)
    if target.exists():
        if not force:
            raise SnapshotExistsError(f"{target} ya existe; usá --force para reemplazarlo")
        shutil.rmtree(target)
    staging = target.with_name(target.name + ".partial")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        records: list[ResourceRecord] = []
        for resource in CATALOG_RESOURCES:
            sha256, size = _stream_to_file(http, resource.url, staging / resource.filename)
            records.append(
                ResourceRecord(
                    name=resource.name,
                    filename=resource.filename,
                    url=resource.url,
                    sha256=sha256,
                    size_bytes=size,
                )
            )
        snapshot = CatalogSnapshot(
            snapshot_date=snapshot_date, fetched_at=datetime.now(UTC), resources=records
        )
        (staging / MANIFEST_NAME).write_text(snapshot.model_dump_json(indent=2))
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    staging.rename(target)
    return snapshot


def load_snapshot(layout: RawLayout, snapshot_date: date) -> CatalogSnapshot:
    manifest = layout.catalog_dir(snapshot_date) / MANIFEST_NAME
    return CatalogSnapshot.model_validate_json(manifest.read_text())


def latest_snapshot(layout: RawLayout) -> CatalogSnapshot | None:
    dates = [d for d in layout.catalog_dates() if (layout.catalog_dir(d) / MANIFEST_NAME).exists()]
    if not dates:
        return None
    return load_snapshot(layout, dates[-1])
