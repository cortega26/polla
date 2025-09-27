"""Próximo pozo parsers for community aggregators."""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup

from ..net import fetch_html

LOGGER = logging.getLogger(__name__)
OPENLOTO_URL = "https://www.openloto.cl/pozo-del-loto.html"
RESULTADOS_URL = "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/"
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

_LABEL_PATTERNS = {
    "Loto Clásico": r"Loto\s+Cl[aá]sico",
    "Recargado": r"Recargado",
    "Revancha": r"Revancha",
    "Desquite": r"Desquite",
    "Jubilazo $1.000.000": r"Jubilazo(?:\s*\$?1\.000\.000)?",
    "Total estimado": r"Total\s+estimado",
}


def _parse_millones_to_clp(raw: str) -> int:
    cleaned = re.sub(r"[^0-9,\.]", "", raw or "")
    if not cleaned:
        return 0
    cleaned = cleaned.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        LOGGER.debug("Unable to parse monetary value from %s", raw)
        return 0
    return int(round(value * 1_000_000))


def _extract_amounts(text: str, *, allow_total: bool = True) -> dict[str, int]:
    amounts: dict[str, int] = {}
    for label, pattern in _LABEL_PATTERNS.items():
        if not allow_total and label == "Total estimado":
            continue
        regex = re.compile(
            pattern + r"[^0-9$]{0,40}\$?([\d\.,]+)\s*(?:MM|MILLON(?:ES)?)?", re.IGNORECASE
        )
        match = regex.search(text)
        if match:
            amounts[label] = _parse_millones_to_clp(match.group(1))
    return amounts


def get_pozo_openloto(
    url: str = OPENLOTO_URL,
    *,
    ua: str = DEFAULT_UA,
    timeout: int = 20,
) -> dict[str, Any]:
    """Fetch próximo pozo data from OpenLoto."""

    metadata = fetch_html(url, ua=ua, timeout=timeout)
    soup = BeautifulSoup(metadata.html, "html.parser")
    text = soup.get_text(" ", strip=True)
    amounts = _extract_amounts(text)
    return {
        "fuente": url,
        "fetched_at": metadata.fetched_at.isoformat(),
        "estimado": True,
        "montos": amounts,
        "user_agent": metadata.user_agent,
    }


def get_pozo_resultadosloto(
    url: str = RESULTADOS_URL,
    *,
    ua: str = DEFAULT_UA,
    timeout: int = 20,
) -> dict[str, Any]:
    """Fetch próximo pozo data from resultadoslotochile.com."""

    metadata = fetch_html(url, ua=ua, timeout=timeout)
    soup = BeautifulSoup(metadata.html, "html.parser")
    text = soup.get_text(" ", strip=True)
    # The resultadosloto site rarely publishes a "Total" headline. Skip that
    # label to avoid false positives from unrelated marketing text.
    amounts = _extract_amounts(text, allow_total=False)
    return {
        "fuente": url,
        "fetched_at": metadata.fetched_at.isoformat(),
        "estimado": True,
        "montos": amounts,
        "user_agent": metadata.user_agent,
    }
