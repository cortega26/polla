from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polla_app.net import FetchMetadata
from polla_app.pipeline import SOURCE_LOADERS, SourceResult, run_pipeline


@pytest.fixture
def fake_metadata() -> FetchMetadata:
    return FetchMetadata(
        url="https://example.test/t13",
        user_agent="pytest",
        fetched_at=datetime(2024, 12, 1, tzinfo=timezone.utc),
        html="<html></html>",
    )


def _make_record(premio_value: int) -> dict[str, object]:
    return {
        "sorteo": 5198,
        "fecha": "2024-12-01",
        "fuente": "https://example.test/t13",
        "premios": [
            {"categoria": "Loto 6 aciertos", "premio_clp": premio_value, "ganadores": 0},
            {"categoria": "Terna", "premio_clp": 1000, "ganadores": 10},
        ],
    }


def test_pipeline_produces_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_metadata: FetchMetadata
) -> None:
    source_results = {
        "t13": SourceResult("t13", "https://example.test/t13", fake_metadata, _make_record(0)),
        "24h": SourceResult("24h", "https://example.test/24h", fake_metadata, _make_record(0)),
    }

    for key, result in source_results.items():
        monkeypatch.setitem(SOURCE_LOADERS, key, lambda url, timeout, result=result: result)

    output = run_pipeline(
        sources=["all"],
        source_overrides={"t13": "https://example.test/t13", "24h": "https://example.test/24h"},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "run.log",
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.5,
        include_pozos=False,
    )

    assert (tmp_path / "raw" / "t13.json").exists()
    assert (tmp_path / "normalized.jsonl").exists()
    assert (tmp_path / "comparison.json").exists()
    assert output["publish"] is True

    normalized_rows = [
        json.loads(line)
        for line in (tmp_path / "normalized.jsonl").read_text().splitlines()
        if line
    ]
    assert normalized_rows[0]["sorteo"] == 5198


def test_pipeline_detects_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_metadata: FetchMetadata
) -> None:
    good = SourceResult("t13", "https://example.test/t13", fake_metadata, _make_record(0))
    mismatch_record = _make_record(1000)
    mismatch = SourceResult("24h", "https://example.test/24h", fake_metadata, mismatch_record)

    monkeypatch.setitem(SOURCE_LOADERS, "t13", lambda url, timeout: good)
    monkeypatch.setitem(SOURCE_LOADERS, "24h", lambda url, timeout: mismatch)

    summary = run_pipeline(
        sources=["t13", "24h"],
        source_overrides={"t13": good.url, "24h": mismatch.url},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "run.log",
        retries=1,
        timeout=5,
        fail_fast=False,
        mismatch_threshold=0.0,
        include_pozos=False,
    )

    assert summary["decision"]["status"] == "quarantine"
    report = json.loads((tmp_path / "comparison.json").read_text())
    assert report["decision"]["status"] == "quarantine"
    assert report["mismatches"], "Expected mismatches in comparison report"


def test_pipeline_skips_missing_url_and_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_metadata: FetchMetadata
) -> None:
    def _unexpected_loader(url: str, timeout: int) -> SourceResult:
        pytest.fail("t13 loader should not be invoked when URL is missing")

    success = SourceResult("24h", "https://example.test/24h", fake_metadata, _make_record(0))

    monkeypatch.setitem(SOURCE_LOADERS, "t13", _unexpected_loader)
    monkeypatch.setitem(SOURCE_LOADERS, "24h", lambda url, timeout: success)

    summary = run_pipeline(
        sources=["t13", "24h"],
        source_overrides={"24h": success.url},
        raw_dir=tmp_path / "raw",
        normalized_path=tmp_path / "normalized.jsonl",
        comparison_report_path=tmp_path / "comparison.json",
        summary_path=tmp_path / "summary.json",
        state_path=tmp_path / "state.jsonl",
        log_path=tmp_path / "run.log",
        retries=1,
        timeout=5,
        fail_fast=False,
        mismatch_threshold=0.5,
        include_pozos=False,
    )

    assert summary["publish"] is True
    report = json.loads((tmp_path / "comparison.json").read_text())
    assert report["decision"]["status"] == "publish"
    assert report["sources"].keys() == {"24h"}
    assert report["failures"] == [
        {"source": "t13", "url": None, "error": "Source skipped: missing URL"}
    ]


def test_pipeline_missing_url_fail_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_metadata: FetchMetadata
) -> None:
    def _unexpected_loader(url: str, timeout: int) -> SourceResult:
        pytest.fail("t13 loader should not be invoked when URL is missing")

    success = SourceResult("24h", "https://example.test/24h", fake_metadata, _make_record(0))

    monkeypatch.setitem(SOURCE_LOADERS, "t13", _unexpected_loader)
    monkeypatch.setitem(SOURCE_LOADERS, "24h", lambda url, timeout: success)

    with pytest.raises(RuntimeError, match="No URL configured for source 't13'"):
        run_pipeline(
            sources=["t13", "24h"],
            source_overrides={"24h": success.url},
            raw_dir=tmp_path / "raw",
            normalized_path=tmp_path / "normalized.jsonl",
            comparison_report_path=tmp_path / "comparison.json",
            summary_path=tmp_path / "summary.json",
            state_path=tmp_path / "state.jsonl",
            log_path=tmp_path / "run.log",
            retries=1,
            timeout=5,
            fail_fast=True,
            mismatch_threshold=0.5,
            include_pozos=False,
        )
