"""Tests for retry behaviour, state rotation and the publish lock."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import requests

from polla_app.exceptions import PublishError
from polla_app.net import fetch_html
from polla_app.pipeline import MAX_STATE_RECORDS, _persist_state


def _fail_once(failures: list[Any], exc: Exception) -> Callable[..., requests.Response]:
    """Return a helper that raises once then succeeds."""

    def inner(*args: Any, **kwargs: Any) -> requests.Response:
        if not failures:
            response = requests.Response()
            response.status_code = 200
            response._content = b"<html>ok</html>"
            return response
        failures.pop(0)
        raise exc

    return inner


def test_fetch_html_retries_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    state: list[Any] = [requests.exceptions.Timeout("slow")]
    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type("S", (), {"get": _fail_once(state, requests.exceptions.Timeout("slow"))})(),
    )

    # backoff capped at 300s; use a tiny factor via env to keep the test fast
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"


def test_fetch_html_retries_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    state: list[Any] = [requests.exceptions.ConnectionError("refused")]
    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type(
            "S", (), {"get": _fail_once(state, requests.exceptions.ConnectionError("refused"))}
        )(),
    )
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"


def test_fetch_html_exhausts_retries_on_persistent_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    errors: list[Any] = [requests.exceptions.Timeout("slow") for _ in range(4)]

    def always_timeout(*args: Any, **kwargs: Any) -> requests.Response:
        errors.pop(0)
        raise requests.exceptions.Timeout("slow")

    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type("S", (), {"get": always_timeout})(),
    )
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    with pytest.raises(requests.exceptions.Timeout):
        fetch_html("https://example.test", "ua", timeout=5, retries=2)


def test_fetch_html_retries_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    error = requests.HTTPError("Service Unavailable")
    error.response = requests.Response()
    error.response.status_code = 503
    state: list[Any] = [error]

    def fail_once(*args: Any, **kwargs: Any) -> requests.Response:
        if state:
            state.pop(0)
            raise error
        response = requests.Response()
        response.status_code = 200
        response._content = b"<html>ok</html>"
        return response

    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type("S", (), {"get": fail_once})(),
    )
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"


def test_fetch_html_retries_on_500(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    error = requests.HTTPError("Internal Server Error")
    error.response = requests.Response()
    error.response.status_code = 500
    state: list[Any] = [error]

    def fail_once(*args: Any, **kwargs: Any) -> requests.Response:
        if state:
            state.pop(0)
            raise error
        response = requests.Response()
        response.status_code = 200
        response._content = b"<html>ok</html>"
        return response

    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type("S", (), {"get": fail_once})(),
    )
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"


def test_fetch_html_fails_fast_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    error = requests.HTTPError("Not Found")
    error.response = requests.Response()
    error.response.status_code = 404

    def always_404(*args: Any, **kwargs: Any) -> requests.Response:
        raise error

    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type("S", (), {"get": always_404})(),
    )
    with pytest.raises(requests.HTTPError):
        fetch_html("https://example.test", "ua", timeout=5, retries=3)


def test_persist_state_dedupes_by_sorteo_and_caps(tmp_path: Path) -> None:
    state_path = tmp_path / "state.jsonl"
    previous: list[dict[str, Any]] = []

    # Simulate MAX_STATE_RECORDS + 5 unique draws, then re-run the same draw
    for i in range(MAX_STATE_RECORDS + 5):
        previous = (
            json.loads("[" + ",".join(state_path.read_text().splitlines()) + "]")
            if state_path.exists()
            else previous
        )
        _persist_state(
            state_path, previous, {"sorteo": 1000 + i, "fecha": f"2025-01-{i % 28 + 1:02d}"}
        )
        previous = [json.loads(line) for line in state_path.read_text().splitlines()]

    lines = [json.loads(line) for line in state_path.read_text().splitlines()]
    assert len(lines) == MAX_STATE_RECORDS
    assert lines[-1]["sorteo"] == 1000 + MAX_STATE_RECORDS + 4

    # Re-persisting the same draw replaces it (no duplicates)
    _persist_state(
        state_path,
        [json.loads(line) for line in state_path.read_text().splitlines()],
        {"sorteo": 1000 + MAX_STATE_RECORDS + 4, "fecha": "2025-01-04"},
    )
    lines = [json.loads(line) for line in state_path.read_text().splitlines()]
    assert len(lines) == MAX_STATE_RECORDS


def test_publish_lock_acquired_and_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import polla_app.publish as pub

    lock_path = tmp_path / "publish.lock"
    monkeypatch.setenv("POLLA_PUBLISH_LOCK_PATH", str(lock_path))
    monkeypatch.setenv("POLLA_PUBLISH_LOCK_TIMEOUT", "5")

    with pub._PublishLock():
        assert lock_path.exists()
        # A second lock on the same path must time out while the first is held
        with pytest.raises(PublishError, match="Timed out waiting for publish lock"):
            with pub._PublishLock():
                pass

    # After release, the lock can be acquired again
    with pub._PublishLock():
        pass
