import hashlib
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from legal_ai.ingest.layout import RawLayout
from legal_ai.ingest.manifest import ResolvedNorm

VINCULOS_URL = (
    "http://servicios.infoleg.gob.ar/infolegInternet/verVinculos.do?modo={modo}&id={id_norma}"
)
META_NAME = "meta.json"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class InfolegClient:
    def __init__(
        self,
        http: httpx.Client,
        *,
        min_interval: float,
        max_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = http
        self._min_interval = min_interval
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    def _wait_turn(self) -> None:
        if self._last_request is not None:
            elapsed = self._clock() - self._last_request
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
        self._last_request = self._clock()

    def get(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            if attempt:
                self._sleep(float(2 ** (attempt - 1)))
            self._wait_turn()
            try:
                response = self._http.get(url, follow_redirects=True)
            except httpx.TransportError as exc:
                last_error = exc
                continue
            if response.status_code in RETRYABLE_STATUS:
                last_error = httpx.HTTPStatusError(
                    f"{response.status_code} en {url}", request=response.request, response=response
                )
                continue
            response.raise_for_status()
            return response
        assert last_error is not None
        raise last_error


def norm_urls(norm: ResolvedNorm) -> dict[str, str | None]:
    return {
        "norma.htm": norm.url_original,
        "texact.htm": norm.url_actualizado,
        "vinculos_modifica.htm": VINCULOS_URL.format(modo=1, id_norma=norm.id_norma),
        "vinculos_modificada_por.htm": VINCULOS_URL.format(modo=2, id_norma=norm.id_norma),
    }


class FileRecord(BaseModel):
    url: str
    status_code: int
    sha256: str
    size_bytes: int
    content_type: str | None
    fetched_at: datetime


class NormMeta(BaseModel):
    id_norma: int
    files: dict[str, FileRecord] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)


class FetchOutcome(StrEnum):
    FETCHED = "fetched"
    CACHED = "cached"
    NO_URL = "no_url"
    FAILED = "failed"


class FetchReport(BaseModel):
    id_norma: int
    outcomes: dict[str, FetchOutcome] = Field(default_factory=dict)
    errors: dict[str, str] = Field(default_factory=dict)


def _load_meta(norm_dir: Path, id_norma: int) -> NormMeta:
    path = norm_dir / META_NAME
    if path.exists():
        return NormMeta.model_validate_json(path.read_text(encoding="utf-8"))
    return NormMeta(id_norma=id_norma)


def _save_meta(norm_dir: Path, meta: NormMeta) -> None:
    (norm_dir / META_NAME).write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def fetch_norm(
    client: InfolegClient, layout: RawLayout, norm: ResolvedNorm, *, force: bool = False
) -> FetchReport:
    norm_dir = layout.norm_dir(norm.id_norma)
    norm_dir.mkdir(parents=True, exist_ok=True)
    meta = _load_meta(norm_dir, norm.id_norma)
    report = FetchReport(id_norma=norm.id_norma)

    for name, url in norm_urls(norm).items():
        target = norm_dir / name
        if url is None:
            report.outcomes[name] = FetchOutcome.NO_URL
            if name not in meta.missing:
                meta.missing.append(name)
            continue
        if not force and name in meta.files and target.exists():
            report.outcomes[name] = FetchOutcome.CACHED
            continue
        try:
            response = client.get(url)
        except httpx.HTTPError as exc:
            report.outcomes[name] = FetchOutcome.FAILED
            report.errors[name] = str(exc)
            continue
        target.write_bytes(response.content)
        meta.files[name] = FileRecord(
            url=url,
            status_code=response.status_code,
            sha256=hashlib.sha256(response.content).hexdigest(),
            size_bytes=len(response.content),
            content_type=response.headers.get("content-type"),
            fetched_at=datetime.now(UTC),
        )
        if name in meta.missing:
            meta.missing.remove(name)
        report.outcomes[name] = FetchOutcome.FETCHED
        _save_meta(norm_dir, meta)

    _save_meta(norm_dir, meta)
    return report
