"""HTTP helpers for fetching lottery data politely."""

import hashlib
import logging
import os
import random
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from time import monotonic
from typing import Final
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests

from .exceptions import RobotsDisallowedError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchMetadata:
    """Metadata returned alongside fetched HTML content."""

    url: str
    user_agent: str
    fetched_at: datetime
    html: str

    @property
    def sha256(self) -> str:
        """Return the SHA-256 digest of the response body."""
        return hashlib.sha256(self.html.encode("utf-8")).hexdigest()


@lru_cache(maxsize=64)
def _get_robots_parser(robots_url: str, ua: str) -> RobotFileParser | None:
    parser = RobotFileParser()
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=10) as response:
            lines = [line.decode("utf-8", errors="ignore") for line in response.readlines()]
        parser.set_url(robots_url)
        parser.parse(lines)
    except Exception as exc:  # pragma: no cover - network/IO edge cases
        LOGGER.warning("Failed to read robots.txt from %s: %s", robots_url, exc)
        return None
    return parser


def _robots_allowed(url: str, ua: str) -> bool:
    """Check whether the given URL is allowed by robots.txt.

    The function is deliberately forgiving: if robots.txt cannot be fetched we
    default to allowing the request but emit a log entry so the operator can
    inspect it manually.
    """

    parsed = urlparse(url)
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    parser = _get_robots_parser(robots_url, ua)
    if parser is None:
        return True
    allowed = parser.can_fetch(ua, url)
    if not allowed:
        LOGGER.warning("robots.txt forbids %s for UA %s", url, ua)
    return allowed


def _calculate_backoff(attempt: int, factor: float, max_seconds: float) -> float:
    """Calculate exponential backoff with jitter.

    Uses the formula: (factor * 2^(attempt-1)) + jitter.
    """
    delay = factor * (2 ** (attempt - 1))
    # Add up to 25% jitter
    jitter = random.uniform(0, 0.25 * delay)
    return float(min(delay + jitter, max_seconds))


# Exceptions worth retrying: rate limiting, transient timeouts and dropped
# connections. Everything else (4xx, TLS, malformed responses) fails fast.
_RETRYABLE_EXC = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)

# HTTP status codes worth retrying with backoff (transient server errors).
_RETRYABLE_STATUS = (429, 502, 503, 504)


def fetch_html(
    url: str,
    ua: str,
    timeout: int = 20,
    *,
    retries: int | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> FetchMetadata:
    """GET ``url`` with a descriptive UA and return the body plus metadata.

    Supports exponential backoff with jitter for retryable failures:
    HTTP 429 (rate limit), timeouts and dropped connections.
    Retries and backoff factor are configurable via POLLA_MAX_RETRIES and
    POLLA_BACKOFF_FACTOR. If ``retries`` is provided it takes precedence over the
    environment variable. ``extra_headers`` are merged on top of the defaults
    (e.g. Sec-Fetch-* for sources that require browser-like framing).
    """

    session = requests.Session()
    headers = {
        "User-Agent": ua,
        "Accept-Language": "es-CL,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
    }
    if extra_headers:
        headers.update(extra_headers)

    if not _robots_allowed(url, ua):
        raise RobotsDisallowedError(
            "Robots policy forbids fetching URL",
            context={"url": url, "ua": ua},
        )

    last_seen: dict[str, float] = getattr(fetch_html, "_last_seen", {})
    rate_limit_env: Final[str] = "POLLA_RATE_LIMIT_RPS"

    def _rate_limit_if_needed() -> None:
        rps = os.getenv(rate_limit_env)
        if not rps:
            return
        try:
            limit = float(rps)
        except ValueError:
            return
        if limit <= 0:
            return
        min_interval = 1.0 / limit
        host = urlparse(url).netloc
        last = last_seen.get(host)
        now = monotonic()
        if last is not None:
            delta = now - last
            if delta < min_interval:
                time.sleep(min_interval - delta)
        last_seen[host] = monotonic()
        fetch_html._last_seen = last_seen  # type: ignore[attr-defined]

    def _request() -> requests.Response:
        _rate_limit_if_needed()
        response = session.get(url, headers=headers, timeout=timeout)
        if response.status_code == 429:
            raise requests.HTTPError("Too Many Requests", response=response)
        response.raise_for_status()
        return response

    max_retries = retries if retries is not None else int(os.getenv("POLLA_MAX_RETRIES", "3"))
    backoff_factor = float(os.getenv("POLLA_BACKOFF_FACTOR", "30.0"))
    # Fallback to legacy env if set for backward compatibility
    if "POLLA_429_BACKOFF_SECONDS" in os.environ and "POLLA_BACKOFF_FACTOR" not in os.environ:
        backoff_factor = float(os.getenv("POLLA_429_BACKOFF_SECONDS", "30.0"))

    attempts = 0
    response: requests.Response | None = None
    last_error: Exception | None = None
    while attempts < max_retries:
        try:
            response = _request()
            break
        except requests.HTTPError as err:
            # Only transient status codes are retryable; the rest fail fast.
            attempts += 1
            status = getattr(err.response, "status_code", None)
            if attempts >= max_retries or status not in _RETRYABLE_STATUS:
                raise

            sleep_time = _calculate_backoff(attempts, backoff_factor, 300.0)
            LOGGER.info(
                "%s received from %s (attempt %d/%d); backing off %.1fs",
                status,
                url,
                attempts,
                max_retries,
                sleep_time,
            )
            time.sleep(sleep_time)
        except _RETRYABLE_EXC as err:
            attempts += 1
            last_error = err
            if attempts >= max_retries:
                raise

            sleep_time = _calculate_backoff(attempts, backoff_factor, 300.0)
            LOGGER.info(
                "Transient failure fetching %s (%s; attempt %d/%d); retrying in %.1fs",
                url,
                type(err).__name__,
                attempts,
                max_retries,
                sleep_time,
            )
            time.sleep(sleep_time)

    if response is None:  # pragma: no cover - safety guard
        raise RuntimeError(f"Failed to fetch {url}") from last_error

    fetched_at = datetime.now(timezone.utc)
    html = response.text
    LOGGER.debug("Fetched %s (%d bytes)", url, len(html))
    return FetchMetadata(url=url, user_agent=ua, fetched_at=fetched_at, html=html)
