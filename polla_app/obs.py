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

    sensitive_tokens = ("password", "secret", "token", "credential", "apikey", "api_key")
    if any(tok in key_l for tok in sensitive_tokens):
        return True

    # Exact or anchored match for "key" to avoid redacting "monkey", "jockey", etc.
    return key_l == "key" or key_l.startswith("key_") or key_l.endswith("_key") or "_key_" in key_l


_SENSITIVE_QUERY_PARAMS = (
    "token",
    "key",
    "apikey",
    "api_key",
    "sig",
    "signature",
    "credential",
    "password",
    "secret",
    "auth",
    "session",
    "access_token",
)


def _redact_url_query(value: str) -> str:
    """Redact sensitive query/fragment params from a URL (host/path kept)."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return value
        query = parse_qsl(parts.query, keep_blank_values=True)
        redacted = [
            (k, "<redacted>" if k.lower() in _SENSITIVE_QUERY_PARAMS else v) for k, v in query
        ]
        fragment = parts.fragment
        if fragment:
            frag_parts = parse_qsl(fragment, keep_blank_values=True)
            frag_redacted = [
                (k, "<redacted>" if k.lower() in _SENSITIVE_QUERY_PARAMS else v)
                for k, v in frag_parts
            ]
            fragment = urlencode(frag_redacted, safe="<>")
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(redacted, safe="<>"), fragment)
        )
    except Exception:
        return value


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
                if isinstance(v, str) and v.startswith(("http://", "https://")):
                    result[k] = _redact_url_query(v)
                else:
                    result[k] = sanitize(v)
        return result
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
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


def metric(
    name: str,
    log: Callable[[dict[str, Any]], None],
    *,
    kind: str = "counter",
    value: int | float = 1,
    tags: Mapping[str, Any] | None = None,
) -> None:
    """Emit a simple metric event via the structured log stream."""

    payload: dict[str, Any] = {"event": "metric", "name": name, "kind": kind, "value": value}
    if tags:
        payload["tags"] = dict(tags)
    log(payload)
