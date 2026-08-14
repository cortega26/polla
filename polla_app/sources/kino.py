"""Kino (Lotería de Concepción) próximo pozo parser.

Kino ya no es operado por Polla Chilena; desde su traspaso, los pozos
estimados del próximo sorteo se publican en el "pendón" oficial de
Lotería de Concepción:

    https://pendon-kino.loteria.cl/pendonkino

La página es server-rendered (Next.js) y expone los datos en el bloque
``__NEXT_DATA__``, por lo que se parsea sin navegador. El payload
resultante sigue la misma forma que los agregadores de Loto
(``fuente``, ``fetched_at``, ``sha256``, ``estimado``, ``montos``,
``sorteo``, ``fecha``) para que el pipeline de consenso lo trate igual.

Reglas del juego (para validación):
- Se eligen 14 números del 1 al 25.
- Sorteos: miércoles, viernes y domingo.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from ..exceptions import ParseError
from ..net import fetch_html

LOGGER = logging.getLogger(__name__)

PENDON_URL = "https://pendon-kino.loteria.cl/pendonkino"
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

# Map field -> canonical category label. Values are expressed in MILLONES.
# Fields with value 0 ("no estimado publicado") are omitted to avoid
# phantom zeros in the consensus engine.
_POZO_FIELDS: dict[str, str] = {
    "F_SrtKinAproxSrt": "Kino",
    "F_SrtKinRevAprox": "Kino Revancha",
    "F_SrtKinRev2Aprox": "Kino Revancha 2",
    "F_SrtKinRevSd2Aprox": "Kino Sueldo 50",
    "F_SrtKinRevCJ4Aprox": "Kino Sueldo 30",
    "F_SrtKinRevCJ2Aprox": "Kino Casa",
    "F_SrtKinRevGMSdAprox": "Kino Gran Sueldo",
}

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)


def _extract_next_data(html: str) -> dict[str, Any]:
    """Extract and parse the ``__NEXT_DATA__`` JSON block from a Next.js page."""
    match = _NEXT_DATA_RE.search(html)
    if not match:
        raise ParseError(
            "Kino pendón page did not contain __NEXT_DATA__ (site layout changed?)",
            context={"snippet": html[:200]},
        )
    try:
        return json.loads(match.group(1))  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise ParseError(
            "Kino pendón __NEXT_DATA__ is not valid JSON",
            original_error=exc,
        ) from exc


def _extract_pendon(data: dict[str, Any]) -> dict[str, Any]:
    """Pull ``pageProps.pendon`` out of the __NEXT_DATA__ payload."""
    props = (data.get("props") or {}).get("pageProps") or {}
    pendon = props.get("pendon") or {}
    if pendon.get("error") is not None:
        raise ParseError(
            "Kino pendón reported an upstream error",
            context={"error": str(pendon.get("error"))[:200]},
        )
    return pendon


def _parse_pendon_fecha(raw: str | None) -> str | None:
    """Normalize ``2026/08/14`` to an ISO ``2026-08-14`` string."""
    if not raw:
        return None
    try:
        year, month, day = raw.split("/")
        return date(int(year), int(month), int(day)).isoformat()
    except (ValueError, AttributeError):
        return None


def _extract_montos(outputs: dict[str, Any]) -> dict[str, int]:
    """Map pendón outputs to CLP amounts, skipping zero/absent estimates."""
    montos: dict[str, int] = {}
    for field, label in _POZO_FIELDS.items():
        value = outputs.get(field)
        if not isinstance(value, int | float) or value <= 0:
            continue
        montos[label] = int(value) * 1_000_000
    return montos


def _extract_pozo_info(
    data: dict[str, Any], outputs: dict[str, Any]
) -> tuple[int | None, str | None]:
    """Return (sorteo, fecha_iso) for the upcoming Kino draw."""
    page_props = (data.get("props") or {}).get("pageProps") or {}
    sorteo: int | None = page_props.get("firstSorteo")
    if isinstance(sorteo, bool) or not isinstance(sorteo, int):
        sorteo = None
    fecha = _parse_pendon_fecha(outputs.get("F_FechaTxt"))
    return sorteo, fecha


def _fetch_pozo_kino(
    *, url: str, ua: str, timeout: int, retries: int | None = None
) -> dict[str, Any]:
    metadata = fetch_html(url, ua=ua, timeout=timeout, retries=retries)
    data = _extract_next_data(metadata.html)
    pendon = _extract_pendon(data)
    outputs = pendon.get("outputs") or {}
    montos = _extract_montos(outputs)
    if not montos:
        raise ParseError(
            "No valid Kino pozo amounts found in pendón content",
            context={"url": url, "outputs": outputs},
        )
    sorteo, fecha = _extract_pozo_info(data, outputs)

    # Validate against known Kino constraints before returning.
    if len(montos) != len(set(montos.keys())):
        raise ParseError("Duplicate Kino category labels", context={"montos": montos})
    if sorteo is not None and sorteo <= 0:
        raise ParseError("Kino sorteo number is invalid", context={"sorteo": sorteo})

    # Sanity-check the embedded HTML with BeautifulSoup only to confirm the
    # page rendered content (defensive against a stub page without data).
    soup = BeautifulSoup(metadata.html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "Kino" not in text and "kino" not in text:
        LOGGER.warning("Kino pendón page content looks unexpected (missing 'Kino' text)")

    return {
        "fuente": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(metadata.html.encode("utf-8")).hexdigest(),
        "estimado": True,
        "montos": montos,
        "user_agent": metadata.user_agent,
        "sorteo": sorteo,
        "fecha": fecha,
    }


def get_pozo_kino(
    url: str = PENDON_URL,
    *,
    ua: str = DEFAULT_UA,
    timeout: int = 20,
    retries: int | None = None,
) -> dict[str, Any]:
    """Fetch próximo pozo estimates for Kino from the official pendón."""
    return _fetch_pozo_kino(url=url, ua=ua, timeout=timeout, retries=retries)


__all__ = ["get_pozo_kino", "PENDON_URL"]
