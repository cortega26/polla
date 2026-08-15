"""Tests for the shared StealthyFetcher singleton."""

import pytest
import requests


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


def _http_error(status: int) -> requests.HTTPError:
    error = requests.HTTPError(f"HTTP {status}")
    error.response = requests.Response()
    error.response.status_code = status
    return error


def _fake_page(html: str = "<html>browser</html>") -> object:
    return type("FakePage", (), {"status": 200, "html": html, "text": html})()


def test_fetch_with_browser_fallback_on_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from polla_app.sources import browser

    def failing_fetch(*args: object, **kwargs: object) -> None:
        raise _http_error(500)

    monkeypatch.setattr(browser, "fetch_html", failing_fetch)
    monkeypatch.setattr(
        browser,
        "get_stealthy_fetcher",
        lambda: type("F", (), {"fetch": lambda self, url, timeout: _fake_page()})(),
    )

    metadata = browser.fetch_with_browser_fallback(
        "https://example.test", ua="ua", timeout=5, retries=1
    )
    assert metadata.html == "<html>browser</html>"
    assert metadata.user_agent == "Scrapling/StealthyFetcher"


def test_fetch_with_browser_fallback_no_fallback_on_4xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from polla_app.sources import browser

    calls: list[str] = []

    def failing_fetch(*args: object, **kwargs: object) -> None:
        raise _http_error(404)

    monkeypatch.setattr(browser, "fetch_html", failing_fetch)

    class FakeFetcher:
        @staticmethod
        def fetch(url: str, timeout: int) -> object:
            calls.append("browser")
            return _fake_page()

    monkeypatch.setattr(browser, "get_stealthy_fetcher", lambda: FakeFetcher())

    with pytest.raises(requests.HTTPError):
        browser.fetch_with_browser_fallback("https://example.test", ua="ua", timeout=5, retries=1)
    assert calls == []


def test_fetch_with_browser_fallback_fallback_on_any(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from polla_app.sources import browser

    def failing_fetch(*args: object, **kwargs: object) -> None:
        raise requests.Timeout("slow")

    monkeypatch.setattr(browser, "fetch_html", failing_fetch)
    monkeypatch.setattr(
        browser,
        "get_stealthy_fetcher",
        lambda: type("F", (), {"fetch": lambda self, url, timeout: _fake_page()})(),
    )

    metadata = browser.fetch_with_browser_fallback(
        "https://example.test", ua="ua", timeout=5, retries=1, fallback_on_any=True
    )
    assert metadata.html == "<html>browser</html>"
