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
        "fuente": "https://example.test/24h",
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


def test_publish_dry_run(
    normalized_file: Path, comparison_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_discrepancy_sheet_written_on_allow_quarantine(
    normalized_file: Path, comparison_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange: stub credentials/client to avoid real gspread calls
    import polla_app.publish as pub

    class MockGspread:
        class WorksheetNotFound(Exception):  # noqa: N818
            pass

    monkeypatch.setattr(pub, "gspread", MockGspread)

    class FakeWorksheet:
        def __init__(self, title: str) -> None:
            self.title = title
            self.cleared = False
            self.last_update: list[list[object]] | None = None

        def clear(self) -> None:
            self.cleared = True

        def update(self, payload: list[list[object]]) -> None:
            self.last_update = payload

    class FakeSpreadsheet:
        def __init__(self) -> None:
            self._sheets: dict[str, FakeWorksheet] = {}

        def worksheet(self, name: str) -> FakeWorksheet:
            if name not in self._sheets:
                # Simulate gspread behavior
                raise pub.gspread.WorksheetNotFound("missing")
            return self._sheets[name]

        def add_worksheet(self, title: str, rows: str, cols: str) -> FakeWorksheet:  # noqa: ARG002
            ws = FakeWorksheet(title)
            self._sheets[title] = ws
            return ws

    class FakeClient:
        def __init__(self) -> None:
            self.last_key: str | None = None
            self.spreadsheet = FakeSpreadsheet()

        def open_by_key(self, key: str) -> FakeSpreadsheet:
            self.last_key = key
            return self.spreadsheet

    fake_client = FakeClient()
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "dummy-sheet")
    monkeypatch.setattr(pub, "_load_credentials", lambda: fake_client)

    # Force publish to be disallowed so canonical sheet is skipped; still write discrepancies
    summary = {"publish": False, "decision": {"status": "skip"}}
    result = pub.publish_to_google_sheets(
        normalized_path=normalized_file,
        comparison_report_path=comparison_file,
        summary=summary,
        worksheet_name="Normalized",
        discrepancy_tab="Discrepancies",
        dry_run=False,
        force_publish=False,
        allow_quarantine=True,
    )

    # Canonical rows are skipped; discrepancy sheet receives placeholder row
    assert result["updated_rows"] == 0
    ws = fake_client.spreadsheet._sheets.get("Discrepancies")
    assert ws is not None, "Discrepancies worksheet should be created"
    assert ws.cleared is True
    expected_headers = [
        "sorteo",
        "categoria",
        "consensus",
        "disagreeing",
        "missing_sources",
    ]
    assert ws.last_update is not None
    assert ws.last_update[0] == expected_headers
    # Placeholder row uses last_draw.sorteo from report fixture (5198)
    assert ws.last_update[1][0] == 5198


def test_publish_pozos_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import polla_app.publish as pub

    record = {
        "sorteo": 5417,
        "fecha": "2026-04-26",
        "pozos_proximo": {"Loto Clásico": 140000000, "Revancha": 50000000},
    }
    normalized_path = tmp_path / "pozos.jsonl"
    normalized_path.write_text(json.dumps(record), encoding="utf-8")

    comparison_path = tmp_path / "comp.json"
    comparison_path.write_text(
        json.dumps({"decision": {"status": "publish"}, "mismatches": []}), encoding="utf-8"
    )

    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "dummy")
    result = pub.publish_to_google_sheets(
        normalized_path=normalized_path,
        comparison_report_path=comparison_path,
        summary=None,
        worksheet_name="Pozos",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=True,
    )

    rows = result["rows"]
    assert len(rows) == 2
    # Verify 4-column format: sorteo, fecha, categoria, pozo_clp
    assert rows[0] == [5417, "2026-04-26", "Loto Clásico", 140000000]
    assert rows[1] == [5417, "2026-04-26", "Revancha", 50000000]


def test_publish_multiple_records_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import polla_app.publish as pub

    # Two records
    r1 = {"sorteo": 1, "fecha": "2025-01-01", "pozos_proximo": {"Loto": 100}}
    r2 = {"sorteo": 2, "fecha": "2025-01-02", "pozos_proximo": {"Loto": 200}}

    path = tmp_path / "multi.jsonl"
    path.write_text(json.dumps(r1) + "\n" + json.dumps(r2), encoding="utf-8")

    comparison_path = tmp_path / "comp.json"
    comparison_path.write_text(
        json.dumps({"decision": {"status": "publish"}, "mismatches": []}), encoding="utf-8"
    )

    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "dummy")

    with caplog.at_level("WARNING"):
        result = pub.publish_to_google_sheets(
            normalized_path=path,
            comparison_report_path=comparison_path,
            summary=None,
            worksheet_name="Pozos",
            discrepancy_tab="Discrepancies",
            dry_run=True,
            force_publish=False,
            allow_quarantine=True,
        )

    assert "Multiple records found in normalized file (2)" in caplog.text
    # Ensure only r1 was processed
    assert result["rows"][0][0] == 1


def test_publish_with_empty_pozos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import polla_app.publish as pub

    record = {
        "sorteo": 5417,
        "fecha": "2026-04-26",
        "pozos_proximo": {},  # Empty
    }
    normalized_path = tmp_path / "empty.jsonl"
    normalized_path.write_text(json.dumps(record), encoding="utf-8")

    comparison_path = tmp_path / "comp.json"
    comparison_path.write_text(
        json.dumps({"decision": {"status": "publish"}, "mismatches": []}), encoding="utf-8"
    )

    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "dummy")
    result = pub.publish_to_google_sheets(
        normalized_path=normalized_path,
        comparison_report_path=comparison_path,
        summary=None,
        worksheet_name="Pozos",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=True,
    )

    assert result["updated_rows"] == 0
    assert result["rows"] == []
