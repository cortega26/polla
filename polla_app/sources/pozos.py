"""Próximo pozo parsers for community aggregators."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from bs4 import BeautifulSoup

from ..exceptions import ParseError
from ..net import fetch_html

LOGGER = logging.getLogger(__name__)
OPENLOTO_URL = "https://www.openloto.cl/pozo-del-loto.html"
POLLA_URL = "https://www.polla.cl/es/"
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

_LABEL_PATTERNS = {
    "Loto Clásico": r"Loto\s+Cl[aá]sico",
    "Recargado": r"Recargado",
    "Revancha": r"Revancha",
    "Desquite": r"Desquite",
    "Jubilazo $1.000.000": r"Jubilazo(?:\s*(?:de\s*)?\$?1\.000\.000)?(?!\s*(?:50\s*a(?:ñ|n)os|Aniversario))",
    # Also include the anniversary/500k variant explicitly so we don't miss it
    # on sources that enumerate both Jubilazo prizes.
    "Jubilazo $500.000": r"Jubilazo\s*(?:de\s*)?\$?500\.000",
    # Long-term annuity variants ("Jubilazo 50 años ...")
    "Jubilazo 50 años $1.000.000": r"Jubilazo\s*(?:50\s*a(?:ñ|n)os|Aniversario)(?:\s*de)?\s*\$?1\.000\.000",
    "Jubilazo 50 años $500.000": r"Jubilazo\s*(?:50\s*a(?:ñ|n)os|Aniversario)(?:\s*de)?\s*\$?500\.000",
    "Total estimado": r"Total\s+estimado",
}


# Precompiled helpers to avoid repeated regex compilation in hot paths
_NON_NUM = re.compile(r"[^0-9,\.]")
_LABEL_REGEX: dict[str, re.Pattern[str]] = {
    label: re.compile(
        pattern + r"[^0-9$]{0,50}\$?([\d\.,]+)",
        re.IGNORECASE,
    )
    for label, pattern in _LABEL_PATTERNS.items()
}
_DATE_RE = re.compile(
    r"(\d{1,2})\s+de\s+([a-zA-Z\u00C0-\u017F]+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)
_PROX_FECHA_BLOCK_RE = re.compile(
    r"Fecha\s+Pr[oó]ximo\s+Sorteo[:\s]*([^\n]+)",
    re.IGNORECASE,
)
_SORTEO_RE = re.compile(r"Sorteo\s*(?:N[°º]\s*)?(\d{4,})", re.IGNORECASE)


def _parse_millones_to_clp(raw: str) -> int:
    """Parse Spanish-formatted MILLONES into integer CLP.

    Examples:
    - "690" -> 690_000_000
    - "4.300" -> 4_300_000_000 (dot as thousands separator)
    - "4,75" -> 4_750_000 (comma as decimal separator)
    - "1.234,56" -> 1_234_560_000
    - "4.300 MM" -> 4_300_000_000
    """

    cleaned = (raw or "").strip().lower()
    if not cleaned:
        raise ParseError("Empty monetary value", context={"raw": raw})

    # Detect explicit units
    multiplier = 1_000_000
    if cleaned.endswith("mm") or "millones" in cleaned:
        multiplier = 1_000_000
        cleaned = cleaned.replace("millones", "").replace("mm", "").strip()
    elif cleaned.endswith("mil"):
        # "1.000 mil" -> 1,000,000 (but in MILLONES context this is rare)
        # If the input expects millions, "mil" might be a suffix for an absolute value
        # that was accidentally passed. We'll honor the "mil" = 1000.
        multiplier = 1_000
        cleaned = cleaned.replace("mil", "").strip()
    elif cleaned.endswith("m") and not cleaned.endswith("mm"):
        # Single M usually means Millions in this context
        multiplier = 1_000_000
        cleaned = cleaned.rstrip("m").strip()

    # Remove currency and whitespace
    cleaned = cleaned.replace("$", "").replace(" ", "")

    # Detect separator intent
    if "." in cleaned and "," in cleaned:
        # Mixed: 1.234,56 -> 1234.56
        # Validate that dots are thousands (3 digits)
        parts = cleaned.split(".")
        for p in parts[1:-1]:
            if len(p) != 3:
                raise ParseError("Invalid thousands separator position", context={"raw": raw})
        if len(parts[-1].split(",")[0]) != 3:
            raise ParseError("Invalid last thousands separator", context={"raw": raw})
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # Only comma.
        parts = cleaned.split(",")
        if len(parts) > 2:
            # 1,234,567
            for p in parts[1:]:
                if len(p) != 3:
                    raise ParseError("Invalid multiple commas", context={"raw": raw})
            cleaned = cleaned.replace(",", "")
        elif len(parts) == 2 and len(parts[1]) == 3:
            # 4,300 -> 4300
            cleaned = cleaned.replace(",", "")
        else:
            # 4,75 -> 4.75
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        # Only dot.
        parts = cleaned.split(".")
        if len(parts) > 2:
            # 1.234.567
            for p in parts[1:]:
                if len(p) != 3:
                    raise ParseError("Invalid multiple dots", context={"raw": raw})
            cleaned = cleaned.replace(".", "")
        elif len(parts) == 2 and len(parts[1]) == 3:
            # 4.300 -> 4300
            cleaned = cleaned.replace(".", "")
        else:
            # 4.3 -> 4.3
            pass

    try:
        value = float(cleaned)
    except ValueError as exc:
        raise ParseError(
            f"Unable to parse monetary value: {raw}",
            original_error=exc,
            context={"raw": raw, "processed": cleaned},
        ) from exc

    return int(round(value * multiplier))


def _extract_amounts(text: str, *, allow_total: bool = True) -> dict[str, int]:
    amounts: dict[str, int] = {}
    for label, regex in _LABEL_REGEX.items():
        if not allow_total and label == "Total estimado":
            continue
        match = regex.search(text)
        if match:
            amounts[label] = _parse_millones_to_clp(match.group(1))
        elif label != "Total estimado":
            amounts[label] = 0
    return amounts


_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def _parse_spanish_date(text: str) -> str | None:
    # Match e.g., 16 de septiembre de 2025
    m = _DATE_RE.search(text)
    if not m:
        return None
    day, month_name, year = m.group(1), m.group(2), m.group(3)
    month = _MONTHS.get(month_name.lower())
    if not month:
        return None
    try:
        from datetime import date

        return date(int(year), int(month), int(day)).isoformat()
    except Exception:
        return None


def _extract_proximo_info(text: str) -> tuple[int | None, str | None]:
    # Common patterns on aggregator pages
    sorteo: int | None = None
    fecha_iso: str | None = None

    m_sorteo = _SORTEO_RE.search(text)
    if m_sorteo:
        try:
            sorteo = int(m_sorteo.group(1))
        except ValueError:
            sorteo = None

    # Prefer explicit "Fecha Próximo Sorteo" segment if present
    m_fecha_block = _PROX_FECHA_BLOCK_RE.search(text)
    if m_fecha_block:
        fecha_iso = _parse_spanish_date(m_fecha_block.group(1))
    if not fecha_iso:
        fecha_iso = _parse_spanish_date(text)
    return sorteo, fecha_iso


def _effective_ua(ua: str) -> str:
    """Resolve effective User-Agent from env override or provided value.

    Honors the POLLA_USER_AGENT environment variable if set.
    """
    return os.getenv("POLLA_USER_AGENT") or ua


def _fetch_pozos(
    *, url: str, ua: str, timeout: int, allow_total: bool, retries: int | None = None
) -> dict[str, Any]:
    metadata = fetch_html(url, ua=_effective_ua(ua), timeout=timeout, retries=retries)
    soup = BeautifulSoup(metadata.html, "html.parser")
    text = soup.get_text(" ", strip=True)
    amounts = _extract_amounts(text, allow_total=allow_total)
    if not amounts or sum(amounts.values()) == 0:
        raise ParseError(
            f"No valid pozo amounts found in source content from {url}",
            context={"url": url, "text_snippet": text[:200]},
        )
    sorteo, fecha = _extract_proximo_info(text)
    return {
        "fuente": url,
        "fetched_at": metadata.fetched_at.isoformat(),
        "sha256": metadata.sha256,
        "estimado": True,
        "montos": amounts,
        "user_agent": metadata.user_agent,
        "sorteo": sorteo,
        "fecha": fecha,
    }


def get_pozo_openloto(
    url: str = OPENLOTO_URL,
    *,
    ua: str = DEFAULT_UA,
    timeout: int = 20,
    retries: int | None = None,
) -> dict[str, Any]:
    """Fetch próximo pozo data from OpenLoto."""

    return _fetch_pozos(url=url, ua=ua, timeout=timeout, allow_total=False, retries=retries)


def get_pozo_polla(
    url: str = POLLA_URL,
    *,
    ua: str = DEFAULT_UA,
    timeout: int = 20,
    retries: int | None = None,
) -> dict[str, Any]:
    """Fetch próximo pozo data directly from polla.cl using Playwright.

    Note: polla.cl is an SPA. This function uses Playwright to render the DOM,
    clicks the 'VER DETALLE POR CATEGORÍA' button to expand granular prizes,
    and then parses the structured HTML.
    """
    try:
        from scrapling import StealthyFetcher
    except ImportError as e:
        raise ParseError("scrapling must be installed to fetch from polla.cl") from e

    import hashlib
    from datetime import datetime, timezone

    from bs4 import BeautifulSoup

    shared_data: dict[str, str] = {}

    def click_detalle(page: Any) -> None:
        try:
            page.locator("text=VER DETALLE POR CATEGORÍA").first.click(timeout=3000)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        # Scrapling sometimes fails to serialize the DOM text correctly, returning an empty string.
        # We extract the content natively here before the session closes.
        try:
            shared_data["html"] = page.content()
            shared_data["text"] = page.locator("body").inner_text()
        except Exception:
            pass

    try:
        fetcher = StealthyFetcher(headless=True)
        page = fetcher.fetch(url, page_action=click_detalle)
        if page.status != 200:
            raise ParseError(f"Polla.cl returned status {page.status}", context={"url": url})

        html_content = str(shared_data.get("html") or getattr(page, "text", ""))
        text_content = str(shared_data.get("text") or getattr(page, "text_content", html_content))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"Scrapling failed to fetch {url}", original_error=exc) from exc

    fetched_at = datetime.now(timezone.utc)

    soup = BeautifulSoup(html_content, "html.parser")
    amounts: dict[str, int] = {}

    # 1. Total Estimado
    total_text = soup.find(string=lambda s: s and "POZO TOTAL ESTIMADO" in s)
    if total_text and total_text.parent:
        parent_li = total_text.parent.find_parent("li")
        if parent_li:
            prize_span = parent_li.find(class_="prize")
            if prize_span:
                try:
                    amounts["Total estimado"] = _parse_millones_to_clp(
                        prize_span.get_text(strip=True)
                    )
                except Exception:
                    pass

    # 2. Sub-games
    for li in soup.select(".sub-game"):
        img = li.select_one("img")
        if not img:
            continue
        src = str(img.get("src", "")).lower()

        texts = list(li.stripped_strings)
        prize_span = li.find(class_="prize")
        if not prize_span:
            continue

        prize_str = prize_span.get_text(strip=True)
        try:
            prize_val = _parse_millones_to_clp(prize_str)
        except Exception:
            continue

        category = None
        if "loto_logo" in src:
            category = "Loto Clásico"
        elif "recargado" in src:
            category = "Recargado"
        elif "revancha" in src:
            category = "Revancha"
        elif "desquite" in src:
            category = "Desquite"
        elif "jubilazo" in src and "50" not in src:
            if "$1.000.000" in texts:
                category = "Jubilazo $1.000.000"
            elif "$500.000" in texts:
                category = "Jubilazo $500.000"
        elif "jubilazo-50" in src:
            if "$1.000.000" in texts:
                category = "Jubilazo 50 años $1.000.000"
            elif "$500.000" in texts:
                category = "Jubilazo 50 años $500.000"

        if category:
            amounts[category] = prize_val

    if not amounts or sum(amounts.values()) == 0:
        raise ParseError(
            f"No valid pozo amounts found in source content from {url}",
            context={"url": url, "text_snippet": text_content[:200]},
        )

    sorteo, fecha = _extract_proximo_info(text_content)

    sha256 = hashlib.sha256(html_content.encode("utf-8")).hexdigest()

    return {
        "fuente": url,
        "fetched_at": fetched_at.isoformat(),
        "sha256": sha256,
        "estimado": True,
        "montos": amounts,
        "user_agent": "Scrapling/StealthyFetcher",
        "sorteo": sorteo,
        "fecha": fecha,
    }
