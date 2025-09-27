from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from ..net import fetch_html


INDEX_URL = "https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html"


def list_24h_result_urls(index_url: str = INDEX_URL, limit: int = 10) -> list[str]:
    """Return last N Loto result article URLs from the tag index."""
    html = fetch_html(index_url)
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    # Heuristic: capture anchors whose href contains '/loto/' or 'resultados-loto'
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/loto/" in href or "resultados-loto" in href:
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = "https://www.24horas.cl" + href
            if href not in urls:
                urls.append(href)
        if len(urls) >= limit:
            break
    return urls


def parse_24h_draw(url: str) -> dict[str, Any]:
    """Parse a 24Horas article for category/premio/ganadores.

    Reuses the robust fallback parsing patterns similar to T13.
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Try to locate a table first
    premios: list[dict[str, Any]] = []
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        start = 1 if rows and "Categor" in rows[0].get_text() else 0
        for tr in rows[start:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) >= 3:
                categoria, premio, ganadores = cells[0], cells[1], cells[2]
                premios.append(
                    {
                        "categoria": re.sub(r"\s+", " ", categoria).strip(),
                        "premio_clp": int(re.sub(r"[^0-9]", "", premio) or "0"),
                        "ganadores": int(re.sub(r"[^0-9]", "", ganadores) or "0"),
                    }
                )

    if not premios:
        block = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        pat = re.compile(r"([A-Za-z\s\u00C0-\u017F\$\d\(\)\+]+?)\s*\$([\d\.]+)\s*(\d+)", re.I)
        for cat, monto, gan in pat.findall(block):
            premios.append(
                {
                    "categoria": re.sub(r"\s+", " ", cat).strip(),
                    "premio_clp": int(re.sub(r"[^0-9]", "", monto) or "0"),
                    "ganadores": int(re.sub(r"[^0-9]", "", gan) or "0"),
                }
            )

    # Extract potential sorteo number
    sorteo = None
    m_sor = re.search(r"sorteo\s+(\d{4,})", text, re.I)
    if m_sor:
        try:
            sorteo = int(m_sor.group(1))
        except ValueError:
            sorteo = None

    # Extract date best-effort
    fecha = None
    m_date = re.search(r"(\d{1,2})\s+de\s+\w+\s+de\s+(\d{4})", text, re.I)
    if m_date:
        # leave as free-form to avoid month mapping brittleness on 24h variants
        fecha = " ".join(m_date.groups())

    return {"sorteo": sorteo, "fecha": fecha, "fuente": url, "premios": premios}

