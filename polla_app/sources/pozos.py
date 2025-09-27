"""Parse próximo pozo data from community aggregators."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..exceptions import ScriptError
from ..net import DEFAULT_UA, fetch_html

_logger = logging.getLogger("polla_app.sources.pozos")


def _extract_key_value_pairs(soup: BeautifulSoup) -> dict[str, int]:
    data: dict[str, int] = {}
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        key = cells[0].get_text(" ", strip=True)
        value_text = cells[1].get_text(" ", strip=True)
        value_digits = "".join(ch for ch in value_text if ch.isdigit())
        if not key or not value_digits:
            continue
        data[key] = int(value_digits)
    return data


def get_pozo_openloto(url: str = "https://www.openloto.cl/pozo-del-loto.html", *, ua: str = DEFAULT_UA) -> dict[str, int]:
    """Return pozo dictionary parsed from OpenLoto."""

    html = fetch_html(url, ua=ua)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        raise ScriptError("OpenLoto no contiene tabla de pozos", error_code="OPENLOTO_NO_TABLA")
    return _extract_key_value_pairs(table)


def get_pozo_resultadosloto(url: str = "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/", *, ua: str = DEFAULT_UA) -> dict[str, int]:
    """Return pozo dictionary parsed from ResultadosLotoChile."""

    html = fetch_html(url, ua=ua)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        raise ScriptError("ResultadosLotoChile no contiene tabla de pozos", error_code="RLC_NO_TABLA")
    return _extract_key_value_pairs(table)


class JackpotSnapshot:
    """Utility to capture jackpots with timestamps."""

    def __init__(self, fuente: str, pozos: dict[str, int]):
        self.fuente = fuente
        self.pozos = pozos
        self.captured_at = datetime.now(timezone.utc)

    def to_record(self) -> tuple[str, dict[str, int], datetime]:
        return self.fuente, self.pozos, self.captured_at

