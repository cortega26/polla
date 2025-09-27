"""Parser for T13 lottery result pages."""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from ..net import FetchMetadata, fetch_html

LOGGER = logging.getLogger(__name__)
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

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


@dataclass
class _PrizeRow:
    categoria: str
    premio_clp: int
    ganadores: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "categoria": self.categoria,
            "premio_clp": self.premio_clp,
            "ganadores": self.ganadores,
        }


def _clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_category(text: str) -> str:
    cleaned = _clean_whitespace(text)
    cleaned = cleaned.lstrip(".-:; ")
    cleaned = re.sub(
        r"(\b(?:otorga|entrega|paga|para|con)\b.*)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[,:;\-]+$", "", cleaned).strip()
    return cleaned


def _parse_amount(raw: str) -> int:
    if not raw:
        return 0

    text = raw.strip()
    upper = text.upper()
    multiplier = 1
    if "MM" in upper or "MILLON" in upper:
        multiplier = 1_000_000
    elif "MILLONES" in upper:
        multiplier = 1_000_000

    numeric = re.sub(r"[^0-9,\.]", "", text)
    if not numeric:
        return 0

    if multiplier > 1:
        numeric = numeric.replace(" ", "")
        numeric = numeric.replace(",", ".")
        value = float(numeric)
        return int(round(value * multiplier))

    if numeric.count(",") > 1 and "." not in numeric:
        numeric = numeric.replace(",", "")
    elif numeric.count(".") > 1 and "," not in numeric:
        numeric = numeric.replace(".", "")
    else:
        numeric = numeric.replace(".", "").replace(",", "")

    return int(float(numeric)) if numeric else 0


def _parse_int(raw: str) -> int:
    numeric = re.sub(r"[^0-9]", "", raw or "")
    if not numeric:
        return 0
    try:
        return int(numeric)
    except ValueError:  # pragma: no cover - defensive
        return 0


def _extract_table(anchor: BeautifulSoup) -> Iterable[_PrizeRow]:
    table = anchor.find_next("table") if anchor else None
    if not table:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    start_index = 1 if "Categoría" in rows[0].get_text() else 0
    prizes: list[_PrizeRow] = []
    for tr in rows[start_index:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        categoria = _clean_whitespace(cells[0])
        premio = _parse_amount(cells[1])
        ganadores = _parse_int(cells[2]) if len(cells) > 2 else 0
        if not categoria:
            continue
        prizes.append(_PrizeRow(categoria=categoria, premio_clp=premio, ganadores=ganadores))
    return prizes


def _extract_paragraphs(soup: BeautifulSoup) -> Iterable[_PrizeRow]:
    prizes: list[_PrizeRow] = []
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    block = " ".join(filter(None, paragraphs))
    if not block:
        return prizes

    seen: set[str] = set()
    for match in re.finditer(r"\$[\d\.,]+(?:\s*MM)?", block):
        premio = _parse_amount(match.group(0))
        prefix = block[: match.start()]
        split_idx = max(prefix.rfind("."), prefix.rfind(";"))
        if split_idx == -1:
            split_idx = 0
        categoria_raw = prefix[split_idx:].strip()
        categoria_raw = re.sub(r"^[-:]+", "", categoria_raw).strip()
        categoria = _sanitize_category(categoria_raw)
        if (
            not categoria
            or categoria.lower().startswith("sorteo")
            or not re.search(r"[a-zA-Z]", categoria)
        ):
            continue
        if categoria in seen:
            continue
        seen.add(categoria)

        suffix = block[match.end() :]
        gan_match = re.search(r"(\d[\d\.]*)\s+ganad", suffix, re.IGNORECASE)
        ganadores = _parse_int(gan_match.group(1) if gan_match else "0")
        prizes.append(_PrizeRow(categoria=categoria, premio_clp=premio, ganadores=ganadores))
    return prizes


_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+de\s+([a-zA-Z\u00C0-\u017F]+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)


def _parse_metadata(text: str) -> tuple[int | None, str | None]:
    sorteo_match = re.search(r"sorteo\s+(\d{4,})", text, re.IGNORECASE)
    sorteo = int(sorteo_match.group(1)) if sorteo_match else None

    fecha_iso: str | None = None
    for day, month_name, year in _DATE_PATTERN.findall(text):
        month = _MONTHS.get(month_name.lower())
        if not month:
            continue
        try:
            fecha = dt.date(int(year), month, int(day))
        except ValueError:
            continue
        fecha_iso = fecha.isoformat()
        break

    return sorteo, fecha_iso


def parse_draw_from_metadata(metadata: FetchMetadata, *, source: str) -> dict[str, Any]:
    soup = BeautifulSoup(metadata.html, "html.parser")
    text = soup.get_text(" ", strip=True)

    anchor = None
    for tag in soup.find_all(["h2", "h3"]):
        if "ganadores" in tag.get_text(strip=True).lower():
            anchor = tag
            break

    prizes = list(_extract_table(anchor))
    if not prizes:
        prizes = list(_extract_paragraphs(soup))

    sorteo, fecha = _parse_metadata(text)

    record = {
        "sorteo": sorteo,
        "fecha": fecha,
        "fuente": metadata.url,
        "premios": [row.to_dict() for row in prizes],
        "provenance": {
            "source": source,
            "fetched_at": metadata.fetched_at.isoformat(),
            "html_sha256": metadata.sha256,
            "user_agent": metadata.user_agent,
        },
    }
    return record


def parse_t13_draw(url: str, *, ua: str = DEFAULT_UA, timeout: int = 20) -> dict[str, Any]:
    """Parse a T13 draw page and return the normalized record."""

    metadata = fetch_html(url, ua=ua, timeout=timeout)
    try:
        return parse_draw_from_metadata(metadata, source="t13")
    except Exception as exc:
        LOGGER.exception("Failed to parse T13 draw from %s", url)
        raise RuntimeError(f"Could not parse T13 draw at {url}") from exc
