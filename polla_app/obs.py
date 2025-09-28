"""Lightweight observability utilities: correlation, spans, metrics, redaction.

This module avoids external dependencies to keep the project minimal.
It provides:
- Correlation ID context storage
- A span context manager that logs start/end with timing
- A sanitizer that redacts sensitive fields
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .exceptions import redact

_CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(value: str | None) -> None:
    _CORRELATION_ID.set(value)


def get_correlation_id() -> str | None:
    return _CORRELATION_ID.get()


def _should_redact_key(key: str) -> bool:
    key_l = key.lower()
    if key_l in {"fuente", "source", "url"}:  # URLs are safe in this context
        return False
    return any(tok in key_l for tok in ("password", "secret", "token", "credential", "apikey", "api_key", "key"))


def sanitize(obj: Any) -> Any:
    """Recursively sanitize payloads by redacting sensitive tokens.

    - Redacts values for keys that look sensitive
    - Applies token redaction to long alphanumeric strings
    """

    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if _should_redact_key(str(k)):
                if isinstance(v, str):
                    result[k] = redact(v)
                else:
                    result[k] = "<redacted>"
            else:
                result[k] = sanitize(v)
        return result
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj


@contextmanager
def span(
    name: str,
    log: Callable[[dict[str, Any]], None],
    *,
    attrs: Mapping[str, Any] | None = None,
) -> Any:
    """Minimal span that logs start/end with elapsed time in ms.

    Usage:
        with span("pozos_only", log_event, attrs={"sources": ["pozos"]}):
            ...
    """

    start = time.monotonic()
    payload: dict[str, Any] = {"event": "span_start", "name": name}
    if attrs:
        payload["attrs"] = dict(attrs)
    log(payload)
    try:
        yield
    finally:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        end_payload: dict[str, Any] = {"event": "span_end", "name": name, "ms": elapsed_ms}
        log(end_payload)


def metric(name: str, log: Callable[[dict[str, Any]], None], *, kind: str = "counter", value: int | float = 1, tags: Mapping[str, Any] | None = None) -> None:
    """Emit a simple metric event via the structured log stream."""

    payload: dict[str, Any] = {"event": "metric", "name": name, "kind": kind, "value": value}
    if tags:
        payload["tags"] = dict(tags)
    log(payload)
