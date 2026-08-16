"""Hermetic CLI tests for the run, publish, and kino commands."""

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import polla_app.pipeline as pipeline_module
from polla_app import __main__ as main_mod
from polla_app.__main__ import cli
from polla_app.exceptions import ParseError

LOTO_PAYLOAD: dict[str, Any] = {
    "fuente": "https://x.test",
    "montos": {"Loto Clásico": 1_000_000_000},
    "sorteo": 5000,
    "fecha": "2026-08-15",
    "sha256": "abc",
}


def _run_args(tmp_path: Path, extra: list[str] | None = None) -> list[str]:
    """Build run-command args with all artifact paths under tmp_path."""
    args = [
        "run",
        "--raw-dir",
        str(tmp_path / "raw"),
        "--normalized",
        str(tmp_path / "n.jsonl"),
        "--comparison-report",
        str(tmp_path / "c.json"),
        "--summary",
        str(tmp_path / "s.json"),
        "--state-file",
        str(tmp_path / "st.jsonl"),
        "--log-file",
        str(tmp_path / "l.jsonl"),
        "--retries",
        "1",
        "--timeout",
        "5",
    ]
    if extra:
        args.extend(extra)
    return args


def _stub_pipeline_fetchers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the pozos loader and auxiliaries so no network is touched."""

    def loader(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], ...]:
        return (LOTO_PAYLOAD,)

    monkeypatch.setitem(pipeline_module.SOURCE_LOADERS, "pozos", loader)
    monkeypatch.setattr(pipeline_module, "_attach_prices", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_module, "notify_slack", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_module, "notify_quarantine", lambda *a, **k: None)


def test_run_ok_with_stubbed_loaders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_pipeline_fetchers(monkeypatch)
    result = CliRunner().invoke(cli, _run_args(tmp_path))
    assert result.exit_code == 0, result.output
    assert '"publish"' in result.output


def test_run_rejects_bad_retries(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, _run_args(tmp_path, ["--retries", "0"]))
    assert result.exit_code != 0
    assert "must be >= 1" in result.output


def test_run_rejects_invalid_source_url_format(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, _run_args(tmp_path, ["--source-url", "novalid"]))
    assert result.exit_code != 0
    assert "must be in the format" in result.output


def test_run_rejects_invalid_alt_source_urls_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALT_SOURCE_URLS", "{not json")
    result = CliRunner().invoke(cli, _run_args(tmp_path))
    assert result.exit_code != 0
    assert "valid JSON" in result.output


def test_run_mixed_games_rejected(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, _run_args(tmp_path, ["--sources", "pozos,kino"]))
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert "separate invocation" in str(result.exception)


def _stub_publish(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub publish_to_google_sheets in the CLI module and return captured kwargs."""
    captured: dict[str, Any] = {}

    def fake_publish(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "ok": True,
            "publish": False,
            "dry_run": True,
            "diff": "- old\n+ new",
        }

    monkeypatch.setattr(main_mod, "publish_to_google_sheets", fake_publish)
    return captured


def test_publish_requires_flags() -> None:
    result = CliRunner().invoke(cli, ["publish"])
    assert result.exit_code != 0
    assert "Missing option" in result.output


def test_publish_dry_run_prints_diff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _stub_publish(monkeypatch)
    result = CliRunner().invoke(
        cli,
        [
            "publish",
            "--dry-run",
            "--normalized",
            str(tmp_path / "n.jsonl"),
            "--comparison-report",
            str(tmp_path / "c.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "- old" in result.output
    assert "+ new" in result.output
    assert captured["dry_run"] is True


def test_publish_missing_summary_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_publish(monkeypatch)
    result = CliRunner().invoke(
        cli,
        [
            "publish",
            "--dry-run",
            "--normalized",
            str(tmp_path / "n.jsonl"),
            "--comparison-report",
            str(tmp_path / "c.json"),
            "--summary",
            str(tmp_path / "missing.json"),
        ],
    )
    assert result.exit_code == 0, result.output


def test_kino_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_mod,
        "get_pozo_kino",
        lambda *a, **k: {
            "fuente": "https://pendon-kino.loteria.cl/pendonkino",
            "montos": {"Kino": 8_000_000_000},
        },
    )
    result = CliRunner().invoke(cli, ["kino"])
    assert result.exit_code == 0, result.output
    assert '"Kino"' in result.output


def test_kino_error_emits_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ParseError("boom")

    monkeypatch.setattr(main_mod, "get_pozo_kino", failing)
    result = CliRunner().invoke(cli, ["kino"])
    assert result.exit_code == 0, result.output
    assert '"error"' in result.output
    assert "Traceback" not in result.output
