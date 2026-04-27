from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from polla_app.pipeline import run_pipeline
from polla_app.publish import publish_to_google_sheets


def test_pipeline_to_publish_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """E2E test: Run pipeline -> Run publisher -> Verify output rows."""

    # 1. Setup paths
    raw_dir = tmp_path / "raw"
    normalized_path = tmp_path / "normalized.jsonl"
    comparison_report_path = tmp_path / "report.json"
    summary_path = tmp_path / "summary.json"
    state_path = tmp_path / "state.jsonl"
    log_path = tmp_path / "run.log"

    # 2. Mock source loaders to return deterministic data with the new formats
    def mock_collect_pozos(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], ...]:
        return (
            {
                "fuente": "https://example.test/pozos",
                "fetched_at": "2026-04-27T20:00:00Z",
                "sha256": "fake-sha",
                "estimado": True,
                "montos": {"Loto Clásico": 1000000000, "Revancha": 500000000},
                "user_agent": "MockBot/1.0",
                "sorteo": 5418,
                "fecha": "2026-04-28",
            },
        )

    # We need to monkeypatch SOURCE_LOADERS in polla_app.pipeline
    import polla_app.pipeline as pipeline

    monkeypatch.setitem(pipeline.SOURCE_LOADERS, "pozos", mock_collect_pozos)

    # 3. Run Pipeline
    summary = run_pipeline(
        sources=["pozos"],
        source_overrides=None,
        raw_dir=raw_dir,
        normalized_path=normalized_path,
        comparison_report_path=comparison_report_path,
        summary_path=summary_path,
        state_path=state_path,
        log_path=log_path,
        retries=1,
        timeout=5,
        fail_fast=True,
        mismatch_threshold=0.5,
        include_pozos=True,
        force_publish=False,
    )

    assert summary["publish"] is True
    assert normalized_path.exists()

    # 4. Run Publisher (Dry Run)
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "fake-sheet-id")

    publish_result = publish_to_google_sheets(
        normalized_path=normalized_path,
        comparison_report_path=comparison_report_path,
        summary=summary,
        worksheet_name="Pozos",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=True,
    )

    # 5. Verify Publication Rows
    rows = publish_result["rows"]
    # Expect 2 rows (Loto Clásico, Revancha) + 1 header?
    # Actually publish_to_google_sheets returns the data rows in "rows" key
    assert len(rows) == 2

    # Format: [sorteo, fecha, categoria, pozo_clp]
    assert rows[0] == [5418, "2026-04-28", "Loto Clásico", 1000000000]
    assert rows[1] == [5418, "2026-04-28", "Revancha", 500000000]

    # Verify header logic indirectly by checking the mock update call would use the right header
    # (Already tested in test_publish.py, but good to have here too)
