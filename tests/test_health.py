from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

from polla_app.__main__ import cli


def _invoke(args: list[str]) -> tuple[int, dict[str, Any]]:
    runner = CliRunner()
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output
    return result.exit_code, json.loads(result.output)


def test_health_offline_pass() -> None:
    _, payload = _invoke(["health"])  # offline by default
    assert payload["status"] == "pass"
    assert "python" in payload["checks"]


def test_pozos_command_error_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app import __main__ as main_mod
    from polla_app.exceptions import ParseError

    def ok_source(**_: object) -> dict[str, Any]:
        return {"montos": {"Loto Clásico": 690_000_000}}

    def failing_source(**_: object) -> None:
        raise ParseError("bad html", context={})

    monkeypatch.setattr(main_mod, "get_pozo_openloto", failing_source)

    runner = CliRunner()
    result = runner.invoke(cli, ["pozos"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["openloto"]["error"] == "ParseError"
    assert "message" in payload["openloto"]


def test_health_online_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub one source to fail, the other to succeed
    from polla_app import __main__ as main_mod

    def ok_source(**_: object) -> dict[str, Any]:
        return {"montos": {"Loto Clásico": 1}}

    def failing_source(**_: object) -> dict[str, Any]:  # noqa: ARG001
        raise RuntimeError("boom")

    monkeypatch.setattr(main_mod, "get_pozo_openloto", failing_source)

    _, payload = _invoke(["health", "--online", "--timeout", "1"])
    assert payload["status"] == "fail"
    assert payload["checks"]["sources"]["openloto"]["ok"] is False
