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


def _ok(*_: Any, **__: Any) -> requests.Response:
    """Return a plain 200 response for success-path tests."""

    response = requests.Response()
    response.status_code = 200
    response._content = b"<html>ok</html>"
    return response


def _fake_session(get: Callable[..., requests.Response]) -> Any:
    """Build a fake session whose ``get`` is the given callable."""
    return type("S", (), {"get": get})()


@pytest.fixture(autouse=True)
def _restore_module_session() -> Any:
    """Restore the module-level session after each test."""
    import polla_app.net as net_mod

    original = net_mod._SESSION
    yield
    net_mod._SESSION = original


def test_fetch_html_rate_limits_same_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    monkeypatch.setattr("polla_app.net._SESSION", _fake_session(_ok))
    monkeypatch.setattr(fetch_html, "_last_seen", {}, raising=False)
    monkeypatch.setenv("POLLA_RATE_LIMIT_RPS", "2")

    clock: dict[str, float] = {"now": 0.0}

    def fake_monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr("polla_app.net.monotonic", fake_monotonic)

    recorded_sleeps: list[float] = []

    def recorder(delay: float) -> None:
        recorded_sleeps.append(delay)

    monkeypatch.setattr("polla_app.net.time.sleep", recorder)

    fetch_html("https://a.test/1", "ua")
    clock["now"] = 0.1
    fetch_html("https://a.test/2", "ua")

    assert len(recorded_sleeps) == 1
    assert recorded_sleeps[0] == pytest.approx(0.5 - 0.1)


def test_fetch_html_rate_limit_does_not_space_different_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    monkeypatch.setattr("polla_app.net._SESSION", _fake_session(_ok))
    monkeypatch.setattr(fetch_html, "_last_seen", {}, raising=False)
    monkeypatch.setenv("POLLA_RATE_LIMIT_RPS", "2")

    clock: dict[str, float] = {"now": 0.0}

    def fake_monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr("polla_app.net.monotonic", fake_monotonic)

    recorded_sleeps: list[float] = []

    def recorder(delay: float) -> None:
        recorded_sleeps.append(delay)

    monkeypatch.setattr("polla_app.net.time.sleep", recorder)

    fetch_html("https://a.test/1", "ua")
    clock["now"] = 0.1
    fetch_html("https://b.test/1", "ua")

    assert recorded_sleeps == []


def test_fetch_html_rate_limit_ignores_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    monkeypatch.setattr("polla_app.net._SESSION", _fake_session(_ok))
    monkeypatch.setattr(fetch_html, "_last_seen", {}, raising=False)
    monkeypatch.setenv("POLLA_RATE_LIMIT_RPS", "abc")

    clock: dict[str, float] = {"now": 0.0}

    def fake_monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr("polla_app.net.monotonic", fake_monotonic)

    recorded_sleeps: list[float] = []

    def recorder(delay: float) -> None:
        recorded_sleeps.append(delay)

    monkeypatch.setattr("polla_app.net.time.sleep", recorder)

    fetch_html("https://a.test/1", "ua")
    clock["now"] = 0.1
    fetch_html("https://a.test/2", "ua")

    assert recorded_sleeps == []


def test_fetch_html_rate_limit_state_lives_on_function_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    monkeypatch.setattr("polla_app.net._SESSION", _fake_session(_ok))
    monkeypatch.setattr(fetch_html, "_last_seen", {}, raising=False)
    monkeypatch.setenv("POLLA_RATE_LIMIT_RPS", "2")

    clock: dict[str, float] = {"now": 0.0}

    def fake_monotonic() -> float:
        return clock["now"]

    monkeypatch.setattr("polla_app.net.monotonic", fake_monotonic)

    recorded_sleeps: list[float] = []

    def recorder(delay: float) -> None:
        recorded_sleeps.append(delay)

    monkeypatch.setattr("polla_app.net.time.sleep", recorder)

    fetch_html("https://a.test/page", "ua")

    last_seen = getattr(fetch_html, "_last_seen", {})
    assert isinstance(last_seen, dict)
    assert "a.test" in last_seen


def test_fetch_html_retries_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    state: list[Any] = [requests.exceptions.Timeout("slow")]
    monkeypatch.setattr(
        "polla_app.net._SESSION",
        _fake_session(_fail_once(state, requests.exceptions.Timeout("slow"))),
    )

    # backoff capped at 300s; use a tiny factor via env to keep the test fast
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"


def test_fetch_html_retries_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    state: list[Any] = [requests.exceptions.ConnectionError("refused")]
    monkeypatch.setattr(
        "polla_app.net._SESSION",
        _fake_session(_fail_once(state, requests.exceptions.ConnectionError("refused"))),
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
        "polla_app.net._SESSION",
        _fake_session(always_timeout),
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
        "polla_app.net._SESSION",
        _fake_session(fail_once),
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
        "polla_app.net._SESSION",
        _fake_session(fail_once),
    )
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"


@pytest.mark.parametrize("status", [429, 502, 504])
def test_fetch_html_retries_on_transient_status(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    error = requests.HTTPError("Transient error")
    error.response = requests.Response()
    error.response.status_code = status
    state: list[Any] = [error]

    def fail_once(*args: Any, **kwargs: Any) -> requests.Response:
        if state:
            state.pop(0)
            raise error
        return _ok()

    monkeypatch.setattr(
        "polla_app.net._SESSION",
        _fake_session(fail_once),
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
        "polla_app.net._SESSION",
        _fake_session(always_404),
    )
    with pytest.raises(requests.HTTPError):
        fetch_html("https://example.test", "ua", timeout=5, retries=3)


def test_fetch_html_closes_failed_response_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    closed: list[Any] = []

    class FakeResponse:
        status_code = 503

        def close(self) -> None:
            closed.append(self)

    error = requests.HTTPError("Service Unavailable")
    error.response = FakeResponse()  # type: ignore[assignment]

    def fail_once(*args: Any, **kwargs: Any) -> requests.Response:
        if closed:
            response = requests.Response()
            response.status_code = 200
            response._content = b"<html>ok</html>"
            return response
        raise error

    monkeypatch.setattr("polla_app.net._SESSION", _fake_session(fail_once))
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"
    assert len(closed) == 1


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
