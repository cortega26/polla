"""Tests for the game-stats sync (public Google Sheets CSV → stats.json)."""

from __future__ import annotations

from pathlib import Path

import pytest

from polla_app.stats import (
    DEFAULT_STATS_URL,
    _to_number,
    build_stats_payload,
    merge_live_kino,
    merge_real_prices,
    merge_real_prizes,
    resolve_stats_url,
    write_site_stats,
)

FIXTURE = Path(__file__).parent / "fixtures" / "stats_sample.csv"


def _prizes() -> dict[str, int]:
    return {
        "Loto Clásico": 620_000_000,
        "Recargado": 810_000_000,
        "Revancha": 190_000_000,
        "Desquite": 460_000_000,
        "Jubilazo $1.000.000": 960_000_000,
        "Jubilazo $500.000": 360_000_000,
        "Kino": 8_370_000_000,
    }


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
    # Empty live data still runs the merges: rows are flagged reference
    # and stale manual prizes are stripped (never shown as live).
    row = payload["games"]["Loto"][0]
    assert row["precio_estatico"] is True
    assert row["premio_real_clp"] is None
    assert "Premio Categoría" not in row


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


def test_merge_real_prizes_overlays_live_data() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    merge_real_prizes(payload, _prizes())

    loto = {row["Categoría"]: row for row in payload["games"]["Loto"]}
    clasico = loto["Loto Clásico"]
    assert clasico["premio_real_clp"] == 620_000_000
    assert clasico["retorno_real_pct"] == pytest.approx(13.79, abs=0.01)  # 620M/4.496.388/1000

    jubilazo = loto["Jubilazo"]
    assert jubilazo["premio_real_clp"] == 1_320_000_000  # 960M + 360M
    assert jubilazo["retorno_real_pct"] == pytest.approx(58.71, abs=0.01)


def test_merge_real_prizes_strips_stale_manual_columns() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    merge_real_prizes(payload, _prizes())

    clasico = payload["games"]["Loto"][0]
    assert "Premio Categoría" not in clasico
    assert "Premio Categoría (num)" not in clasico
    assert "% Retorno Esperado Individual (num)" not in clasico
    assert "premio_real_clp" in clasico


def test_merge_real_prizes_unmapped_rows_get_none() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    merge_real_prizes(payload, _prizes())

    exacta = payload["games"]["Loto 3"][0]
    assert exacta["premio_real_clp"] is None
    assert exacta["retorno_real_pct"] is None


def test_merge_real_prizes_kino_maps_club_kino_only() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    payload["games"]["Kino"] = [
        {
            "Nombre": "Kino",
            "Categoría": "Club Kino",
            "Combinaciones totales (num)": 4457400.0,
            "Precio o apuesta (num)": 600.0,
        },
        {
            "Nombre": "Kino",
            "Categoría": "Rekino",
            "Combinaciones totales (num)": 4457400.0,
            "Precio o apuesta (num)": 400.0,
        },
    ]
    merge_real_prizes(payload, _prizes())

    club = payload["games"]["Kino"][0]
    assert club["premio_real_clp"] == 8_370_000_000
    assert club["retorno_real_pct"] == pytest.approx(312.9, abs=0.1)  # 8370M/4.457.400/600

    rekino = payload["games"]["Kino"][1]
    assert rekino["premio_real_clp"] is None
    assert rekino["retorno_real_pct"] is None


def _loto_prices() -> dict[str, dict[str, int]]:
    return {
        "Loto Clásico": {"delta_clp": 1000, "acumulado_clp": 1000},
        "Recargado": {"delta_clp": 500, "acumulado_clp": 1500},
        "Revancha": {"delta_clp": 300, "acumulado_clp": 1800},
        "Desquite": {"delta_clp": 200, "acumulado_clp": 2000},
        "Jubilazo": {"delta_clp": 500, "acumulado_clp": 2500},
        "Multiplicar": {"delta_clp": 500, "acumulado_clp": 3000},
        "Jubilazo 50 años": {"delta_clp": 500, "acumulado_clp": 3500},
    }


