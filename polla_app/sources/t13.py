"""Parser for T13 articles containing Loto draw results."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable

from bs4 import BeautifulSoup

from ..exceptions import ScriptError
from ..net import DEFAULT_UA, fetch_html, sha256_text

_logger = logging.getLogger("polla_app.sources.t13")

SPANISH_MONTHS = {
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


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _parse_int(text: str) -> int:
    cleaned = re.sub(r"[^0-9]", "", text)
    return int(cleaned) if cleaned else 0


def _parse_money(text: str) -> int:
    cleaned = re.sub(r"[^0-9]", "", text)
    return int(cleaned) if cleaned else 0


def _extract_table_rows(table: Any) -> Iterable[dict[str, Any]]:
    for row in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        if "categor" in cells[0].lower() and "premio" in cells[1].lower():
            # header row
            continue
        categoria = _normalize_spaces(cells[0])
        premio = _parse_money(cells[1])
        ganadores = _parse_int(cells[2]) if len(cells) >= 3 else 0
        yield {"categoria": categoria, "premio_clp": premio, "ganadores": ganadores}


def _extract_paragraph_rows(elements: Iterable[Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<categoria>.+?):\s*\$?(?P<premio>[0-9\.]+)(?:\s+pesos)?(?:\s+(?P<ganadores>\d+))?",
        re.IGNORECASE,
    )
    for element in elements:
        text = _normalize_spaces(element.get_text(" ", strip=True))
        match = pattern.search(text)
        if match:
            ganadores_text = match.group("ganadores") or ""
            results.append(
                {
                    "categoria": match.group("categoria"),
                    "premio_clp": _parse_money(match.group("premio")),
                    "ganadores": _parse_int(ganadores_text),
                }
            )
    return results


def _extract_date(text: str) -> str | None:
    text_norm = text.lower()
    pattern = re.compile(
        r"(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})",
        re.IGNORECASE,
    )
    match = pattern.search(text_norm)
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2).replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    month = SPANISH_MONTHS.get(month_name)
    if not month:
        return None
    year = int(match.group(3))
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def parse_t13_draw(url: str, *, ua: str = DEFAULT_UA, timeout: int = 20) -> dict[str, Any]:
    """Parse a T13 draw article and return normalized data."""

    html = fetch_html(url, ua=ua, timeout=timeout)
    sha = sha256_text(html)
    soup = BeautifulSoup(html, "html.parser")

    heading = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if "ganadores" in tag.get_text(" ", strip=True).lower():
            heading = tag
            break
    if heading is None:
        raise ScriptError("No se encontró la sección de ganadores en la nota de T13", error_code="NO_GANADORES")

    table = heading.find_next("table")
    premios: list[dict[str, Any]] = []
    if table:
        premios = list(_extract_table_rows(table))

    if not premios:
        fallback_elements = []
        sibling = heading
        for _ in range(10):
            sibling = sibling.find_next_sibling()
            if sibling is None:
                break
            if sibling.name in {"p", "div", "li"}:
                fallback_elements.append(sibling)
        premios = _extract_paragraph_rows(fallback_elements)

    if not premios:
        raise ScriptError("No fue posible extraer premios desde la nota de T13", error_code="NO_PREMIOS")

    page_text = soup.get_text(" ", strip=True)
    sorteo_match = re.search(r"sorteo\s+(\d+)", page_text, re.IGNORECASE)
    sorteo = int(sorteo_match.group(1)) if sorteo_match else None
    fecha = _extract_date(page_text)

    title_tag = soup.find("title")
    titulo = title_tag.get_text(strip=True) if title_tag else None

    return {
        "sorteo": sorteo,
        "fecha": fecha,
        "fuente": url,
        "premios": premios,
        "sha256": sha,
        "titulo": titulo,
    }

