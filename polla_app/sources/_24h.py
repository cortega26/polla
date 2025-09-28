"""Parser for 24Horas Loto result articles.\n\nThis module contains both the 24Horas-specific helpers and the generic\nHTML-to-record parsing logic previously shared with the removed T13 parser.\n"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..net import fetch_html
import datetime as dt
import re
from dataclasses import dataclass

from polla_app.net import FetchMetadata

LOGGER = logging.getLogger(__name__)
INDEX_URL = "https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html"
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"


# -------------------------- Generic parsing logic ---------------------------

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


@dataclass(slots=True)
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
    return re.sub(r"\s+", " ", text or "").strip()


def _sanitize_category(raw: str) -> str:
    cleaned = _clean_whitespace(raw)
    cleaned = re.sub(r"\s*[:\-–—]\s*", ": ", cleaned)
    return cleaned


def _parse_amount(text: str) -> int:
    cleaned = (text or "").upper().replace("$", "").strip()
    mm = False
    if cleaned.endswith("MM"):
        mm = True
        cleaned = cleaned[:-2].strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return 0
    return int(value * (1_000_000 if mm or value < 1000 else 1))


def _parse_int(text: str | None) -> int:
    try:
        return int(re.sub(r"[^0-9]", "", text or "0") or "0")
    except ValueError:
        return 0


def _extract_table(anchor: BeautifulSoup) -> list[_PrizeRow]:
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


def _extract_paragraphs(soup: BeautifulSoup) -> list[_PrizeRow]:
    prizes: list[_PrizeRow] = []
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = " ".join(filter(None, paragraphs))
    if not text:
        return prizes
    pat = re.compile(
        r"(?:^|[.;•·\n])\s*"
        r"(?P<cat>[A-Za-z0-9\(\)\+\s\u00C0-\u017F]+?)\s*"
        r"(?:paga|entrega|:)?\s*\$"
        r"(?P<amount>[\d\.,]+(?:\s*MM)?)",
        re.IGNORECASE,
    )
    seen: set[str] = set()
    for m in pat.finditer(text):
        categoria_raw = m.group("cat")
        categoria = _sanitize_category(categoria_raw)
        categoria = categoria.rstrip(": ")
        categoria = re.sub(
            r"\s*(?:paga(?:rá|n)?|entrega(?:rá|n)?|otorga(?:rá|n)?)\.?$",
            "",
            categoria,
            flags=re.IGNORECASE,
        )
        if not categoria or categoria.lower().startswith("sorteo"):
            continue
        if categoria in seen:
            continue
        seen.add(categoria)
        premio = _parse_amount("$" + m.group("amount"))
        suffix = text[m.end() :]
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

    return record
