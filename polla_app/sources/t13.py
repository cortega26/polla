from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from ..net import fetch_html


def _to_int(s: str | None) -> int:
    if not s:
        return 0
    return int(re.sub(r"[^0-9]", "", s) or "0")


def _parse_spanish_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", text, re.I)
    if not m:
        return None
    day, mon, year = m.group(1), m.group(2), m.group(3)
    months = {
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
    mon_n = months.get(mon.lower())
    if not mon_n:
        return None
    try:
        return dt.date(int(year), mon_n, int(day)).isoformat()
    except ValueError:
        return None


def parse_t13_draw(url: str) -> dict[str, Any]:
    """Parse a T13 article for the Ganadores table.

    Returns a dict: {"sorteo": int|None, "fecha": iso|None, "fuente": url, "premios": [..]}
    """
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    m_sor = re.search(r"[Ss]orteo\s+(\d{4,})", text)
    sorteo = int(m_sor.group(1)) if m_sor else None
    fecha = _parse_spanish_date(text)

    anchor = None
    for tag in soup.find_all(["h2", "h3"]):
        if "Ganadores" in tag.get_text(strip=True):
            anchor = tag
            break

    premios: list[dict[str, Any]] = []
    table = anchor.find_next("table") if anchor else None
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
                        "premio_clp": _to_int(premio),
                        "ganadores": _to_int(ganadores),
                    }
                )

    if not premios:
        block = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        pat = re.compile(r"([A-Za-z\s\u00C0-\u017F\$\d\(\)\+]+?)\s*\$([\d\.]+)\s*(\d+)", re.I)
        for cat, monto, gan in pat.findall(block):
            premios.append(
                {
                    "categoria": re.sub(r"\s+", " ", cat).strip(),
                    "premio_clp": _to_int(monto),
                    "ganadores": _to_int(gan),
                }
            )

    return {"sorteo": sorteo, "fecha": fecha, "fuente": url, "premios": premios}

