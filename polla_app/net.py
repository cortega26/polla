"""Minimal polite HTTP fetch utilities for alt sources.

This module intentionally avoids any dynamic/browser automation and only
performs simple GET requests with a descriptive User-Agent and basic
backoff handling for 429 responses.
"""

from __future__ import annotations

import time
from typing import Final

import requests


DEFAULT_UA: Final = "OddsTransparencyBot/1.0 (+contact@example.com)"


class HttpError(RuntimeError):
    pass


def fetch_html(url: str, ua: str = DEFAULT_UA, timeout: int = 20) -> str:
    """GET url with a descriptive UA and minimal headers; raise on non-200.

    On HTTP 429, sleeps for 60s and retries once before failing.
    """
    headers = {
        "User-Agent": ua or DEFAULT_UA,
        "Accept-Language": "es-CL,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    }

    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code == 429:
        time.sleep(60)
        resp = requests.get(url, headers=headers, timeout=timeout)

    if resp.status_code != 200:
        raise HttpError(f"GET {url} -> {resp.status_code}")

    # requests returns bytes decoded to text via apparent encoding; keep it simple
    return resp.text

