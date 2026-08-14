"""Tests for the game-stats sync (public Google Sheets CSV → stats.json)."""

from __future__ import annotations

from pathlib import Path

import pytest

from polla_app.stats import (
    DEFAULT_STATS_URL,
    _to_number,
    build_stats_payload,
    resolve_stats_url,
    write_site_stats,
)

FIXTURE = Path(__file__).parent / "fixtures" / "stats_sample.csv"


def test_to_number_chilean_formats() -> None:
    assert _to_number("4.496.388") == 4496388.0
    assert _to_number("1 en 4.496.388") == 4496388.0
    assert _to_number("333,33") == 333.33
    assert _to_number("13,79%") == 13.79
    assert _to_number("$620.000.000") == 620000000.0
    assert _to_number("n/a") is None
    assert _to_number("") is None
    assert _to_number("") is None


def test_build_stats_payload_groups_by_game() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    assert payload["game_count"] == 2  # Loto + Loto 3 (sample)
    assert payload["row_count"] == 7
    loto = payload["games"]["Loto"]
    assert len(loto) == 5
    clasico = loto[0]
    assert clasico["Categoría"] == "Loto Clásico"
    assert clasico["Probabilidad de ganar"] == "1 en 4.496.388"
    assert clasico["Probabilidad de ganar (num)"] == 4496388.0
    assert clasico["Premio Categoría (num)"] == 620000000.0
    assert clasico["% Retorno Esperado Individual (num)"] == 13.79
    assert "Precio o apuesta (num)" in clasico


def test_write_site_stats_uses_net(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from datetime import datetime, timezone

    from polla_app.net import FetchMetadata

    csv_text = FIXTURE.read_text(encoding="utf-8")
    metadata = FetchMetadata(
        url="https://docs.google.com/spreadsheets/d/x/gviz/tq?tqx=out:csv",
        user_agent="pytest",
        fetched_at=datetime.now(timezone.utc),
        html=csv_text,
    )
    monkeypatch.setattr("polla_app.stats.fetch_html", lambda *_, **__: metadata)

    output = tmp_path / "stats.json"
    write_site_stats("https://docs.google.com/spreadsheets/d/x", output)
    import json

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source_url"].startswith("https://docs.google.com")
    assert payload["game_count"] == 2


def test_write_site_stats_propagates_network_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(*_: object, **__: object) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr("polla_app.stats.fetch_html", fail)
    with pytest.raises(RuntimeError, match="network down"):
        write_site_stats("https://example.test/x", tmp_path / "stats.json")


def test_default_stats_url_points_to_public_sheet() -> None:
    assert DEFAULT_STATS_URL.startswith(
        "https://docs.google.com/spreadsheets/d/16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    )


def test_resolve_stats_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLLA_STATS_URL", "https://example.test/custom.csv")
    assert resolve_stats_url() == "https://example.test/custom.csv"
