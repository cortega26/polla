from __future__ import annotations

import json
from pathlib import Path

import pytest

from polla_app.pipeline import run_pipeline
from polla_app.publish import publish_to_google_sheets


def _is_intlike(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def test_normalized_and_report_schema_and_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polla_app import pipeline as pipeline_mod

    primary = {
        "fuente": "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/",
        "fetched_at": "2025-09-28T00:00:00+00:00",
        "montos": {"Loto Clásico": 101_000_000},
        "user_agent": "pytest",
        "estimado": True,
        "sorteo": 7001,
        "fecha": "2025-10-01",
    }
    fallback = {
        "fuente": "https://www.openloto.cl/pozo-del-loto.html",
        "fetched_at": "2025-09-28T00:00:10+00:00",
        "montos": {"Recargado": 202_000_000},
        "user_agent": "pytest",
        "estimado": True,
        "sorteo": 7001,
        "fecha": "2025-10-01",
    }
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_resultadosloto", lambda: primary)
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", lambda: fallback)

    # First run should publish
    summary1 = run_pipeline(
        sources=["pozos"],
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
        mismatch_threshold=0.5,
        include_pozos=True,
    )
    assert summary1["publish"] is True
    assert isinstance(summary1.get("api_version"), str)

    # Validate normalized record schema
    rows = [
        json.loads(line)
        for line in (tmp_path / "normalized.jsonl").read_text().splitlines()
        if line
    ]
    assert rows and isinstance(rows[0], dict)
    rec = rows[0]
    for key in ("sorteo", "fecha", "pozos_proximo", "provenance"):
        assert key in rec
    assert rec["sorteo"] == 7001
    assert isinstance(rec["pozos_proximo"], dict)
    assert _is_intlike(rec["pozos_proximo"]["Loto Clásico"]) and _is_intlike(
        rec["pozos_proximo"]["Recargado"]
    )

    # Validate comparison report schema
    report = json.loads((tmp_path / "comparison.json").read_text(encoding="utf-8"))
    assert report["decision"]["status"] in {"publish", "publish_forced", "skip"}
    assert isinstance(report.get("api_version"), str)

    # Second run (unchanged) should be idempotent -> no publish
    summary2 = run_pipeline(
        sources=["pozos"],
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
        mismatch_threshold=0.5,
        include_pozos=True,
    )
    assert summary2["publish"] is False


def test_publish_result_contract(tmp_path: Path) -> None:
    normalized = tmp_path / "n.jsonl"
    normalized.write_text(
        json.dumps({"sorteo": 1, "fecha": "2024-01-01", "premios": []}), encoding="utf-8"
    )
    comparison = tmp_path / "c.json"
    comparison.write_text(
        json.dumps(
            {"decision": {"status": "publish"}, "mismatches": [], "last_draw": {"sorteo": 1}}
        ),
        encoding="utf-8",
    )
    out = publish_to_google_sheets(
        normalized_path=normalized,
        comparison_report_path=comparison,
        summary=None,
        worksheet_name="Normalized",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=False,
    )
    for k in ("updated_rows", "discrepancy_rows", "status", "publish_allowed", "api_version"):
        assert k in out
    assert isinstance(out["api_version"], str)
