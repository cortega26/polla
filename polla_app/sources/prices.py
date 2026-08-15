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

import hashlib
import logging
import re
from datetime import UTC, datetime
from typing import Any

from ..exceptions import ParseError
from .browser import fetch_with_browser_fallback

LOGGER = logging.getLogger(__name__)

LOTO_PRICES_URL = "https://www.polla.cl/es/view/juego/loto"
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

# Kino hub (kino.loteria.cl) requires browser-like framing headers or it
# redirects to the loteria.cl home. The price structure per draw lives in
# __NEXT_DATA__.props.pageProps.initialSorteos.data.
KINO_HUB_URL = (
    "https://kino.loteria.cl/kino?session=undefined&company=LCC&machine=1000"
    "&external_id=kino&type=Loterias&demo=true&lang=undefined"
)
KINO_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
_KINO_FRAME_HEADERS = {
    "Sec-Fetch-Dest": "iframe",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-site",
    "Referer": "https://www.loteria.cl/juegos/kino/",
}

# Kino price fields (per draw) -> canonical category labels.
_KINO_PRICE_FIELDS: tuple[tuple[str, str], ...] = (
    ("PrecioKino", "Kino"),
    ("PrecioReKino", "ReKino"),
    ("PrecioRequeteKino", "RequeteKino"),
    ("PrecioChaoJefe2M", "Chao Jefe $2 Millones"),
    ("PrecioChaoJefe3M", "Chao Jefe $3 Millones"),
    ("PrecioComboMarraqueta", "Súper Combo Marraqueta"),
)
_KINO_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)

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


def _fetch_game_page(url: str, *, ua: str, timeout: int, retries: int | None) -> str:
    """Fetch the Loto game page, falling back to a browser client.

    polla.cl blocks plain HTTP clients from some networks (e.g. GitHub
    Actions runners return 403); the shared helper retries with
    Scrapling's StealthyFetcher on any plain-fetch failure.
    """
    metadata = fetch_with_browser_fallback(
        url, ua=ua, timeout=timeout, retries=retries, fallback_on_any=True
    )
    return metadata.html


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
    it. The regexes tolerate surrounding tags. Falls back to a headless
    browser when the plain HTTP client is blocked.
    """
    import html

    raw_html = _fetch_game_page(url, ua=ua, timeout=timeout, retries=retries)
    payload = _extract_prices(html.unescape(raw_html))
    return {
        "fuente": url,
        "fetched_at": datetime.now(UTC).isoformat(),
        "sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "user_agent": ua,
        **payload,
    }


def _extract_kino_prices(next_data: dict[str, Any]) -> dict[str, Any]:
    """Parse the per-draw Kino price structure from the hub __NEXT_DATA__."""
    page_props = (next_data.get("props") or {}).get("pageProps") or {}
    sorteos = (page_props.get("initialSorteos") or {}).get("data") or []
    if not sorteos:
        raise ParseError(
            "Kino hub did not expose initialSorteos (layout changed?)",
            context={"keys": sorted(page_props.keys())},
        )
    # The list is chronological; the upcoming draw is the first entry.
    draw = sorteos[0]
    prices: dict[str, dict[str, int]] = {}
    cumulative = 0
    for field, label in _KINO_PRICE_FIELDS:
        value = draw.get(field)
        if not isinstance(value, int | float) or value <= 0:
            raise ParseError(
                f"Kino hub price field {field} missing for sorteo {draw.get('NumeroSorteo')}",
                context={"draw": draw},
            )
        cumulative += int(value)
        prices[label] = {"delta_clp": int(value), "acumulado_clp": cumulative}
    return {
        "precios": prices,
        "sorteo": draw.get("NumeroSorteo"),
        "fecha": draw.get("FechaSorteo"),
        "cumulative": cumulative,
    }


def get_kino_prices(
    url: str = KINO_HUB_URL,
    *,
    timeout: int = 20,
    retries: int | None = None,
) -> dict[str, Any]:
    """Fetch the per-draw Kino price structure from the official hub.

    The hub (kino.loteria.cl) is public but redirects plain requests to the
    loteria.cl home; browser-like framing headers are required.
    """
    metadata = fetch_with_browser_fallback(
        url,
        ua=KINO_BROWSER_UA,
        timeout=timeout,
        retries=retries,
        extra_headers=_KINO_FRAME_HEADERS,
    )
    match = _KINO_NEXT_DATA_RE.search(metadata.html)
    if not match:
        raise ParseError(
            "Kino hub page did not contain __NEXT_DATA__ (blocked or layout changed?)",
            context={"snippet": metadata.html[:200]},
        )
    import json

    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ParseError("Kino hub __NEXT_DATA__ is not valid JSON", original_error=exc) from exc

    payload = _extract_kino_prices(next_data)
    return {
        "fuente": url,
        "fetched_at": datetime.now(UTC).isoformat(),
        "sha256": hashlib.sha256(metadata.html.encode("utf-8")).hexdigest(),
        "user_agent": metadata.user_agent,
        **payload,
    }


__all__ = ["get_kino_prices", "get_loto_prices", "KINO_HUB_URL", "LOTO_PRICES_URL"]
