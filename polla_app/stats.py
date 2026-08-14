"""Sync the public "geek stats" dataset (Google Sheets CSV) into the dashboard.

The dashboard is a static site, so it cannot fetch the spreadsheet directly
(browser CORS blocks docs.google.com). Instead, the pipeline downloads the
public CSV once per run and normalizes it into ``site/stats.json``:
game metadata, probabilities, combinations, prices and expected returns.

The CSV URL is configurable via ``POLLA_STATS_URL``; fetching respects
robots.txt and the shared rate limiter (``net.fetch_html``).
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import API_VERSION
from .net import fetch_html

LOGGER = logging.getLogger(__name__)

# Public "Protegida Chile" sheet (Loterías metadata/probabilities).
DEFAULT_STATS_URL = (
    "https://docs.google.com/spreadsheets/d/16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc/"
    "gviz/tq?tqx=out:csv&gid=0"
)
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"


def _to_number(raw: str) -> float | None:
    """Parse Chilean-formatted numbers (dots as thousands, comma as decimal)."""
    value = (raw or "").strip().replace("$", "").replace("%", "")
    if not value or value.lower() in {"n/a", "na", "-"}:
        return None
    if "1 en" in value:
        value = value.split("1 en", 1)[1].strip()
    value = value.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _clean_rows(reader: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw in reader:
        rows.append([(cell or "").strip() for cell in raw])
    return rows


def _normalize_stats(header: list[str], rows: list[list[str]]) -> dict[str, Any]:
    """Group CSV rows by game (``Nombre``) and normalize numeric columns."""
    games: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        record: dict[str, Any] = dict(zip(header, row, strict=False))
        game = record.get("Nombre") or "Sin nombre"
        normalized = dict(record)
        for col in (
            "Precio o apuesta",
            "Precio Acumulado",
            "Total de Números",
            "Combinaciones totales",
            "Probabilidad de ganar",
            "Pozo categoría",
            "Premio Categoría",
            "Premio acumulado",
            "% Retorno Esperado Individual",
            "% Retorno esperado Acumulado",
        ):
            numeric = _to_number(record.get(col, ""))
            if numeric is not None:
                normalized[f"{col} (num)"] = numeric
        games.setdefault(game, []).append(normalized)

    return {
        "games": games,
        "game_count": len(games),
        "row_count": sum(len(v) for v in games.values()),
    }


def build_stats_payload(csv_text: str) -> dict[str, Any]:
    """Parse the raw CSV text into the dashboard stats payload."""
    header: list[str] = []
    rows: list[list[str]] = []
    reader = csv.reader(io.StringIO(csv_text))
    for index, raw in enumerate(reader):
        if index == 0:
            header = [cell.strip() for cell in raw]
            continue
        rows.append([(cell or "").strip() for cell in raw])

    stats = _normalize_stats(header, rows)
    return {
        "api_version": API_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "columns": header,
        **stats,
    }


def write_site_stats(csv_url: str, output: Any, *, ua: str = DEFAULT_UA) -> Path:
    """Download the public stats CSV and write ``output`` (a Path or str)."""
    output_path = Path(output)
    metadata = fetch_html(csv_url, ua=ua, timeout=20, retries=2)
    payload = build_stats_payload(metadata.html)
    payload["source_url"] = csv_url
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def resolve_stats_url() -> str:
    """Return the configured stats CSV URL (env override or default)."""
    return os.getenv("POLLA_STATS_URL") or DEFAULT_STATS_URL


__all__ = ["DEFAULT_STATS_URL", "build_stats_payload", "resolve_stats_url", "write_site_stats"]
