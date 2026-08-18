"""Tests for the live Loto/Kino price structure scrapers."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from polla_app.exceptions import ParseError
from polla_app.net import FetchMetadata
from polla_app.sources.prices import (
    _extract_kino_prices,
    _extract_prices,
    get_kino_prices,
    get_loto_prices,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "prices" / "page.html"
KINO_FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "prices" / "kino_hub.html"


def _metadata(html: str) -> FetchMetadata:
    return FetchMetadata(
        url="https://www.polla.cl/es/view/juego/loto",
        user_agent="pytest-agent",
        fetched_at=datetime(2026, 8, 14, tzinfo=UTC),
        html=html,
    )


def test_extract_prices_standard_structure() -> None:
    from bs4 import BeautifulSoup

    html = FIXTURE.read_text(encoding="utf-8")
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    payload = _extract_prices(text)

    assert payload["precios"]["Loto Clásico"] == {"delta_clp": 1000, "acumulado_clp": 1000}
    assert payload["precios"]["Recargado"] == {"delta_clp": 500, "acumulado_clp": 1500}
    assert payload["precios"]["Revancha"] == {"delta_clp": 300, "acumulado_clp": 1800}
    assert payload["precios"]["Desquite"] == {"delta_clp": 200, "acumulado_clp": 2000}
    assert payload["precios"]["Jubilazo"] == {"delta_clp": 500, "acumulado_clp": 2500}
    assert payload["precios"]["Multiplicar"] == {"delta_clp": 500, "acumulado_clp": 3000}
    assert payload["precios"]["Jubilazo 50 años"] == {"delta_clp": 500, "acumulado_clp": 3500}


def test_extract_prices_fallback_to_deltas() -> None:
    html = """
    <html><body>
      <p>LOTO: $1.000</p>
      <h1>Juegos adicionales</h1>
      <label>RECARGADO <span>$500 por sorteo</span></label>
      <label>REVANCHA <span>$300 por sorteo</span></label>
      <label>DESQUITE <span>$200 por sorteo</span></label>
      <label>JUBILAZO <span>$500 por sorteo</span></label>
      <label>MULTIPLICAR <span>$500 por sorteo</span></label>
      <label>JUBILAZO 50 AÑOS <span>$500 por sorteo</span></label>
    </body></html>
    """
    from bs4 import BeautifulSoup

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    payload = _extract_prices(text)
    assert payload["precios"]["Loto Clásico"]["acumulado_clp"] == 1000
    assert payload["precios"]["Jubilazo 50 años"]["acumulado_clp"] == 3500


def test_extract_prices_rejects_missing_structure() -> None:
    with pytest.raises(ParseError, match="Loto price structure"):
        _extract_prices("no prices here at all")


def test_extract_prices_rejects_non_monotonic() -> None:
    text = """
    LOTO: $1.000
    RECARGADO $500 por sorteo
    REVANCHA $300 por sorteo
    DESQUITE $0 por sorteo
    JUBILAZO $500 por sorteo
    MULTIPLICAR $500 por sorteo
    JUBILAZO 50 AÑOS $500 por sorteo
    """
    with pytest.raises(ParseError, match="not monotonic"):
        _extract_prices(text)


def test_get_loto_prices_full_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "polla_app.sources.browser.fetch_html",
        lambda *_, **__: _metadata(FIXTURE.read_text(encoding="utf-8")),
    )
    payload = get_loto_prices()
    assert payload["fuente"].startswith("https://www.polla.cl")
    assert payload["precios"]["Revancha"]["delta_clp"] == 300
    assert len(payload["sha256"]) == 64


def test_extract_kino_prices_structure() -> None:
    import json
    import re

    html = KINO_FIXTURE.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S
    )
    assert match is not None
    payload = _extract_kino_prices(json.loads(match.group(1)))

    assert payload["sorteo"] == 3266
    assert payload["fecha"] == "2026/08/14"
    assert payload["cumulative"] == 3500
    assert payload["precios"]["Kino"] == {"delta_clp": 1000, "acumulado_clp": 1000}
    assert payload["precios"]["ReKino"] == {"delta_clp": 500, "acumulado_clp": 1500}
    assert payload["precios"]["RequeteKino"] == {"delta_clp": 500, "acumulado_clp": 2000}
    assert payload["precios"]["Súper Combo Marraqueta"] == {
        "delta_clp": 500,
        "acumulado_clp": 3500,
    }


def test_extract_kino_prices_rejects_missing_sorteos() -> None:
    with pytest.raises(ParseError, match="initialSorteos"):
        _extract_kino_prices({"props": {"pageProps": {}}})


def _kino_draw(**fields: object) -> dict[str, Any]:
    return {
        "NumeroSorteo": 3266,
        "FechaSorteo": "2026/08/14",
        "PrecioKino": 1000,
        "PrecioReKino": 500,
        "PrecioRequeteKino": 500,
        "PrecioChaoJefe2M": 500,
        "PrecioChaoJefe3M": 500,
        "PrecioComboMarraqueta": 500,
        **fields,
    }


def _kino_next_data(draw: dict[str, Any]) -> dict[str, Any]:
    return {"props": {"pageProps": {"initialSorteos": {"data": [draw]}}}}


def test_extract_kino_prices_skips_missing_variant() -> None:
    draw = _kino_draw()
    draw.pop("PrecioComboMarraqueta")
    payload = _extract_kino_prices(_kino_next_data(draw))

    assert len(payload["precios"]) == 5
    assert payload["cumulative"] == 3000
    assert "Súper Combo Marraqueta" not in payload["precios"]
    assert payload["precios"]["Kino"] == {"delta_clp": 1000, "acumulado_clp": 1000}
    assert payload["precios"]["Chao Jefe $3 Millones"] == {
        "delta_clp": 500,
        "acumulado_clp": 3000,
    }


def test_extract_kino_prices_zero_variant_skipped() -> None:
    payload = _extract_kino_prices(_kino_next_data(_kino_draw(PrecioReKino=0)))

    assert len(payload["precios"]) == 5
    assert payload["cumulative"] == 3000
    assert "ReKino" not in payload["precios"]


def test_extract_kino_prices_all_missing_raises() -> None:
    draw = {k: v for k, v in _kino_draw().items() if not k.startswith("Precio")}
    with pytest.raises(ParseError, match="no valid price fields"):
        _extract_kino_prices(_kino_next_data(draw))


def test_get_kino_prices_full_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def stub_fetch(_url: str, ua: str, **kwargs: object) -> FetchMetadata:
        captured["ua"] = ua
        captured["headers"] = str(kwargs.get("extra_headers"))
        return _metadata(KINO_FIXTURE.read_text(encoding="utf-8"))

    monkeypatch.setattr("polla_app.sources.browser.fetch_html", stub_fetch)
    payload = get_kino_prices()
    assert payload["precios"]["Chao Jefe $3 Millones"]["delta_clp"] == 500
    # The hub requires browser-like framing headers
    assert "Sec-Fetch-Dest" in captured["headers"]
