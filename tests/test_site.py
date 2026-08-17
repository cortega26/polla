"""Tests for the static dashboard data generator."""

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from polla_app.__main__ import cli
from polla_app.site import build_site_payload, write_site_data


def _invoke_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> str:
    """Run `polla site` with a no-op stats writer and return data.json text."""
    from polla_app import __main__ as main_mod

    monkeypatch.setattr(main_mod, "write_site_stats", lambda *a, **k: None)
    result = CliRunner().invoke(cli, ["site", *args])
    assert result.exit_code == 0, result.output
    return (tmp_path / "data.json").read_text(encoding="utf-8")


def _write_ndjson(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    return path


def test_build_site_payload_loto_and_kino(tmp_path: Path) -> None:
    loto = tmp_path / "loto.jsonl"
    kino = tmp_path / "kino.jsonl"
    summary = tmp_path / "summary.json"
    _write_ndjson(
        loto,
        [
            {
                "sorteo": 5464,
                "fecha": "2026-08-13",
                "confidence": "full",
                "fuente": "openloto",
                "pozos_proximo": {"Loto Clásico": 690_000_000, "Revancha": 100_000_000},
            }
        ],
    )
    _write_ndjson(
        kino,
        [
            {
                "sorteo": 3266,
                "fecha": "2026-08-14",
                "confidence": "single_source",
                "fuente": "kino",
                "pozos_proximo": {"Kino": 8_370_000_000},
            }
        ],
    )
    summary.write_text(
        json.dumps({"decision": {"status": "publish"}, "publish_reason": "updated_or_new_amounts"}),
        encoding="utf-8",
    )

    payload = build_site_payload(loto_path=loto, kino_path=kino, summary_path=summary)

    assert payload["loto"]["sorteo"] == 5464
    assert payload["loto"]["pozos_millones"]["Loto Clásico"] == "690"
    assert payload["loto"]["total_millones"] == "790"
    assert payload["kino"]["sorteo"] == 3266
    assert payload["kino"]["pozos_millones"]["Kino"] == "8.370"
    assert payload["last_decision"]["status"] == "publish"
    # History merges both games, newest first
    assert payload["history"][0]["sorteo"] == 3266


def test_format_millones_uses_dot_thousands_separator() -> None:
    from polla_app.site import _format_millones

    assert _format_millones(8_370_000_000) == "8.370"
    assert _format_millones(14_300_000_000) == "14.300"
    assert _format_millones(690_000_000) == "690"


def test_write_site_data_creates_file(tmp_path: Path) -> None:
    loto = _write_ndjson(
        tmp_path / "loto.jsonl",
        [{"sorteo": 1, "fecha": "2026-01-01", "pozos_proximo": {"Loto": 1_000_000_000}}],
    )
    output = tmp_path / "site" / "data.json"
    write_site_data(loto_path=loto, output=output)
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["api_version"] == "v1.2"
    assert data["loto"]["pozos_clp"]["Loto"] == 1_000_000_000


def test_build_site_payload_without_kino_or_summary(tmp_path: Path) -> None:
    loto = _write_ndjson(
        tmp_path / "loto.jsonl",
        [{"sorteo": 1, "fecha": "2026-01-01", "pozos_proximo": {"Loto": 1_000_000_000}}],
    )
    payload = build_site_payload(loto_path=loto, kino_path=None, summary_path=None)
    assert payload["kino"] is None
    assert payload["last_decision"]["status"] == "unknown"


def test_build_site_payload_missing_files(tmp_path: Path) -> None:
    payload = build_site_payload(
        loto_path=tmp_path / "missing.jsonl",
        kino_path=tmp_path / "missing_kino.jsonl",
        summary_path=tmp_path / "missing.json",
    )
    assert payload["loto"] is None
    assert payload["kino"] is None
    assert payload["history"] == []


def test_build_site_payload_dedupes_and_caps_history(tmp_path: Path) -> None:
    records = [
        {"sorteo": i, "fecha": f"2026-01-{i:02d}", "pozos_proximo": {"Loto": 1_000_000_000}}
        for i in range(1, 105)
    ]
    records.append(records[0])  # duplicate of draw 1
    loto = _write_ndjson(tmp_path / "loto.jsonl", records)
    payload = build_site_payload(loto_path=loto, kino_path=None, summary_path=None)
    assert len(payload["history"]) == 100
    sorteos = [h["sorteo"] for h in payload["history"]]
    assert len(sorteos) == len(set(sorteos))


def test_build_site_payload_reuses_previous_section_when_game_missing(
    tmp_path: Path,
) -> None:
    loto = _write_ndjson(
        tmp_path / "loto.jsonl",
        [{"sorteo": 5465, "fecha": "2026-08-16", "pozos_proximo": {"Loto Clásico": 620_000_000}}],
    )
    previous = {
        "loto": {"sorteo": 5465, "pozos_clp": {"Loto Clásico": 620_000_000}},
        "kino": {"sorteo": 3266, "pozos_clp": {"Kino": 8_370_000_000}},
    }

    payload = build_site_payload(
        loto_path=loto,
        kino_path=tmp_path / "missing_kino.jsonl",
        summary_path=None,
        previous_payload=previous,
    )

    # Kino sin records -> se conserva la sección del payload anterior
    assert payload["kino"]["sorteo"] == 3266
    assert payload["loto"]["sorteo"] == 5465


def test_build_site_payload_without_previous_keeps_none(tmp_path: Path) -> None:
    loto = _write_ndjson(
        tmp_path / "loto.jsonl",
        [{"sorteo": 5465, "fecha": "2026-08-16", "pozos_proximo": {"Loto": 1}}],
    )
    payload = build_site_payload(
        loto_path=loto,
        kino_path=tmp_path / "missing_kino.jsonl",
        summary_path=None,
    )
    assert payload["kino"] is None


def test_site_cli_reuses_previous_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loto = tmp_path / "loto.jsonl"
    loto.write_text(
        json.dumps(
            {
                "sorteo": 5465,
                "fecha": "2026-08-16",
                "confidence": "full",
                "fuente": "openloto",
                "pozos_proximo": {"Loto Clásico": 620_000_000},
            }
        ),
        encoding="utf-8",
    )
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps(
            {
                "loto": {"sorteo": 5465, "pozos_clp": {"Loto Clásico": 620_000_000}},
                "kino": {"sorteo": 3266, "pozos_clp": {"Kino": 8_370_000_000}},
            }
        ),
        encoding="utf-8",
    )

    raw = _invoke_site(
        tmp_path,
        monkeypatch,
        [
            "--normalized",
            str(loto),
            "--normalized-kino",
            str(tmp_path / "missing_kino.jsonl"),
            "--previous-data",
            str(previous),
            "--output",
            str(tmp_path / "data.json"),
        ],
    )
    data = json.loads(raw)
    assert data["kino"]["sorteo"] == 3266


