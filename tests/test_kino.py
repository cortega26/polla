"""Tests for the Kino (Lotería de Concepción) pozo fetcher."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polla_app.exceptions import ParseError
from polla_app.net import FetchMetadata
from polla_app.sources.kino import (
    _extract_montos,
    _extract_next_data,
    _parse_pendon_fecha,
    get_pozo_kino,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sources" / "kino" / "page.html"

SAMPLE_OUTPUTS = {
    "F_FechaTxt": "2026/08/14",
    "F_SrtKinPozoTot": 14300,
    "F_SrtKinAproxSrt": 8370,
    "F_SrtKinRevAprox": 1610,
    "F_SrtKinRevGMSdAprox": 0,
    "F_SrtKinRev2Aprox": 1040,
    "F_SrtKinRevCJ2Aprox": 1000,
    "F_SrtKinRevSd2Aprox": 1200,
    "F_SrtKinRevCJ4Aprox": 1080,
}


def _metadata(html: str) -> FetchMetadata:
    return FetchMetadata(
        url="https://pendon-kino.loteria.cl/pendonkino",
        user_agent="pytest-agent",
        fetched_at=datetime(2026, 8, 14, tzinfo=UTC),
        html=html,
    )


def test_parse_pendon_fecha() -> None:
    assert _parse_pendon_fecha("2026/08/14") == "2026-08-14"
    assert _parse_pendon_fecha("14/08/2026") is None
    assert _parse_pendon_fecha(None) is None
    assert _parse_pendon_fecha("") is None


def test_extract_montos_skips_zeros_and_maps_categories() -> None:
    montos = _extract_montos(SAMPLE_OUTPUTS)
    assert montos == {
        "Kino": 8_370_000_000,
        "ReKino": 1_610_000_000,
        "RequeteKino": 1_040_000_000,
        "Chao Jefe $2 Millones": 1_200_000_000,
        "Chao Jefe $3 Millones": 1_080_000_000,
        "Súper Combo Marraqueta": 1_000_000_000,
    }
    # Gran Sueldo is 0 in the source -> omitted (no phantom zeros)
    assert "Kino Gran Sueldo" not in montos


def test_extract_montos_empty_when_all_zero() -> None:
    outputs = {k: 0 for k in SAMPLE_OUTPUTS}
    assert _extract_montos(outputs) == {}


def test_extract_next_data_missing_block() -> None:
    with pytest.raises(ParseError, match="__NEXT_DATA__"):
        _extract_next_data("<html><body>no data</body></html>", context="Kino pendón")


def test_extract_next_data_invalid_json() -> None:
    with pytest.raises(ParseError, match="not valid JSON"):
        _extract_next_data(
            '<script id="__NEXT_DATA__" type="application/json">{broken</script>',
            context="Kino pendón",
        )


def test_get_pozo_kino_parses_real_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr("polla_app.sources.browser.fetch_html", lambda *_, **__: _metadata(html))

    payload = get_pozo_kino()

    assert payload["fuente"] == "https://pendon-kino.loteria.cl/pendonkino"
    assert payload["estimado"] is True
    assert payload["sorteo"] == 3266
    assert payload["fecha"] == "2026-08-14"
    assert payload["montos"]["Kino"] == 8_370_000_000
    assert "Total estimado" not in payload["montos"]
    assert len(payload["sha256"]) == 64


def test_get_pozo_kino_rejects_empty_montos(monkeypatch: pytest.MonkeyPatch) -> None:
    outputs = {k: 0 for k in SAMPLE_OUTPUTS}
    data = {
        "props": {
            "pageProps": {
                "pendon": {"outputs": outputs, "error": None},
                "firstSorteo": 3266,
            }
        }
    }
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'
    monkeypatch.setattr("polla_app.sources.browser.fetch_html", lambda *_, **__: _metadata(html))

    with pytest.raises(ParseError, match="No valid Kino pozo amounts"):
        get_pozo_kino()


def test_get_pozo_kino_rejects_upstream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    data = {
        "props": {
            "pageProps": {
                "pendon": {"outputs": SAMPLE_OUTPUTS, "error": "boom"},
                "firstSorteo": 3266,
            }
        }
    }
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'
    monkeypatch.setattr("polla_app.sources.browser.fetch_html", lambda *_, **__: _metadata(html))

    with pytest.raises(ParseError, match="upstream error"):
        get_pozo_kino()


def test_get_pozo_kino_warns_on_html_without_kino_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    data = {
        "props": {
            "pageProps": {
                "pendon": {"outputs": SAMPLE_OUTPUTS, "error": None},
                "firstSorteo": 3266,
            }
        }
    }
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'
    monkeypatch.setattr("polla_app.sources.browser.fetch_html", lambda *_, **__: _metadata(html))

    with caplog.at_level("WARNING", logger="polla_app.sources.kino"):
        payload = get_pozo_kino()

    assert payload["montos"]["Kino"] == 8_370_000_000
    assert "missing 'Kino' text" in caplog.text


def test_kino_pipeline_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app.pipeline import run_pipeline

    html = FIXTURE.read_text(encoding="utf-8")
    monkeypatch.setattr("polla_app.sources.browser.fetch_html", lambda *_, **__: _metadata(html))

    summary = run_pipeline(
        sources=["kino"],
        source_overrides={},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "run.jsonl",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.25,
    )

    assert summary["decision"]["status"] == "publish"
    assert summary["decision"]["confidence"] == "single_source"

    record = json.loads((tmp_path / "normalized.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["sorteo"] == 3266
    assert record["pozos_proximo"]["Kino"] == 8_370_000_000
    # Kino categories use hub names and never collide with Loto's "Revancha"
    assert "Revancha" not in record["pozos_proximo"]
    assert record["pozos_proximo"]["ReKino"] == 1_610_000_000
