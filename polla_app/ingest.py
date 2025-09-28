"""High-level ingestion pipeline for alternative lottery sources."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .sources import (
    get_pozo_openloto,
    get_pozo_resultadosloto,
    list_24h_result_urls,
    parse_24h_draw,
)

LOGGER = logging.getLogger(__name__)

Parser = Callable[[str], dict[str, Any]]
PozoFetcher = Callable[[], dict[str, Any]]

PARSERS: dict[str, Parser] = {"24h": parse_24h_draw}

POZO_FETCHERS: tuple[PozoFetcher, ...] = (
    # Prefer resultadoslotochile.com as primary; openloto as fallback
    get_pozo_resultadosloto,
    get_pozo_openloto,
)


def _collect_pozos() -> tuple[dict[str, Any], ...]:
    collected: list[dict[str, Any]] = []
    for fetcher in POZO_FETCHERS:
        try:
            data = fetcher()
        except Exception as exc:  # pragma: no cover - network safeguards
            LOGGER.warning("Pozo fetcher %s failed: %s", fetcher.__name__, exc)
            continue
        if data.get("montos"):
            collected.append(data)
    return tuple(collected)


def ingest_draw(
    sorteo_url: str,
    *,
    source: str = "24h",
    include_pozos: bool = True,
) -> dict[str, Any]:
    """Parse a draw from the chosen source and enrich it with próximo pozo data."""

    key = source.lower()
    if key not in PARSERS:
        raise ValueError(f"Unsupported source: {source}")

    parser = PARSERS[key]
    record = parser(sorteo_url)

    provenance = record.setdefault("provenance", {})
    provenance["ingested_at"] = datetime.now(timezone.utc).isoformat()
    provenance.setdefault("url", sorteo_url)
    provenance.setdefault("source", key)

    if include_pozos:
        collected = _collect_pozos()
        if collected:
            primary = collected[0]
            merged = dict(primary.get("montos", {}))
            for alt in collected[1:]:
                for categoria, monto in alt.get("montos", {}).items():
                    merged.setdefault(categoria, monto)
            record["pozos_proximo"] = merged
            provenance["pozos"] = {
                "primary": {
                    "fuente": primary.get("fuente"),
                    "fetched_at": primary.get("fetched_at"),
                    "user_agent": primary.get("user_agent"),
                },
            }
            if len(collected) > 1:
                provenance["pozos"]["alternatives"] = [
                    {
                        "fuente": item.get("fuente"),
                        "fetched_at": item.get("fetched_at"),
                        "user_agent": item.get("user_agent"),
                    }
                    for item in collected[1:]
                ]
    return record


__all__ = ["ingest_draw", "list_24h_result_urls"]
