"""Generate the static data payload consumed by the public dashboard.

The dashboard is a dependency-free static site (HTML/CSS/JS) that reads a
single ``data.json``. This module aggregates the latest Loto and Kino
records plus deduplicated history into that file, so the presentation
layer never touches the network or the pipeline internals.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import API_VERSION

MAX_HISTORY_RECORDS = 100


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: dict[tuple[Any, Any], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        records[(record.get("sorteo"), record.get("fecha"))] = record
    return list(records.values())


def _format_millones(value: int) -> str:
    """Format CLP as 'X.XXX' (millones) with Chilean grouping."""
    return f"{value / 1_000_000:,.0f}".replace(",", ".")


def _game_section(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if not record:
        return None
    pozos = {k: int(v) for k, v in (record.get("pozos_proximo", {}) or {}).items()}
    return {
        "sorteo": record.get("sorteo"),
        "fecha": record.get("fecha"),
        "confidence": record.get("confidence", "unknown"),
        "fuente": record.get("fuente"),
        "pozos_clp": pozos,
        "pozos_millones": {k: _format_millones(v) for k, v in pozos.items()},
        "total_millones": _format_millones(sum(pozos.values())),
    }


def build_site_payload(
    *,
    loto_path: Path,
    kino_path: Path | None,
    summary_path: Path | None,
) -> dict[str, Any]:
    """Aggregate Loto/Kino records into the dashboard payload."""
    loto_records = _load_ndjson(loto_path)
    kino_records = _load_ndjson(kino_path) if kino_path else []

    history = loto_records + kino_records
    history = sorted(
        history,
        key=lambda r: str(r.get("fecha") or ""),
        reverse=True,
    )[:MAX_HISTORY_RECORDS]

    decision: dict[str, Any] = {}
    if summary_path and summary_path.exists():
        decision = json.loads(summary_path.read_text(encoding="utf-8"))

    loto_section = _game_section(loto_records[-1] if loto_records else None)
    kino_section = _game_section(kino_records[-1] if kino_records else None)

    current_prizes: dict[str, int] = {}
    current_prices: dict[str, dict[str, int]] = {}
    if loto_section:
        current_prizes.update(loto_section.get("pozos_clp") or {})
        last_loto = loto_records[-1] if loto_records else None
        if last_loto and last_loto.get("precios"):
            current_prices.update(last_loto["precios"])
    if kino_section:
        current_prizes.update(kino_section.get("pozos_clp") or {})
        last_kino = kino_records[-1] if kino_records else None
        if last_kino and last_kino.get("precios"):
            current_prices.update(last_kino["precios"])

    return {
        "api_version": API_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "last_decision": {
            "status": (decision.get("decision") or {}).get("status", "unknown"),
            "reason": decision.get("publish_reason", ""),
        },
        "loto": loto_section,
        "kino": kino_section,
        "current_prizes_clp": current_prizes,
        "current_prices": current_prices,
        "history": [
            {
                "sorteo": r.get("sorteo"),
                "fecha": r.get("fecha"),
                "confidence": r.get("confidence", "unknown"),
                "pozos_millones": {
                    k: _format_millones(int(v))
                    for k, v in (r.get("pozos_proximo", {}) or {}).items()
                },
            }
            for r in history
        ],
    }


def write_site_data(
    *,
    loto_path: Path,
    output: Path,
    kino_path: Path | None = None,
    summary_path: Path | None = None,
) -> Path:
    """Write the dashboard data payload to ``output``."""
    payload = build_site_payload(
        loto_path=loto_path,
        kino_path=kino_path,
        summary_path=summary_path,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


__all__ = ["build_site_payload", "write_site_data"]
