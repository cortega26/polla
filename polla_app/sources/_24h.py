"""Parsers for 24Horas Loto coverage."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Iterable

from bs4 import BeautifulSoup

from ..exceptions import ScriptError
from ..net import DEFAULT_UA, fetch_html, sha256_text

_logger = logging.getLogger("polla_app.sources.24h")


def _parse_sorteo_from_slug(url: str) -> int | None:
    match = re.search(r"sorteo-(\d+)", url)
    return int(match.group(1)) if match else None


def _clean_int(text: str) -> int:
    cleaned = re.sub(r"[^0-9]", "", text)
    return int(cleaned) if cleaned else 0


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def list_24h_result_urls(index_url: str, *, ua: str = DEFAULT_UA, timeout: int = 20, limit: int = 10) -> list[dict[str, Any]]:
    """Return article metadata from the 24Horas tag index."""

    html = fetch_html(index_url, ua=ua, timeout=timeout)
    soup = BeautifulSoup(html, "html.parser")
    articles: list[dict[str, Any]] = []
    for card in soup.select(".g-box" if soup.select(".g-box") else "article"):
        link = card.find("a")
        if not link or not link.get("href"):
            continue
        url = link["href"]
        sorteo = _parse_sorteo_from_slug(url)
        title = link.get_text(" ", strip=True)
        date_text = ""
        date_el = card.find(class_=re.compile("date", re.IGNORECASE))
        if date_el:
            date_text = date_el.get_text(" ", strip=True)
        articles.append({"url": url, "sorteo": sorteo, "titulo": title, "fecha_texto": date_text})
        if len(articles) >= limit:
            break
    return articles


def _extract_prizes_from_table(table: Any) -> list[dict[str, Any]]:
    prizes: list[dict[str, Any]] = []
    for row in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        if "categor" in cells[0].lower() and "premio" in cells[1].lower():
            continue
        prizes.append(
            {
                "categoria": _normalize_spaces(cells[0]),
                "premio_clp": _clean_int(cells[1]),
                "ganadores": _clean_int(cells[2]),
            }
        )
    return prizes


def _extract_prizes_from_list(elements: Iterable[Any]) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?P<categoria>.+?)\s+\$?(?P<premio>[0-9\.]+)\s+(?P<ganadores>\d+)\s+ganadores",
        re.IGNORECASE,
    )
    prizes: list[dict[str, Any]] = []
    for element in elements:
        text = _normalize_spaces(element.get_text(" ", strip=True))
        match = pattern.search(text)
        if match:
            prizes.append(
                {
                    "categoria": match.group("categoria"),
                    "premio_clp": _clean_int(match.group("premio")),
                    "ganadores": _clean_int(match.group("ganadores")),
                }
            )
    return prizes


def parse_24h_draw(url: str, *, ua: str = DEFAULT_UA, timeout: int = 20) -> dict[str, Any]:
    """Parse a 24Horas article."""

    html = fetch_html(url, ua=ua, timeout=timeout)
    sha = sha256_text(html)
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")
    premios = _extract_prizes_from_table(table) if table else []
    if not premios:
        premios = _extract_prizes_from_list(soup.find_all("li"))

    if not premios:
        raise ScriptError("No se pudo extraer la tabla de premios desde 24Horas", error_code="24H_NO_PREMIOS")

    sorteo = _parse_sorteo_from_slug(url)
    if not sorteo:
        heading = soup.find(["h1", "h2"])
        if heading:
            match = re.search(r"sorteo\s+(\d+)", heading.get_text(" ", strip=True), re.IGNORECASE)
            if match:
                sorteo = int(match.group(1))

    fecha_text = ""
    date_el = soup.find(class_=re.compile("date", re.IGNORECASE))
    if date_el:
        fecha_text = _normalize_spaces(date_el.get_text(" ", strip=True))

    title_tag = soup.find("title")
    titulo = title_tag.get_text(strip=True) if title_tag else None

    return {
        "sorteo": sorteo,
        "fecha": fecha_text or None,
        "fuente": url,
        "premios": premios,
        "sha256": sha,
        "titulo": titulo,
    }

