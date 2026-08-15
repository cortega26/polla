"""Tests for the shared StealthyFetcher singleton."""

import pytest


def test_get_stealthy_fetcher_returns_same_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app.sources import browser

    instances: list[object] = []

    class FakeFetcher:
        def __init__(self, **kwargs: object) -> None:
            instances.append(self)

    monkeypatch.setattr(browser, "_fetcher", None)
    monkeypatch.setattr("scrapling.StealthyFetcher", FakeFetcher)

    first = browser.get_stealthy_fetcher()
    second = browser.get_stealthy_fetcher()

    assert first is second
    assert len(instances) == 1
