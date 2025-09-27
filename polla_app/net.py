"""HTTP helpers for fetching alternative sources politely."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from .config import AppConfig
from .exceptions import ScriptError

DEFAULT_UA = "polla-alt-scraper/3.0 (+https://github.com/your-org/polla-transparency)"
_logger = logging.getLogger("polla_app.net")


@lru_cache(maxsize=32)
def _get_robot_parser(robots_url: str) -> Optional[RobotFileParser]:
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception as exc:  # pragma: no cover - network hiccups
        _logger.warning("No se pudo leer robots.txt %s: %s", robots_url, exc)
        return None
    return parser


def _is_allowed(url: str, ua: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = _get_robot_parser(robots_url)
    if parser is None:
        return True
    return parser.can_fetch(ua, url)


def fetch_html(url: str, ua: str = DEFAULT_UA, timeout: int = 20) -> str:
    """Fetch an HTML page politely, respecting 429 throttling."""

    if os.getenv("NO_NET") == "1":
        raise ScriptError("Network disabled via NO_NET environment variable", error_code="NO_NET")

    if not _is_allowed(url, ua):
        raise ScriptError(f"robots.txt does not allow fetching {url}", error_code="ROBOTS_BLOCKED")

    headers = {"User-Agent": ua, "Accept-Language": "es-CL,es;q=0.9"}
    attempt = 0
    max_attempts = 2
    while attempt < max_attempts:
        attempt += 1
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 429 and attempt < max_attempts:
                _logger.warning("429 received for %s; sleeping before retry", url)
                time.sleep(60)
                continue
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                raise ScriptError(f"HTTP error fetching {url}", exc, "HTTP_ERROR") from exc
            time.sleep(5)
    raise ScriptError(f"Unable to fetch {url}", error_code="HTTP_ERROR")


def sha256_text(text: str) -> str:
    """Return the SHA-256 hash of the provided text."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_default_app_config() -> AppConfig:
    """Provide a cached default configuration for callers that only need network settings."""

    return AppConfig.create_default()

