"""Shared headless-browser fetcher for sources that block plain HTTP.

polla.cl blocks plain HTTP clients from some networks; the pipeline falls
back to Scrapling's StealthyFetcher. A single instance is reused per process
to avoid launching Chromium more than once per run.
"""

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

_fetcher: Any | None = None


def get_stealthy_fetcher() -> Any:
    """Return the process-wide StealthyFetcher instance, creating it once."""
    global _fetcher  # controlled process-wide cache (see net.py rate limiter)
    if _fetcher is None:
        from scrapling import StealthyFetcher

        _fetcher = StealthyFetcher(headless=True)
        LOGGER.info("Launched shared StealthyFetcher instance")
    return _fetcher


__all__ = ["get_stealthy_fetcher"]
