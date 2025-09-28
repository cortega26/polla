from __future__ import annotations

import json
from pathlib import Path

import pytest

from polla_app import net
from polla_app.exceptions import ConfigError, RobotsDisallowedError
from polla_app.publish import _load_credentials, publish_to_google_sheets


def test_robots_disallowed_raises_custom_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyParser:
        def can_fetch(self, ua: str, url: str) -> bool:  # noqa: ARG002
            return False

    # Force robots parser to a dummy that denies
    monkeypatch.setattr(net, "_get_robots_parser", lambda robots_url: DummyParser())

    with pytest.raises(RobotsDisallowedError) as exc:
        net.fetch_html("https://example.test/page", ua="bot", timeout=1)

    # Must also be a PermissionError for compatibility
    assert isinstance(exc.value, PermissionError)
    assert "Robots policy forbids" in str(exc.value)


def test_missing_spreadsheet_id_raises_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Prepare minimal normalized and comparison files
    normalized_file = tmp_path / "normalized.jsonl"
    normalized_file.write_text(json.dumps({"sorteo": 5198, "fecha": "2024-12-01", "premios": []}), encoding="utf-8")
    comparison_file = tmp_path / "comparison.json"
    comparison_file.write_text(
        '{"decision": {"status": "publish"}, "mismatches": [], "last_draw": {"sorteo": 5198}}',
        encoding="utf-8",
    )
    # Ensure env is clean
    monkeypatch.delenv("GOOGLE_SPREADSHEET_ID", raising=False)
    monkeypatch.delenv("GOOGLE_SHEETS_SPREADSHEET_ID", raising=False)

    # Stub credentials to avoid gspread import path
    class DummyClient:
        def open_by_key(self, key: str) -> None:  # noqa: ARG002
            raise AssertionError("should not be called when spreadsheet id missing")

    monkeypatch.setattr("polla_app.publish._load_credentials", lambda: DummyClient())

    with pytest.raises(ConfigError):
        publish_to_google_sheets(
            normalized_path=normalized_file,
            comparison_report_path=comparison_file,
            summary=None,
            worksheet_name="Normalized",
            discrepancy_tab="Discrepancies",
            dry_run=False,
            force_publish=False,
            allow_quarantine=False,
        )


def test_invalid_credentials_json_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Provide invalid JSON in env; ensure the error type and generic message
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{")
    with pytest.raises(ConfigError) as exc:
        _load_credentials()
    msg = str(exc.value)
    assert "Invalid GOOGLE_SERVICE_ACCOUNT_JSON payload" in msg
