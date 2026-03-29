import json
from pathlib import Path
from typing import Any

import pytest

from polla_app.pipeline import run_pipeline


def test_consensus_agreement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app import pipeline as pipeline_mod

    def stub_fetcher(url: str, **_: Any) -> dict[str, Any]:
        return {
            "fuente": url,
            "fetched_at": "2025-01-01T00:00:00",
            "sha256": "abc",
            "montos": {"Loto": 1000},
            "sorteo": 1,
            "fecha": "2025-01-01"
        }

    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_resultadosloto", lambda **kw: stub_fetcher("res", **kw))
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", lambda **kw: stub_fetcher("open", **kw))

    summary_path = tmp_path / "summary.json"
    run_pipeline(
        sources=["pozos"],
        source_overrides={},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "norm.jsonl",
        comparison_report_path=tmp_path / "report.json",
        summary_path=summary_path,
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "log.jsonl",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.25,
        include_pozos=True
    )

    summary = json.loads(summary_path.read_text())
    assert summary["decision"]["status"] == "publish"
    assert summary["decision"]["mismatched_categories"] == 0

def test_consensus_disagreement_quarantine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app import pipeline as pipeline_mod

    def stub_res(**_: Any) -> dict[str, Any]:
        return {"fuente": "res", "montos": {"Loto": 1000}, "sorteo": 1, "fecha": "2025-01-01"}

    def stub_open(**_: Any) -> dict[str, Any]:
        return {"fuente": "open", "montos": {"Loto": 2000}, "sorteo": 1, "fecha": "2025-01-01"}

    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_resultadosloto", stub_res)
    monkeypatch.setattr(pipeline_mod.pozos_module, "get_pozo_openloto", stub_open)

    summary_path = tmp_path / "summary.json"
    run_pipeline(
        sources=["pozos"],
        source_overrides={},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "norm.jsonl",
        comparison_report_path=tmp_path / "report.json",
        summary_path=summary_path,
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "log.jsonl",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.1,
        include_pozos=True
    )

    summary = json.loads(summary_path.read_text())
    assert summary["decision"]["status"] == "quarantine"

    report = json.loads((tmp_path / "report.json").read_text())
    assert len(report["mismatches"]) == 1

def test_multi_source_majority_vote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app import pipeline as pipeline_mod
    from polla_app.pipeline import _run_ingestion_for_sources

    entries = [
        {"fuente": "s1", "montos": {"Loto": 1000}, "sorteo": 1, "fecha": "2025-01-01"},
        {"fuente": "s2", "montos": {"Loto": 1000}, "sorteo": 1, "fecha": "2025-01-01"},
        {"fuente": "s3", "montos": {"Loto": 3000}, "sorteo": 1, "fecha": "2025-01-01"},
    ]

    monkeypatch.setitem(pipeline_mod.SOURCE_LOADERS, "multi", lambda *a, **k: entries)

    summary_path = tmp_path / "summary.json"
    _run_ingestion_for_sources(
        run_id="test",
        requested_sources=["multi"],
        source_overrides={},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "norm.jsonl",
        comparison_report_path=tmp_path / "report.json",
        summary_path=summary_path,
        state_path=tmp_path / "state.jsonl",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.25,
        force_publish=False,
        log_event=lambda x: None
    )

    # Check consensus
    norm = [json.loads(line) for line in (tmp_path / "norm.jsonl").read_text().splitlines()][0]
    assert norm["pozos_proximo"]["Loto"] == 1000
