"""Utility functions to validate draw information across sources."""

from __future__ import annotations

from typing import Iterable, Sequence

from .models import ComparisonResult, DrawSourceRecord, PrizeBreakdown


def determine_last_draw(records: Sequence[DrawSourceRecord]) -> DrawSourceRecord:
    """Pick the record with the highest sorteo or most recent date."""

    def sort_key(record: DrawSourceRecord) -> tuple[int, str]:
        sorteo = record.sorteo or 0
        fecha = record.fecha or ""
        return sorteo, fecha

    return max(records, key=sort_key)


def _map_prizes(record: DrawSourceRecord) -> dict[str, PrizeBreakdown]:
    mapping: dict[str, PrizeBreakdown] = {}
    for prize in record.premios:
        mapping[prize.categoria.lower()] = prize
    return mapping


def compare_records(primary: DrawSourceRecord, secondary: DrawSourceRecord) -> ComparisonResult:
    """Compare prize tables between two records."""

    primary_map = _map_prizes(primary)
    secondary_map = _map_prizes(secondary)
    differences: list[str] = []

    for categoria, primary_prize in primary_map.items():
        if categoria not in secondary_map:
            differences.append(f"{primary_prize.categoria}: no aparece en {secondary.fuente}")
            continue
        secondary_prize = secondary_map[categoria]
        if primary_prize.premio_clp != secondary_prize.premio_clp or primary_prize.ganadores != secondary_prize.ganadores:
            differences.append(
                f"{primary_prize.categoria}: {primary_prize.premio_clp}/{primary_prize.ganadores} vs "
                f"{secondary_prize.premio_clp}/{secondary_prize.ganadores}"
            )

    for categoria, secondary_prize in secondary_map.items():
        if categoria not in primary_map:
            differences.append(f"{secondary_prize.categoria}: solo en {secondary.fuente}")

    return ComparisonResult(fuente=secondary.fuente, matches=not differences, differences=differences)


def summarize_differences(comparisons: Iterable[ComparisonResult]) -> dict[str, int]:
    """Aggregate difference counts per comparison."""

    summary: dict[str, int] = {}
    for comparison in comparisons:
        summary[comparison.fuente] = len(comparison.differences)
    return summary

