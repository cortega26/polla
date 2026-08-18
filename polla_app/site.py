"""Generate the static data payload consumed by the public dashboard.

The dashboard is a dependency-free static site (HTML/CSS/JS) that reads a
single ``data.json``. This module aggregates the latest Loto and Kino
records plus deduplicated history into that file, so the presentation
layer never touches the network or the pipeline internals.
"""

import json
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import API_VERSION
from .io import read_json, read_jsonl
from .numbers import format_millones as _format_millones

LOGGER = logging.getLogger(__name__)

MAX_HISTORY_RECORDS = 100

# Category labels that identify a Kino record (mirror of the Kino-only
# labels in polla_app/sources/kino.py:_POZO_FIELDS values). A record whose
# ``pozos_proximo`` carries any of these keys is a Kino record; anything
# else is treated as Loto.
_KINO_LABELS = frozenset(
    {
        "Kino",
        "ReKino",
        "RequeteKino",
        "Chao Jefe $2 Millones",
        "Chao Jefe $3 Millones",
        "Súper Combo Marraqueta",
        "Kino Gran Sueldo",
    }
)


def _load_state_records(path: Path) -> list[dict[str, Any]]:
    """Load pipeline state records, skipping invalid JSON lines.

    The state file mixes Loto and Kino draws (see plan 030 for per-game
    files), so classification happens later via :func:`_classify_game`.
    """
    return read_jsonl(path, tolerant=True)


def _classify_game(record: Mapping[str, Any]) -> str:
    """Return ``"kino"`` for Kino records, ``"loto"`` otherwise."""
    pozos = record.get("pozos_proximo") or {}
    if any(label in _KINO_LABELS for label in pozos):
        return "kino"
    return "loto"


def _merge_history_records(*groups: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Merge record groups into history, deduped by ``(sorteo, fecha)``.

    Later groups override earlier ones for the same draw, so current
    ``normalized.jsonl`` records stay fresher than state-file copies.
    """
    merged: dict[tuple[Any, Any], dict[str, Any]] = {}
    for group in groups:
        for record in group:
            merged[(record.get("sorteo"), record.get("fecha"))] = dict(record)
    return list(merged.values())


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


def _dedup_key(record: dict[str, Any]) -> tuple[Any, Any]:
    return (record.get("sorteo"), record.get("fecha"))


def build_site_payload(
    *,
    loto_path: Path,
    kino_path: Path | None,
    summary_path: Path | None,
    previous_payload: Mapping[str, Any] | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Aggregate Loto/Kino records into the dashboard payload.

    When a game produced no records this run (ingest failure), its section is
    reused from ``previous_payload`` (e.g. the last successfully deployed
    ``data.json``), so a single-game outage never blanks the dashboard.

    History is sourced from the pipeline state file (``state_path``) when
    available — it accumulates bounded per-draw history across runs — plus
    the current ``normalized.jsonl`` records, which may be fresher within the
    same run.
    """
    loto_records = read_jsonl(loto_path, dedup_key=_dedup_key)
    kino_records = read_jsonl(kino_path, dedup_key=_dedup_key) if kino_path else []

    state_loto: list[dict[str, Any]] = []
    state_kino: list[dict[str, Any]] = []
    if state_path:
        for record in _load_state_records(state_path):
            if _classify_game(record) == "kino":
                state_kino.append(record)
            else:
                state_loto.append(record)

    history = sorted(
        _merge_history_records(state_loto, loto_records, state_kino, kino_records),
        key=lambda r: str(r.get("fecha") or ""),
        reverse=True,
    )[:MAX_HISTORY_RECORDS]

    decision: dict[str, Any] = {}
    if summary_path and summary_path.exists():
        decision = read_json(summary_path)

    loto_section = _game_section(loto_records[-1] if loto_records else None)
    kino_section = _game_section(kino_records[-1] if kino_records else None)
    if previous_payload:
        if loto_section is None and previous_payload.get("loto"):
            loto_section = previous_payload["loto"]
        if kino_section is None and previous_payload.get("kino"):
            kino_section = previous_payload["kino"]

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
        "generated_at": datetime.now(UTC).isoformat(),
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
    previous_payload: Mapping[str, Any] | None = None,
    state_path: Path | None = None,
    payload: Mapping[str, Any] | None = None,
) -> Path:
    """Write the dashboard data payload to ``output``.

    ``payload`` may be a prebuilt payload from :func:`build_site_payload`
    (avoids a duplicate build + NDJSON re-read when the caller already built
    it); when ``None`` it is built here for backward compatibility.
    """
    if payload is None:
        payload = build_site_payload(
            loto_path=loto_path,
            kino_path=kino_path,
            summary_path=summary_path,
            previous_payload=previous_payload,
            state_path=state_path,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output


__all__ = ["build_site_payload", "write_site_data"]
