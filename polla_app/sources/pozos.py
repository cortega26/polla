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
    # Also include the anniversary/500k variant explicitly so we don't miss it
    # on sources that enumerate both Jubilazo prizes.
    "Jubilazo $500.000": (
        r"(?:Jubilazo\s+Aniversario(?:\s*de\s*\$?500\.000)?|Jubilazo\s*\$?500\.000)"
    ),
    "Total estimado": r"Total\s+estimado",
}


def _parse_millones_to_clp(raw: str) -> int:
    """Parse Spanish-formatted MILLONES into integer CLP.

    Examples:
    - "690" -> 690_000_000
    - "4.300" -> 4_300_000_000 (dot as thousands separator)
    - "4,75" -> 4_750_000 (comma as decimal separator)
    - "1.234,56" -> 1_234_560
    """

    cleaned = re.sub(r"[^0-9,\.]", "", raw or "")
    if not cleaned:
        return 0

    if "," in cleaned and "." in cleaned:
        # Assume dot thousands + comma decimal
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(".", "")

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
    m = re.search(r"(\d{1,2})\s+de\s+([a-zA-Z\u00C0-\u017F]+)\s+de\s+(\d{4})", text, re.IGNORECASE)
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

    m_sorteo = re.search(r"Sorteo\s*(?:N[°º]\s*)?(\d{4,})", text, re.IGNORECASE)
    if m_sorteo:
        try:
            sorteo = int(m_sorteo.group(1))
        except ValueError:
            sorteo = None

    # Prefer explicit "Fecha Próximo Sorteo" segment if present
    m_fecha_block = re.search(
        r"Fecha\s+Pr[oó]ximo\s+Sorteo[:\s]*([^\n]+)", text, re.IGNORECASE
    )
    if m_fecha_block:
        fecha_iso = _parse_spanish_date(m_fecha_block.group(1))
    if not fecha_iso:
        fecha_iso = _parse_spanish_date(text)
    return sorteo, fecha_iso


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
    amounts = _extract_amounts(text, allow_total=False)
    sorteo, fecha = _extract_proximo_info(text)
    return {
        "fuente": url,
        "fetched_at": metadata.fetched_at.isoformat(),
        "estimado": True,
        "montos": amounts,
        "user_agent": metadata.user_agent,
        "sorteo": sorteo,
        "fecha": fecha,
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
    # Skip total to avoid noise
    amounts = _extract_amounts(text, allow_total=False)
    sorteo, fecha = _extract_proximo_info(text)
    return {
        "fuente": url,
        "fetched_at": metadata.fetched_at.isoformat(),
        "estimado": True,
        "montos": amounts,
        "user_agent": metadata.user_agent,
        "sorteo": sorteo,
        "fecha": fecha,
    }
