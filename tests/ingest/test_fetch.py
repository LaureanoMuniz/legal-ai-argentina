import hashlib
import json
from pathlib import Path

import httpx
import pytest
import respx

from legal_ai.ingest.fetch import (
    VINCULOS_URL,
    FetchOutcome,
    InfolegClient,
    fetch_norm,
    norm_urls,
)
from legal_ai.ingest.layout import RawLayout
from legal_ai.ingest.manifest import ResolvedNorm
from legal_ai.settings import DEFAULT_USER_AGENT

LCT = ResolvedNorm(
    id_norma=25552,
    tipo_norma="Ley",
    numero_norma="20744",
    fecha_boletin=None,
    titulo_sumario=None,
    url_original="http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/norma.htm",
    url_actualizado="http://servicios.infoleg.gob.ar/infolegInternet/anexos/25000-29999/25552/texact.htm",
    reason="seed",
    depth=0,
)
NO_TEXACT = LCT.model_copy(update={"id_norma": 401266, "url_actualizado": None})


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


def make_client(clock: FakeClock, min_interval: float = 0.5) -> InfolegClient:
    http = httpx.Client(headers={"User-Agent": DEFAULT_USER_AGENT})
    return InfolegClient(http, min_interval=min_interval, sleep=clock.sleep, clock=clock.monotonic)


def test_norm_urls_order_and_missing_texact():
    urls = norm_urls(NO_TEXACT)
    assert list(urls) == [
        "norma.htm",
        "texact.htm",
        "vinculos_modifica.htm",
        "vinculos_modificada_por.htm",
    ]
    assert urls["texact.htm"] is None
    assert urls["vinculos_modifica.htm"] == VINCULOS_URL.format(modo=1, id_norma=401266)
    assert urls["vinculos_modificada_por.htm"] == VINCULOS_URL.format(modo=2, id_norma=401266)


@respx.mock
def test_client_sends_user_agent_and_rate_limits():
    route = respx.get("http://example.test/a").mock(return_value=httpx.Response(200, content=b"x"))
    clock = FakeClock()
    client = make_client(clock, min_interval=0.5)
    client.get("http://example.test/a")
    client.get("http://example.test/a")
    assert route.calls[0].request.headers["User-Agent"] == DEFAULT_USER_AGENT
    assert clock.sleeps == [0.5]


@respx.mock
def test_client_retries_on_5xx_then_succeeds():
    route = respx.get("http://example.test/b").mock(
        side_effect=[httpx.Response(503), httpx.Response(500), httpx.Response(200, content=b"ok")]
    )
    clock = FakeClock()
    response = make_client(clock, min_interval=0).get("http://example.test/b")
    assert response.content == b"ok"
    assert route.call_count == 3
    assert clock.sleeps == [1.0, 2.0]


@respx.mock
def test_client_gives_up_after_max_attempts():
    respx.get("http://example.test/c").mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        make_client(FakeClock(), min_interval=0).get("http://example.test/c")


@respx.mock
def test_client_does_not_retry_403():
    route = respx.get("http://example.test/d").mock(return_value=httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        make_client(FakeClock(), min_interval=0).get("http://example.test/d")
    assert route.call_count == 1


@respx.mock
def test_fetch_norm_writes_files_and_meta(tmp_path: Path):
    urls = norm_urls(LCT)
    for name, url in urls.items():
        assert url is not None
        respx.get(url).mock(
            return_value=httpx.Response(
                200, content=name.encode(), headers={"content-type": "text/html"}
            )
        )
    layout = RawLayout(tmp_path)
    report = fetch_norm(make_client(FakeClock(), min_interval=0), layout, LCT)

    assert all(o == FetchOutcome.FETCHED for o in report.outcomes.values())
    norm_dir = layout.norm_dir(25552)
    assert (norm_dir / "texact.htm").read_bytes() == b"texact.htm"
    meta = json.loads((norm_dir / "meta.json").read_text())
    assert meta["id_norma"] == 25552
    assert meta["files"]["norma.htm"]["sha256"] == hashlib.sha256(b"norma.htm").hexdigest()
    assert meta["files"]["norma.htm"]["content_type"] == "text/html"
    assert meta["missing"] == []


@respx.mock
def test_fetch_norm_uses_cache_unless_force(tmp_path: Path):
    urls = norm_urls(LCT)
    routes = {
        name: respx.get(url).mock(return_value=httpx.Response(200, content=b"v1"))
        for name, url in urls.items()
        if url is not None
    }
    layout = RawLayout(tmp_path)
    client = make_client(FakeClock(), min_interval=0)
    fetch_norm(client, layout, LCT)
    second = fetch_norm(client, layout, LCT)
    assert all(o == FetchOutcome.CACHED for o in second.outcomes.values())
    assert all(r.call_count == 1 for r in routes.values())

    third = fetch_norm(client, layout, LCT, force=True)
    assert all(o == FetchOutcome.FETCHED for o in third.outcomes.values())
    assert all(r.call_count == 2 for r in routes.values())


@respx.mock
def test_fetch_norm_records_missing_url_and_failed_file(tmp_path: Path):
    urls = norm_urls(NO_TEXACT)
    respx.get(urls["norma.htm"]).mock(return_value=httpx.Response(404))
    respx.get(urls["vinculos_modifica.htm"]).mock(return_value=httpx.Response(200, content=b"m1"))
    respx.get(urls["vinculos_modificada_por.htm"]).mock(
        return_value=httpx.Response(200, content=b"m2")
    )
    layout = RawLayout(tmp_path)
    report = fetch_norm(make_client(FakeClock(), min_interval=0), layout, NO_TEXACT)

    assert report.outcomes["texact.htm"] == FetchOutcome.NO_URL
    assert report.outcomes["norma.htm"] == FetchOutcome.FAILED
    assert "404" in report.errors["norma.htm"]
    assert report.outcomes["vinculos_modifica.htm"] == FetchOutcome.FETCHED
    meta = json.loads((layout.norm_dir(401266) / "meta.json").read_text())
    assert meta["missing"] == ["texact.htm"]
    assert "norma.htm" not in meta["files"]
    assert not (layout.norm_dir(401266) / "norma.htm").exists()
