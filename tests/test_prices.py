"""Tests for the live Loto price structure scraper."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from polla_app.exceptions import ParseError
from polla_app.net import FetchMetadata
from polla_app.sources.prices import _extract_prices, get_loto_prices

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "prices" / "page.html"


def _metadata(html: str) -> FetchMetadata:
    return FetchMetadata(
        url="https://www.polla.cl/es/view/juego/loto",
        user_agent="pytest-agent",
        fetched_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
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


def test_get_loto_prices_full_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "polla_app.sources.prices.fetch_html",
        lambda *_, **__: _metadata(FIXTURE.read_text(encoding="utf-8")),
    )
    payload = get_loto_prices()
    assert payload["fuente"].startswith("https://www.polla.cl")
    assert payload["precios"]["Revancha"]["delta_clp"] == 300
    assert len(payload["sha256"]) == 64
