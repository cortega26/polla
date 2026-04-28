import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from polla_app.notifiers import notify_quarantine, notify_slack
from polla_app.publish import publish_to_google_sheets


def test_publish_dry_run_includes_rows(tmp_path: Path) -> None:
    normalized_path = tmp_path / "normalized.jsonl"
    record = {
        "sorteo": 1,
        "fecha": "2025-01-01",
        "fuente": "http://example.com",
        "pozos_proximo": {"Loto": 1000},
        "premios": [],
    }
    normalized_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    report_path = tmp_path / "report.json"
    report = {
        "decision": {"status": "publish"},
        "mismatches": [{"categoria": "Loto", "consensus": {}, "disagreeing": {}}],
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = publish_to_google_sheets(
        normalized_path=normalized_path,
        comparison_report_path=report_path,
        summary=None,
        worksheet_name="Test",
        discrepancy_tab="Discrepancies",
        dry_run=True,
        force_publish=False,
        allow_quarantine=False,
    )

    assert "rows" in result
    assert result["rows"] == [[1, "2025-01-01", "Loto", 1000]]
    assert "mismatch_rows" in result
    assert len(result["mismatch_rows"]) == 1


def test_slack_notifier_skips_without_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    notify_slack({"status": "publish"})
    assert "Slack notification sent" not in caplog.text


def test_slack_notifier_handles_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://invalid")
    import requests

    def mock_post(*args: Any, **kwargs: Any) -> MagicMock:
        raise requests.exceptions.ConnectionError("Failed")

    monkeypatch.setattr(requests, "post", mock_post)

    with caplog.at_level("WARNING"):
        notify_slack({"status": "publish"})
    assert "Failed to send Slack" in caplog.text


def test_health_online_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    from polla_app.__main__ import cli

    def stub_fetcher(**_: Any) -> dict[str, Any]:
        return {"montos": {"Loto": 1000}}  # Within sane range

    monkeypatch.setattr("polla_app.__main__.get_pozo_openloto", stub_fetcher)
    monkeypatch.setattr("polla_app.__main__.get_pozo_polla", stub_fetcher)

    runner = CliRunner()
    result = runner.invoke(cli, ["health", "--online"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "pass"


def test_health_online_validation_insane_range(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    from polla_app.__main__ import cli

    def stub_fetcher(**_: Any) -> dict[str, Any]:
        return {"montos": {"Loto": 60_000_000_000}}  # Insane range (> 50,000 MM)

    monkeypatch.setattr("polla_app.__main__.get_pozo_openloto", stub_fetcher)
    monkeypatch.setattr("polla_app.__main__.get_pozo_polla", stub_fetcher)

    runner = CliRunner()
    result = runner.invoke(cli, ["health", "--online"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "fail"
    assert data["checks"]["sources"]["openloto"]["error"] == "amounts_out_of_range"


def test_notify_quarantine_sends_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://mock-slack")
    import requests

    captured_payload: dict[str, Any] = {}

    def mock_post(url: str, json: dict[str, Any], timeout: int = 10) -> MagicMock:
        nonlocal captured_payload
        captured_payload = json
        mock = MagicMock()
        mock.status_code = 200
        mock.raise_for_status = MagicMock()
        return mock

    monkeypatch.setattr(requests, "post", mock_post)

    summary = {
        "run_id": "test-run",
        "publish_reason": "mismatch_detected",
        "decision": {"status": "quarantine"},
    }
    mismatches = [
        {
            "categoria": "Loto",
            "consensus": {"1000": ["source1"]},
            "missing_sources": ["source2"],
        }
    ]

    notify_quarantine(summary, mismatches)

    assert "blocks" in captured_payload
    blocks = captured_payload["blocks"]
    assert any("Quarantine Alert" in str(b) for b in blocks)
    assert any("test-run" in str(b) for b in blocks)
    assert any("Loto" in str(b) for b in blocks)
    assert any("Missing: source2" in str(b) for b in blocks)
