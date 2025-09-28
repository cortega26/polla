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


def test_pozos_pipeline_applies_source_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polla_app import pipeline as pipeline_mod

    res_override = "https://override.example/resultados"
    open_override = "https://override.example/openloto"

    def stub_resultados(url: str = "https://default.resultados/", **_: object) -> dict[str, object]:
        return {
            "fuente": url,
            "fetched_at": "2025-09-28T00:00:00+00:00",
            "montos": {"Loto Clásico": 101_000_000},
            "user_agent": "pytest",
            "estimado": True,
            "sorteo": 7001,
            "fecha": "2025-10-01",
        }

    def stub_openloto(url: str = "https://default.openloto/", **_: object) -> dict[str, object]:
        return {
            "fuente": url,
            "fetched_at": "2025-09-28T00:00:10+00:00",
            "montos": {"Recargado": 202_000_000},
            "user_agent": "pytest",
            "estimado": True,
            "sorteo": 7001,
            "fecha": "2025-10-01",
        }

    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_resultadosloto", stub_resultados)
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", stub_openloto)

    run_pipeline(
        sources=["pozos"],
        source_overrides={
            "resultadoslotochile": res_override,
            "openloto": open_override,
        },
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "run.jsonl",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.5,
        include_pozos=True,
    )

    # Read normalized record
    record = json.loads((tmp_path / "normalized.jsonl").read_text().splitlines()[0])
    assert record["fuente"] == res_override
    assert record["pozos_proximo"]["Loto Clásico"] == 101_000_000
    assert record["pozos_proximo"]["Recargado"] == 202_000_000
    prov = record.get("provenance", {}).get("pozos", {})
    assert prov.get("primary", {}).get("fuente") == res_override
    assert prov.get("alternatives", [])[0].get("fuente") == open_override


def test_openloto_only_uses_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app import pipeline as pipeline_mod

    open_override = "https://override.example/openloto"

    def stub_openloto(url: str = "https://default.openloto/", **_: object) -> dict[str, object]:
        return {
            "fuente": url,
            "fetched_at": "2025-09-28T00:00:10+00:00",
            "montos": {"Recargado": 303_000_000},
            "user_agent": "pytest",
            "estimado": True,
        }

    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", stub_openloto)

    run_pipeline(
        sources=["openloto"],
        source_overrides={"openloto": open_override},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "run.jsonl",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.5,
        include_pozos=False,
    )

    # Verify raw payload wrote the override URL
    raw_payload = json.loads((tmp_path / "raw" / "openloto.json").read_text(encoding="utf-8"))
    assert raw_payload["fuente"] == open_override
