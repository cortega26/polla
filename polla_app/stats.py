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


# Maps a stats-sheet category to the pipeline's scraped pozo categories.
# A callable receives the stats row and returns the real CLP prize (or None).
# Sums handle sheet rows that aggregate several scraped categories
# (e.g. sheet "Jubilazo" = pipeline "Jubilazo $1.000.000" + "Jubilazo $500.000").
def _sum_prizes(prizes: dict[str, Any], *categories: str) -> int | None:
    """Sum the scraped prizes present for the given categories (zeros omitted)."""
    values = [
        int(prizes[category])
        for category in categories
        if isinstance(prizes.get(category), int | float) and prizes[category] > 0
    ]
    if not values:
        return None
    return sum(values)


def _real_prize_for(category: str, row: dict[str, Any], prizes: dict[str, Any]) -> int | None:
    """Resolve the live scraped prize for a stats-sheet row, if mappable."""
    if category == "Loto":
        lookup = {
            "Loto Clásico": lambda: prizes.get("Loto Clásico"),
            "Recargado": lambda: prizes.get("Recargado"),
            "Revancha": lambda: prizes.get("Revancha"),
            "Desquite": lambda: prizes.get("Desquite"),
            "Jubilazo": lambda: _sum_prizes(prizes, "Jubilazo $1.000.000", "Jubilazo $500.000"),
            "Jubilazo 50 años": lambda: _sum_prizes(
                prizes, "Jubilazo 50 años $1.000.000", "Jubilazo 50 años $500.000"
            ),
            # "Multiplicar" has no pozo of its own
        }
        resolver = lookup.get(row.get("Categoría", ""))
        return resolver() if resolver else None
    if category == "Kino":
        # The pendón publishes the total estimated Kino pool, not per-variant
        # breakdowns (Club Kino / Rekino / ...), so only the main row maps.
        if row.get("Categoría") == "Club Kino":
            return prizes.get("Kino")
    return None


def merge_real_prices(
    stats: dict[str, Any],
    prices: dict[str, Any],
) -> dict[str, Any]:
    """Overlay live scraped prices (delta + cumulative) onto the stats payload.

    Loto prices change on special draws, so the sheet's manual price columns
    are replaced by the per-draw scrape for Loto rows. Games without a public
    per-draw price source (e.g. Kino, gated behind the authenticated hub) keep
    the sheet prices but are flagged ``precio_estatico: True`` so the UI can
    render them as reference values.
    """
    for rows in stats.get("games", {}).values():
        for row in rows:
            category = row.get("Categoría", "")
            scraped = (prices or {}).get(category)
            if scraped:
                row["precio_real_clp"] = scraped.get("delta_clp")
                row["precio_acumulado_clp"] = scraped.get("acumulado_clp")
                row["precio_estatico"] = False
            else:
                row["precio_real_clp"] = None
                row["precio_acumulado_clp"] = None
                row["precio_estatico"] = True
    return stats


def merge_real_prizes(
    stats: dict[str, Any],
    prizes: dict[str, Any],
) -> dict[str, Any]:
    """Overlay live scraped prizes onto the stats payload.

    The sheet's manual "Premio Categoría"/"Premio acumulado" columns go stale
    between draws, so they are never published as current data. Each row
    receives ``premio_real_clp`` (when a live mapping exists) and
    ``retorno_real_pct`` computed as prize / combinations / effective bet
    (real scraped price when available, sheet price otherwise). Rows without
    a live mapping get ``None`` and the UI renders "—" instead of stale values.
    """
    for game, rows in stats.get("games", {}).items():
        for row in rows:
            real = _real_prize_for(game, row, prizes)
            row["premio_real_clp"] = real
            combinations = row.get("Combinaciones totales (num)")
            bet = row.get("precio_real_clp")
            if bet is None:
                bet = row.get("Precio o apuesta (num)")
            if real is not None and combinations and bet:
                row["retorno_real_pct"] = round(real / combinations / bet * 100, 2)
            else:
                row["retorno_real_pct"] = None
            # Strip stale manual prizes so they can never be shown as current.
            for stale_col in (
                "Premio Categoría",
                "Premio acumulado",
                "Premio Categoría (num)",
                "Premio acumulado (num)",
                "% Retorno Esperado Individual",
                "% Retorno esperado Acumulado",
                "% Retorno Esperado Individual (num)",
                "% Retorno esperado Acumulado (num)",
            ):
                row.pop(stale_col, None)
    return stats


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


def write_site_stats(
    csv_url: str,
    output: Any,
    *,
    ua: str = DEFAULT_UA,
    prizes: dict[str, Any] | None = None,
    prices: dict[str, Any] | None = None,
) -> Path:
    """Download the public stats CSV and write ``output`` (a Path or str).

    When ``prizes`` (live scraped pozos, category -> CLP) is provided, the
    payload is overlaid with the current prizes via :func:`merge_real_prizes`.
    When ``prices`` (live scraped Loto price structure) is provided, sheet
    prices are replaced by the per-draw values via :func:`merge_real_prices`.
    """
    output_path = Path(output)
    metadata = fetch_html(csv_url, ua=ua, timeout=20, retries=2)
    payload = build_stats_payload(metadata.html)
    payload["source_url"] = csv_url
    # Merges always run: empty live data marks rows as reference ("ref") and
    # strips stale manual prize columns, so the UI never presents them live.
    payload = merge_real_prices(payload, prices or {})
    payload = merge_real_prizes(payload, prizes or {})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def resolve_stats_url() -> str:
    """Return the configured stats CSV URL (env override or default)."""
    return os.getenv("POLLA_STATS_URL") or DEFAULT_STATS_URL


__all__ = ["DEFAULT_STATS_URL", "build_stats_payload", "resolve_stats_url", "write_site_stats"]
