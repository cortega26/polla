"""Shared helpers for source fetchers (Loto pozos, Kino, prices)."""

import json
import re
from typing import Any

from ..exceptions import ParseError
from ..net import FetchMetadata

DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)


def extract_next_data(html: str, *, context: str) -> dict[str, Any]:
    """Extract and parse the ``__NEXT_DATA__`` JSON block from a Next.js page.

    ``context`` names the source in the error messages (e.g. "Kino pendón"
    or "Kino hub"). Raises ParseError on missing block or invalid JSON.
    """
    match = _NEXT_DATA_RE.search(html)
    if not match:
        raise ParseError(
            f"{context} page did not contain __NEXT_DATA__ (site layout changed?)",
            context={"snippet": html[:200]},
        )
    try:
        return json.loads(match.group(1))  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"{context} __NEXT_DATA__ is not valid JSON",
            original_error=exc,
        ) from exc


def build_pozo_payload(
    *,
    metadata: FetchMetadata,
    montos: dict[str, int],
    sorteo: Any,
    fecha: Any,
    fuente: str | None = None,
) -> dict[str, Any]:
    """Build the canonical pozo payload shared by all fetchers.

    The shape is stable across games so the consensus engine and the
    publishers can treat every source identically.
    """
    return {
        "fuente": fuente or metadata.url,
        "fetched_at": metadata.fetched_at.isoformat(),
        "sha256": metadata.sha256,
        "estimado": True,
        "montos": montos,
        "user_agent": metadata.user_agent,
        "sorteo": sorteo,
        "fecha": fecha,
    }


__all__ = ["build_pozo_payload"]