def test_merge_real_prices_overlays_live_loto_prices() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    merge_real_prices(payload, _loto_prices())
    merge_real_prizes(payload, _prizes())

    loto = {row["Categoría"]: row for row in payload["games"]["Loto"]}
    clasico = loto["Loto Clásico"]
    assert clasico["precio_real_clp"] == 1000
    assert clasico["precio_acumulado_clp"] == 1000
    assert clasico["precio_estatico"] is False

    revancha = loto["Revancha"]
    assert revancha["precio_real_clp"] == 300
    assert revancha["precio_acumulado_clp"] == 1800
    # Retorno recalculado con el precio vivo: 190M / 4.496.388 / 300
    assert revancha["retorno_real_pct"] == pytest.approx(14.09, abs=0.01)


def test_merge_real_prices_marks_unmapped_games_as_static() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    merge_real_prices(payload, _loto_prices())

    exacta = payload["games"]["Loto 3"][0]
    assert exacta["precio_estatico"] is True
    assert exacta["precio_real_clp"] is None
    # Sheet price columns are kept as reference for static rows
    assert "Precio o apuesta" in exacta


def _kino_prices() -> dict[str, dict[str, int]]:
    return {
        "Kino": {"delta_clp": 1000, "acumulado_clp": 1000},
        "ReKino": {"delta_clp": 500, "acumulado_clp": 1500},
        "RequeteKino": {"delta_clp": 500, "acumulado_clp": 2000},
        "Chao Jefe $2 Millones": {"delta_clp": 500, "acumulado_clp": 2500},
        "Chao Jefe $3 Millones": {"delta_clp": 500, "acumulado_clp": 3000},
        "Súper Combo Marraqueta": {"delta_clp": 500, "acumulado_clp": 3500},
    }


def test_merge_live_kino_rebuilds_section_with_all_additional_games() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    payload["games"]["Kino"] = [
        {"Categoría": "Club Kino", "Precio o apuesta": "600"},
        {"Categoría": "Chanchito Regalón", "Precio o apuesta": "200"},
    ]
    merge_live_kino(
        payload,
        prizes={
            "Kino": 8_370_000_000,
            "ReKino": 1_610_000_000,
            "RequeteKino": 1_040_000_000,
            "Chao Jefe $2 Millones": 1_200_000_000,
            "Chao Jefe $3 Millones": 1_080_000_000,
            "Súper Combo Marraqueta": 1_000_000_000,
        },
        prices=_kino_prices(),
    )

    rows = {row["Categoría"]: row for row in payload["games"]["Kino"]}
    assert list(rows.keys()) == [
        "Kino",
        "ReKino",
        "RequeteKino",
        "Chao Jefe $2 Millones",
        "Chao Jefe $3 Millones",
        "Súper Combo Marraqueta",
    ]
    # Obsolete sheet rows are gone
    assert "Chanchito Regalón" not in rows

    club = rows["Kino"]
    assert club["precio_real_clp"] == 1000
    assert club["precio_acumulado_clp"] == 1000
    assert club["premio_real_clp"] == 8_370_000_000
    assert club["retorno_real_pct"] == pytest.approx(187.78, abs=0.01)

    rekino = rows["ReKino"]
    assert rekino["precio_real_clp"] == 500
    assert rekino["precio_acumulado_clp"] == 1500
    assert rekino["premio_real_clp"] == 1_610_000_000
    assert rekino["retorno_real_pct"] == pytest.approx(72.24, abs=0.01)

    combo = rows["Súper Combo Marraqueta"]
    assert combo["precio_acumulado_clp"] == 3500
    assert combo["premio_real_clp"] == 1_000_000_000


def test_merge_live_kino_keeps_sheet_rows_when_no_live_prizes() -> None:
    payload = build_stats_payload(FIXTURE.read_text(encoding="utf-8"))
    payload["games"]["Kino"] = [{"Categoría": "Club Kino", "Precio o apuesta": "600"}]
    merge_live_kino(payload, prizes={}, prices=_kino_prices())
    # No live prizes -> section untouched (UI renders "—" without ref marks)
    assert payload["games"]["Kino"][0]["Categoría"] == "Club Kino"
    assert "kino_live" not in payload
