from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from ..net import fetch_html


def _parse_millones_to_clp(txt: str) -> int:
    n = int(re.sub(r"[^0-9]", "", txt or "0") or "0")
    return n * 1_000_000


def get_pozo_openloto(url: str = "https://www.openloto.cl/pozo-del-loto.html") -> dict[str, int]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    pairs: dict[str, int] = {}
    for label in ["Loto Clásico", "Recargado", "Revancha", "Desquite", "Jubilazo", "Total"]:
        m = re.search(label + r".{0,40}?\$?([\d\.]+)\s*MILLONES", text, re.I)
        if m:
            key = "Jubilazo $1.000.000" if label.startswith("Jubilazo") else (
                "Loto Clásico" if label.startswith("Loto") else ("Total estimado" if label.startswith("Total") else label)
            )
            pairs[key] = _parse_millones_to_clp(m.group(1))
    return pairs


def get_pozo_resultadosloto(url: str = "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/") -> dict[str, int]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    pairs: dict[str, int] = {}
    for label in ["Loto", "Recargado", "Revancha", "Desquite", "Jubilazo", "Total"]:
        m = re.search(label + r".{0,40}?\$?([\d\.]+)\s*MILLONES", text, re.I)
        if m:
            key = "Loto Clásico" if label == "Loto" else (
                "Jubilazo $1.000.000" if label == "Jubilazo" else ("Total estimado" if label == "Total" else label)
            )
            pairs[key] = _parse_millones_to_clp(m.group(1))
    return pairs

