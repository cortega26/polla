"""Shared headless-browser fetcher for sources that block plain HTTP.

polla.cl blocks plain HTTP clients from some networks; the pipeline falls
back to Scrapling's StealthyFetcher. A single instance is reused per process
to avoid launching Chromium more than once per run.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from ..exceptions import ParseError
from ..net import FetchMetadata, fetch_html

LOGGER = logging.getLogger(__name__)

_fetcher: Any | None = None


def get_stealthy_fetcher() -> Any:
    """Return the process-wide StealthyFetcher instance, creating it once."""
    global _fetcher  # controlled process-wide cache (see net.py rate limiter)
    if _fetcher is None:
        from scrapling import StealthyFetcher

        _fetcher = StealthyFetcher()
        LOGGER.info("Launched shared StealthyFetcher instance")
    return _fetcher


def fetch_with_browser_fallback(
    url: str,
    *,
    ua: str,
    timeout: int = 20,
    retries: int | None = None,
    extra_headers: dict[str, str] | None = None,
    fallback_on_any: bool = False,
) -> FetchMetadata:
    """Fetch ``url`` with plain HTTP; on failure, retry with the headless browser.

    Default policy: fall back only when the server answers a 5XX status
    (transient upstream errors). ``fallback_on_any=True`` (polla.cl game page)
    falls back on any plain-fetch failure, including 403/timeouts.
    """
    try:
        return fetch_html(url, ua=ua, timeout=timeout, retries=retries, extra_headers=extra_headers)
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        is_5xx = isinstance(status, int) and 500 <= status <= 599
        if not fallback_on_any and not is_5xx:
            raise
        LOGGER.info(
            "Plain fetch of %s failed (%s%s); retrying with browser",
            url,
            type(exc).__name__,
            f" status={status}" if status else "",
        )

    try:
        fetcher = get_stealthy_fetcher()
        page = fetcher.fetch(url, timeout=timeout)
    except ImportError as exc:  # scrapling no instalado
        raise ParseError("scrapling must be installed to use the browser fallback") from exc
    if getattr(page, "status", None) != 200:
        raise ParseError(
            f"Browser fetch of {url} failed with status {getattr(page, 'status', None)}"
        )
    html = str(getattr(page, "html", "") or getattr(page, "text", ""))
    if not html:
        raise ParseError(f"Browser fetch of {url} returned empty content")
    return FetchMetadata(
        url=url,
        user_agent="Scrapling/StealthyFetcher",
        fetched_at=datetime.now(UTC),
        html=html,
    )


__all__ = ["fetch_with_browser_fallback", "get_stealthy_fetcher"]
