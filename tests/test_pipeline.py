from __future__ import annotations

import json
from pathlib import Path

import pytest

from polla_app.pipeline import run_pipeline


def test_pozos_pipeline_produces_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub pozo fetchers
    from polla_app import pipeline as pipeline_mod

    primary = {
        "fuente": "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/",
        "fetched_at": "2025-09-28T00:00:00+00:00",
        "montos": {"Loto Clásico": 111_000_000, "Jubilazo $500.000": 222_000_000},
        "user_agent": "pytest",
        "estimado": True,
        "sorteo": 6001,
        "fecha": "2025-09-30",
    }
    fallback = {
        "fuente": "https://www.openloto.cl/pozo-del-loto.html",
        "fetched_at": "2025-09-28T00:00:10+00:00",
        "montos": {"Recargado": 333_000_000},
        "user_agent": "pytest",
        "estimado": True,
        "sorteo": 6001,
        "fecha": "2025-09-30",
    }

    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_resultadosloto", lambda: primary)
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", lambda: fallback)

    log_path = tmp_path / "run.jsonl"
    output = run_pipeline(
        sources=["pozos"],
        source_overrides={},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=log_path,
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.5,
        include_pozos=True,
    )

    assert (tmp_path / "normalized.jsonl").exists()
    assert (tmp_path / "comparison.json").exists()
    assert output["publish"] is True

    normalized_rows = [
        json.loads(line)
        for line in (tmp_path / "normalized.jsonl").read_text().splitlines()
        if line
    ]
    rec = normalized_rows[0]
    assert rec["sorteo"] == 6001
    assert rec["fecha"] == "2025-09-30"
    assert rec["pozos_proximo"]["Loto Clásico"] == 111_000_000
    assert rec["pozos_proximo"]["Recargado"] == 333_000_000

    # Ensure pozos_enriched event was emitted
    events = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    assert any(e.get("event") == "pozos_enriched" for e in events)


def test_pozos_pipeline_skip_when_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polla_app import pipeline as pipeline_mod

    primary = {
        "fuente": "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/",
        "fetched_at": "2025-09-28T00:00:00+00:00",
        "montos": {"Loto Clásico": 111_000_000},
        "user_agent": "pytest",
        "estimado": True,
        "sorteo": 6001,
        "fecha": "2025-09-30",
    }
    fallback = {
        "fuente": "https://www.openloto.cl/pozo-del-loto.html",
        "fetched_at": "2025-09-28T00:00:10+00:00",
        "montos": {"Recargado": 333_000_000},
        "user_agent": "pytest",
        "estimado": True,
        "sorteo": 6001,
        "fecha": "2025-09-30",
    }

    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_resultadosloto", lambda: primary)
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", lambda: fallback)

    state = tmp_path / "state.jsonl"
    state.write_text(
        json.dumps(
            {
                "sorteo": 6001,
                "fecha": "2025-09-30",
                "pozos_proximo": {"Loto Clásico": 111_000_000},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = run_pipeline(
        sources=["pozos"],
        source_overrides={},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=state,
        log_path=tmp_path / "run.log",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.5,
        include_pozos=True,
    )

    # Previous state only had one category; current merge adds Recargado -> should publish
    assert summary["publish"] is True


def test_openloto_only_logs_pozos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app import pipeline as pipeline_mod

    payload = {
        "fuente": "https://www.openloto.cl/pozo-del-loto.html",
        "fetched_at": "2025-09-28T00:00:10+00:00",
        "montos": {"Recargado": 333_000_000},
        "user_agent": "pytest",
        "estimado": True,
    }
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", lambda: payload)

    log_path = tmp_path / "run.jsonl"
    run_pipeline(
        sources=["openloto"],
        source_overrides={},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=log_path,
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.5,
        include_pozos=False,
    )

    events = [json.loads(line) for line in log_path.read_text().splitlines() if line]
    pozos_events = [e for e in events if e.get("event") == "pozos_enriched"]
    assert pozos_events, "Expected pozos_enriched event in openloto-only run"
    evt = pozos_events[-1]
    assert evt["source_mode"] == "openloto_only"
    assert evt["categories"]["Recargado"] == 333_000_000