def test_site_cli_without_previous_keeps_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loto = tmp_path / "loto.jsonl"
    loto.write_text(
        json.dumps(
            {
                "sorteo": 5465,
                "fecha": "2026-08-16",
                "confidence": "full",
                "fuente": "openloto",
                "pozos_proximo": {"Loto Clásico": 620_000_000},
            }
        ),
        encoding="utf-8",
    )
    raw = _invoke_site(
        tmp_path,
        monkeypatch,
        [
            "--normalized",
            str(loto),
            "--normalized-kino",
            str(tmp_path / "missing_kino.jsonl"),
            "--output",
            str(tmp_path / "data.json"),
        ],
    )
    data = json.loads(raw)
    assert data["kino"] is None
    assert data["loto"]["sorteo"] == 5465


def test_site_cli_stats_failure_still_writes_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polla_app import __main__ as main_mod

    loto = tmp_path / "loto.jsonl"
    loto.write_text(
        json.dumps(
            {
                "sorteo": 5465,
                "fecha": "2026-08-16",
                "confidence": "full",
                "fuente": "openloto",
                "pozos_proximo": {"Loto Clásico": 620_000_000},
            }
        ),
        encoding="utf-8",
    )

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("csv fetch failed")

    monkeypatch.setattr(main_mod, "write_site_stats", boom)
    result = CliRunner().invoke(
        cli,
        [
            "site",
            "--normalized",
            str(loto),
            "--output",
            str(tmp_path / "data.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert data["loto"]["sorteo"] == 5465


def test_build_site_payload_history_from_state_file(tmp_path: Path) -> None:
    state_file = _write_ndjson(
        tmp_path / "last_run.jsonl",
        [
            {"sorteo": 5460, "fecha": "2026-08-10", "pozos_proximo": {"Loto Clásico": 600_000_000}},
            {"sorteo": 5462, "fecha": "2026-08-12", "pozos_proximo": {"Loto Clásico": 610_000_000}},
            {"sorteo": 5464, "fecha": "2026-08-13", "pozos_proximo": {"Loto Clásico": 620_000_000}},
        ],
    )
    loto = _write_ndjson(
        tmp_path / "loto.jsonl",
        [{"sorteo": 5462, "fecha": "2026-08-12", "pozos_proximo": {"Loto Clásico": 610_000_000}}],
    )

    payload = build_site_payload(
        loto_path=loto,
        kino_path=None,
        summary_path=None,
        state_path=state_file,
    )

    assert [h["sorteo"] for h in payload["history"]] == [5464, 5462, 5460]
    assert [h["fecha"] for h in payload["history"]] == [
        "2026-08-13",
        "2026-08-12",
        "2026-08-10",
    ]


def test_build_site_payload_state_mixed_games(tmp_path: Path) -> None:
    state_file = _write_ndjson(
        tmp_path / "last_run.jsonl",
        [
            {"sorteo": 5001, "fecha": "2026-08-01", "pozos_proximo": {"Loto Clásico": 500_000_000}},
            {"sorteo": 5002, "fecha": "2026-08-03", "pozos_proximo": {"Revancha": 80_000_000}},
            {"sorteo": 6001, "fecha": "2026-08-02", "pozos_proximo": {"Kino": 8_000_000_000}},
            {"sorteo": 6002, "fecha": "2026-08-04", "pozos_proximo": {"ReKino": 400_000_000}},
        ],
    )

    payload = build_site_payload(
        loto_path=tmp_path / "missing.jsonl",
        kino_path=tmp_path / "missing_kino.jsonl",
        summary_path=None,
        state_path=state_file,
    )

    assert len(payload["history"]) == 4
    assert {
        h["sorteo"]: h["pozos_millones"]
        for h in payload["history"]
        if "Kino" in h["pozos_millones"] or "ReKino" in h["pozos_millones"]
    } == {6002: {"ReKino": "400"}, 6001: {"Kino": "8.000"}}


def test_build_site_payload_state_tolerant_of_bad_lines(tmp_path: Path) -> None:
    state_file = tmp_path / "last_run.jsonl"
    state_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {"sorteo": 5450, "fecha": "2026-08-05", "pozos_proximo": {"Loto": 500_000_000}}
                ),
                "this is not json{{{",
                json.dumps(
                    {"sorteo": 5452, "fecha": "2026-08-08", "pozos_proximo": {"Loto": 510_000_000}}
                ),
            ]
        ),
        encoding="utf-8",
    )

    payload = build_site_payload(
        loto_path=tmp_path / "missing.jsonl",
        kino_path=None,
        summary_path=None,
        state_path=state_file,
    )

    assert [h["sorteo"] for h in payload["history"]] == [5452, 5450]


def test_site_cli_accepts_state_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loto = _write_ndjson(
        tmp_path / "loto.jsonl",
        [{"sorteo": 5465, "fecha": "2026-08-16", "pozos_proximo": {"Loto Clásico": 620_000_000}}],
    )
    state_file = _write_ndjson(
        tmp_path / "last_run.jsonl",
        [{"sorteo": 5460, "fecha": "2026-08-10", "pozos_proximo": {"Loto Clásico": 600_000_000}}],
    )

    raw = _invoke_site(
        tmp_path,
        monkeypatch,
        [
            "--normalized",
            str(loto),
            "--state-file",
            str(state_file),
            "--output",
            str(tmp_path / "data.json"),
        ],
    )
    data = json.loads(raw)
    assert data["loto"]["sorteo"] == 5465
    assert [h["sorteo"] for h in data["history"]] == [5465, 5460]
