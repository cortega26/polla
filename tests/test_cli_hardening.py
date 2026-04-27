from pathlib import Path

import pytest

from polla_app import publish


def test_dry_run_diff_calculation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Setup mock data files
    norm_file = tmp_path / "normalized.jsonl"
    norm_file.write_text('{"pozos_proximo": {"Loto": 1000}, "fuente": "A"}\n')

    comp_file = tmp_path / "comparison.json"
    comp_file.write_text('{"decision": {"status": "publish"}, "mismatches": []}')

    # Mock current sheet values
    # Return different values to force a diff
    class MockWorksheet:
        def get_all_values(self) -> list[list[str]]:
            return [["sorteo", "fecha", "categoria", "pozo_clp"], ["None", "None", "Loto", "900"]]

    class MockSpreadsheet:
        def worksheet(self, name: str) -> MockWorksheet:
            return MockWorksheet()

    class MockClient:
        def open_by_key(self, key: str) -> MockSpreadsheet:
            return MockSpreadsheet()

    # Mock credentials and spreadsheet ID
    monkeypatch.setattr(publish, "_load_credentials", lambda: MockClient())
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "mock-id")

    result = publish.publish_to_google_sheets(
        normalized_path=norm_file,
        comparison_report_path=comp_file,
        summary=None,
        worksheet_name="Normalized",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=True,
    )

    assert "diff" in result
    assert "current_sheet" not in result["diff"]  # We named it sheet:Normalized
    assert "sheet:Normalized" in result["diff"]
    # Check that it identifies the change from 900 to 1000
    assert "-None, None, Loto, 900" in result["diff"]
    assert "+None, None, Loto, 1000" in result["diff"]


def test_dry_run_no_diff_if_equal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    norm_file = tmp_path / "normalized.jsonl"
    norm_file.write_text('{"pozos_proximo": {"Loto": 1000}, "fuente": "A"}\n')
    comp_file = tmp_path / "comparison.json"
    comp_file.write_text('{"decision": {"status": "publish"}, "mismatches": []}')

    class MockWorksheet:
        def get_all_values(self) -> list[list[str]]:
            return [["sorteo", "fecha", "categoria", "pozo_clp"], ["None", "None", "Loto", "1000"]]

    class MockSpreadsheet:
        def worksheet(self, name: str) -> MockWorksheet:
            return MockWorksheet()

    class MockClient:
        def open_by_key(self, key: str) -> MockSpreadsheet:
            return MockSpreadsheet()

    monkeypatch.setattr(publish, "_load_credentials", lambda: MockClient())
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "mock-id")

    result = publish.publish_to_google_sheets(
        normalized_path=norm_file,
        comparison_report_path=comp_file,
        summary=None,
        worksheet_name="Normalized",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=True,
    )

    # Unified diff of identical files is empty string but we show a helper message
    assert result["diff"] == "(No changes detected against the current sheet)"
