from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from polla_app.exceptions import ParseError
from polla_app.net import FetchMetadata
from polla_app.sources.pozos import get_pozo_openloto

FIXTURES = Path(__file__).parent / "fixtures"


def _metadata(name: str, *, url: str = "https://example.test") -> FetchMetadata:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return FetchMetadata(
        url=url,
        user_agent="pytest-agent",
        fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        html=html,
    )


## Draw article parsers removed; only pozo aggregators remain.


def test_openloto_pozo(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = _metadata("openloto_pozo.html")
    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    pozos = get_pozo_openloto()

    assert pozos["montos"]["Loto Clásico"] == 690_000_000
    assert "Total estimado" not in pozos["montos"], "Totals are excluded from output"


def test_env_user_agent_override_applied_openloto(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure POLLA_USER_AGENT overrides provided UA
    ua_env = "EnvUA/2.0"
    monkeypatch.setenv("POLLA_USER_AGENT", ua_env)

    html = (FIXTURES / "openloto_pozo.html").read_text(encoding="utf-8")

    def stub_fetch_html(url: str, ua: str, timeout: int, **_: Any) -> FetchMetadata:  # noqa: ARG002
        # The UA received by fetch_html should be the env override, not the default
        assert ua == ua_env
        return FetchMetadata(
            url=url,
            user_agent=ua,
            fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            html=html,
        )

    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", stub_fetch_html)
    payload = get_pozo_openloto()
    assert payload["user_agent"] == ua_env


def test_pozo_parsing_malformed_amounts(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = _metadata("malformed_pozo.html")
    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    with pytest.raises(
        ParseError,
        match=r"Unable to parse monetary value|Empty monetary value|No valid pozo amounts",
    ):
        get_pozo_openloto()


def test_pozo_parsing_invalid_date(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = _metadata("invalid_date_pozo.html")
    monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    pozos = get_pozo_openloto()
    # Date should be None if unparseable, but it shouldn't crash the whole fetch
    # unless we decided it's a ParseError. The current impl returns None.
    # We'll stick to check it's None for now, as ParseError was requested for amounts.
    assert pozos["fecha"] is None
