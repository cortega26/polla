from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from polla_app.net import FetchMetadata
from polla_app.sources.pozos import get_pozo_openloto, get_pozo_resultadosloto

FIXTURES = Path(__file__).parent / "fixtures"


def _metadata(name: str, *, url: str = "https://example.test") -> FetchMetadata:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return FetchMetadata(
        url=url,
        user_agent="pytest-agent",
        fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        html=html,
    )


## Draw article parsers removed; only pozo aggregators remain.


def test_openloto_pozo(monkeypatch) -> None:
    metadata = _metadata("openloto_pozo.html")
    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    pozos = get_pozo_openloto()

    assert pozos["montos"]["Loto Clásico"] == 690_000_000
    assert "Total estimado" not in pozos["montos"], "Totals are excluded from output"


def test_resultadosloto_pozo_with_anniversary_jubilazo(monkeypatch) -> None:
    metadata = _metadata("resultadosloto_pozo.html")
    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    pozos = get_pozo_resultadosloto()

    assert pozos["montos"]["Jubilazo $1.000.000"] == 960_000_000
    assert pozos["montos"]["Jubilazo $500.000"] == 480_000_000
    assert pozos["sorteo"] == 5322
    assert pozos["fecha"] == "2025-09-16"
