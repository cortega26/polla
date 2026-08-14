"""Loto price structure scraper (polla.cl official game page).

Prices change per draw on special Loto draws, so they are scraped live
every run from the server-rendered game page (no browser needed):

    https://www.polla.cl/es/view/juego/loto

The page contains the "VALOR DE LAS JUGADAS LOTO" block with cumulative
prices (Loto $1.000, Loto + Recargado $1.500, ...). Deltas are derived
from consecutive cumulative values. If the page structure changes, the
parser raises ParseError and the pipeline continues without prices
(the dashboard renders "—" instead of stale values).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from ..exceptions import ParseError
from ..net import fetch_html

LOGGER = logging.getLogger(__name__)

LOTO_PRICES_URL = "https://www.polla.cl/es/view/juego/loto"
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

# Category labels as published in the price block (canonical order).
_CATEGORY_ORDER = (
    "Loto Clásico",
    "Recargado",
    "Revancha",
    "Desquite",
    "Jubilazo",
    "Multiplicar",
    "Jubilazo 50 años",
)

# Each cumulative line: "Loto + Recargado + Revancha ... $X.XXX.-"
_CUMULATIVE_RE = re.compile(
    r"Loto(?:\s*\+\s*[A-ZÁÉÍÓÚÑ0-9áéíóúñ\s+]+?)?\s*\$\s?([\d.]+)",
    re.IGNORECASE,
)
# "Juegos adicionales" deltas: "RECARGADO" ... "$500 por sorteo"
_DELTA_RE = re.compile(
    r"(RECARGADO|REVANCHA|DESQUITE|JUBILAZO(?: 50 AÑOS)?|MULTIPLICAR)\b[^$]{0,80}\$?\s?([\d.]+)\s*por sorteo",
    re.IGNORECASE,
)


def _clean_clp(raw: str) -> int:
    return int(raw.replace(".", "").replace("$", "").replace(" ", ""))


def _extract_prices(text: str) -> dict[str, Any]:
    """Parse cumulative prices from the 'VALOR DE LAS JUGADAS' block."""
    cumulative: list[int] = []
    for match in _CUMULATIVE_RE.finditer(text):
        # Only accept the standard-play block (prices up to $3.500);
        # combinadas blocks use larger amounts and would break deltas.
        value = _clean_clp(match.group(1))
        if 0 < value <= 10_000 and (not cumulative or value > cumulative[-1]):
            cumulative.append(value)
            if len(cumulative) == len(_CATEGORY_ORDER):
                break

    if len(cumulative) != len(_CATEGORY_ORDER):
        # Fallback: derive deltas from the "Juegos adicionales" checkboxes.
        deltas: dict[str, int] = {}
        for match in _DELTA_RE.finditer(text):
            deltas[match.group(1).upper()] = _clean_clp(match.group(2))
        base_match = re.search(r"LOTO\s*:\s*\$?\s?([\d.]+)", text, re.IGNORECASE)
        if not deltas or not base_match:
            raise ParseError(
                "Could not find Loto price structure on the official page",
                context={"snippet": text[:300]},
            )
        cumulative = [_clean_clp(base_match.group(1))]
        for label in (
            "RECARGADO",
            "REVANCHA",
            "DESQUITE",
            "JUBILAZO",
            "MULTIPLICAR",
            "JUBILAZO 50 AÑOS",
        ):
            cumulative.append(cumulative[-1] + deltas.get(label, 0))

    prices: dict[str, dict[str, int]] = {}
    for index, category in enumerate(_CATEGORY_ORDER):
        delta = cumulative[index] - (cumulative[index - 1] if index else 0)
        if delta <= 0:
            raise ParseError(
                "Loto price structure is not monotonic (special draw changed layout?)",
                context={"cumulative": cumulative},
            )
        prices[category] = {"delta_clp": delta, "acumulado_clp": cumulative[index]}
    return {"precios": prices, "cumulative": cumulative}


def get_loto_prices(
    url: str = LOTO_PRICES_URL,
    *,
    ua: str = DEFAULT_UA,
    timeout: int = 20,
    retries: int | None = None,
) -> dict[str, Any]:
    """Fetch the current Loto price structure from the official game page.

    The price block is server-rendered but embedded JSON-escaped inside a
    script (HTML entities + escaped newlines), so the parser runs over the
    raw page after HTML-unescaping; BeautifulSoup's ``get_text`` would skip
    it. The regexes tolerate surrounding tags.
    """
    import html

    metadata = fetch_html(url, ua=ua, timeout=timeout, retries=retries)
    payload = _extract_prices(html.unescape(metadata.html))
    return {
        "fuente": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(metadata.html.encode("utf-8")).hexdigest(),
        "user_agent": metadata.user_agent,
        **payload,
    }


__all__ = ["get_loto_prices", "LOTO_PRICES_URL"]
