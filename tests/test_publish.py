from __future__ import annotations

import json
from pathlib import Path

import pytest

from polla_app.publish import publish_to_google_sheets


@pytest.fixture
def normalized_file(tmp_path: Path) -> Path:
    record = {
        "sorteo": 5198,
        "fecha": "2024-12-01",
        "fuente": "https://example.test/t13",
        "premios": [
            {"categoria": "Loto 6 aciertos", "premio_clp": 0, "ganadores": 0},
        ],
    }
    path = tmp_path / "normalized.jsonl"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


@pytest.fixture
def comparison_file(tmp_path: Path) -> Path:
    payload = {
        "decision": {"status": "publish", "total_categories": 1, "mismatched_categories": 0},
        "mismatches": [],
        "last_draw": {"sorteo": 5198},
    }
    path = tmp_path / "comparison.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_publish_dry_run(normalized_file: Path, comparison_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "dummy")
    result = publish_to_google_sheets(
        normalized_path=normalized_file,
        comparison_report_path=comparison_file,
        summary=None,
        worksheet_name="Normalized",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=True,
    )

    assert result["updated_rows"] == 0
    assert result["discrepancy_rows"] == 0
