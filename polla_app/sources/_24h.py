"""Parser for 24Horas Loto result articles."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..net import fetch_html
from .t13 import DEFAULT_UA as T13_UA
from .t13 import parse_draw_from_metadata

LOGGER = logging.getLogger(__name__)
INDEX_URL = "https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html"
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"


def list_24h_result_urls(
    index_url: str = INDEX_URL,
    *,
    limit: int = 10,
    ua: str = DEFAULT_UA,
    timeout: int = 20,
) -> list[str]:
    """Return up to ``limit`` article URLs from the 24Horas tag index."""

    metadata = fetch_html(index_url, ua=ua, timeout=timeout)
    soup = BeautifulSoup(metadata.html, "html.parser")

    urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not href:
            continue
        # Only keep direct result articles, not generic /loto/ listing pages
        if "resultados-loto-sorteo" in href:
            absolute = urljoin(index_url, href)
            if absolute not in urls:
                urls.append(absolute)
                if len(urls) >= limit:
                    break
    LOGGER.debug("Discovered %d URLs from 24Horas index", len(urls))
    return urls


def parse_24h_draw(url: str, *, ua: str = DEFAULT_UA, timeout: int = 20) -> dict[str, Any]:
    """Parse a 24Horas article describing a Loto draw."""

    metadata = fetch_html(url, ua=ua, timeout=timeout)
    record = parse_draw_from_metadata(metadata, source="24horas")

    # Some 24Horas articles embed T13 tables; fall back to the T13 UA when no
    # prize rows are detected to maximise compatibility.
    if not record["premios"] and ua != T13_UA:
        LOGGER.debug("Retrying %s with T13 UA because no premios were found", url)
        metadata = fetch_html(url, ua=T13_UA, timeout=timeout)
        record = parse_draw_from_metadata(metadata, source="24horas")

    return record
