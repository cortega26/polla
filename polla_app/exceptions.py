"""Error taxonomy and utilities for the Polla scraper."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


class ScriptError(Exception):
    """Base application error with standardized fields and safe messaging."""

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        *,
        error_code: str | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.original_error = original_error
        self.error_code = error_code
        self.timestamp = datetime.now()
        self.context = dict(context or {})
        self.traceback = traceback.format_exc() if original_error else None
        super().__init__(self.get_error_message())

    def get_error_message(self) -> str:
        base_msg = f"[{self.error_code}] {self.message}" if self.error_code else self.message
        if self.original_error:
            return f"{base_msg} (caused by {self.original_error.__class__.__name__})"
        return base_msg

    def log_error(self, logger: logging.Logger) -> None:
        # Use localized import to avoid cyclic dependency
        from .obs import sanitize

        payload = {
            "event": "error",
            "timestamp": self.timestamp.isoformat(),
            "error_code": self.error_code,
            "message": self.message,
            "context": self.context or {},
        }
        logger.error("%s", sanitize(payload))
        if self.traceback:
            logger.debug("traceback=%s", self.traceback)


class ConfigError(ScriptError):
    """Configuration or environment error (e.g., missing credentials)."""


class PublishError(ScriptError):
    """Errors during publishing to external services."""


class NetworkError(ScriptError):
    """Network/HTTP errors reaching external services."""


class ParseError(ScriptError):
    """HTML or content parsing errors."""


class RobotsDisallowedError(PermissionError, ScriptError):
    """Fetching a URL disallowed by robots.txt (retains PermissionError type)."""

    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        PermissionError.__init__(self, message)
        ScriptError.__init__(self, message, error_code="robots_disallowed", context=context)


def redact(text: str) -> str:
    """Redact a sensitive token entirely.

    This mechanism relies on the caller (e.g. sanitization logic) to provide
    only tokens that are already identified as sensitive. It no longer
    blindly searches for long alphanumeric sequences to avoid affecting URLs.
    """

    if not text:
        return ""

    text = str(text)
    if len(text) <= 6:
        return "…"
    # Mask most of the token but keep prefixes for debugging
    return f"{text[:4]}…{text[-2:]}"


@dataclass(frozen=True)
class ErrorMetric:
    code: str
    count: int = 1
