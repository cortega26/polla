"""HTTP helpers for fetching lottery data politely."""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
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
def _get_robots_parser(robots_url: str) -> RobotFileParser | None:
    parser = RobotFileParser()
    try:
        parser.set_url(robots_url)
        parser.read()
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
    parser = _get_robots_parser(robots_url)
    if parser is None:
        return True
    allowed = parser.can_fetch(ua, url)
    if not allowed:
        LOGGER.warning("robots.txt forbids %s for UA %s", url, ua)
    return allowed


def fetch_html(url: str, ua: str, timeout: int = 20) -> FetchMetadata:
    """GET ``url`` with a descriptive UA and return the body plus metadata.

    A single retry with 60s back-off is attempted if the remote responds with
    HTTP 429. Any other non-200 response raises ``HTTPError``.
    """

    session = requests.Session()
    headers = {
        "User-Agent": ua,
        "Accept-Language": "es-CL,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cache-Control": "no-cache",
    }

    if not _robots_allowed(url, ua):
        raise RobotsDisallowedError(
            "Robots policy forbids fetching URL",
            context={"url": url, "ua": ua},
        )

    def _request() -> requests.Response:
        response = session.get(url, headers=headers, timeout=timeout)
        if response.status_code == 429:
            raise requests.HTTPError("Too Many Requests", response=response)
        response.raise_for_status()
        return response

    attempts = 0
    response: requests.Response | None = None
    while attempts < 2:
        try:
            response = _request()
            break
        except requests.HTTPError as err:
            attempts += 1
            if attempts >= 2 or not getattr(err.response, "status_code", None) == 429:
                raise
            LOGGER.info("429 received from %s; backing off before retry", url)
            time.sleep(60)

    if response is None:  # pragma: no cover - safety guard
        raise RuntimeError(f"Failed to fetch {url}")

    fetched_at = datetime.now(timezone.utc)
    html = response.text
    LOGGER.debug("Fetched %s (%d bytes)", url, len(html))
    return FetchMetadata(url=url, user_agent=ua, fetched_at=fetched_at, html=html)
