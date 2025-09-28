from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from polla_app.net import FetchMetadata
from polla_app.sources._24h import list_24h_result_urls, parse_24h_draw
from polla_app.sources.pozos import get_pozo_openloto, get_pozo_resultadosloto
from polla_app.sources.t13 import parse_t13_draw

FIXTURES = Path(__file__).parent / "fixtures"


def _metadata(name: str, *, url: str = "https://example.test") -> FetchMetadata:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return FetchMetadata(
        url=url,
        user_agent="pytest-agent",
        fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        html=html,
    )


def test_t13_table_parse(monkeypatch) -> None:
    metadata = _metadata("t13_sorteo_5198.html")
    monkeypatch.setattr("polla_app.sources.t13.fetch_html", lambda *_, **__: metadata)

    record = parse_t13_draw("https://example.test/t13/5198")

    assert record["sorteo"] == 5198
    assert record["fecha"] == "2024-12-01"
    assert any(p["categoria"].lower().startswith("quina") for p in record["premios"])


def test_t13_paragraph_fallback(monkeypatch) -> None:
    metadata = _metadata("t13_sorteo_5322.html")
    monkeypatch.setattr("polla_app.sources.t13.fetch_html", lambda *_, **__: metadata)

    record = parse_t13_draw("https://example.test/t13/5322")

    categorias = {p["categoria"] for p in record["premios"]}
    assert "Súper Terna (3 + comodín)" in categorias
    assert record["fecha"] == "2025-09-16"


def test_list_24h_result_urls(monkeypatch) -> None:
    metadata = _metadata("24h_tag_index.html")
    monkeypatch.setattr("polla_app.sources._24h.fetch_html", lambda *_, **__: metadata)

    urls = list_24h_result_urls(limit=2)

    assert urls[0] == "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322"
    assert urls[1].endswith("sorteo-5321")


def test_parse_24h_draw(monkeypatch) -> None:
    metadata = _metadata("t13_sorteo_5198.html", url="https://www.24horas.cl/loto/5198")
    monkeypatch.setattr("polla_app.sources._24h.fetch_html", lambda *_, **__: metadata)

    record = parse_24h_draw("https://www.24horas.cl/loto/5198")

    assert record["provenance"]["source"] == "24horas"
    assert any(p["categoria"].startswith("Loto 6") for p in record["premios"])


def test_openloto_pozo(monkeypatch) -> None:
    metadata = _metadata("openloto_pozo.html")
    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    pozos = get_pozo_openloto()

    assert pozos["montos"]["Loto Clásico"] == 690_000_000
    assert "Total estimado" in pozos["montos"]


def test_resultadosloto_pozo_with_anniversary_jubilazo(monkeypatch) -> None:
    metadata = _metadata("resultadosloto_pozo.html")
    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    pozos = get_pozo_resultadosloto()

    assert pozos["montos"]["Jubilazo $1.000.000"] == 960_000_000
    assert pozos["montos"]["Jubilazo $500.000"] == 480_000_000
