"""Shared helpers for source fetchers (Loto pozos, Kino, prices)."""

from typing import Any

from ..net import FetchMetadata


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
