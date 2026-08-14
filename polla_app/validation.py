"""Game-aware data validation shared by the pipeline and health checks.

A suspicious result must never be published silently: every validation
issue is reported with the offending value so operators can act.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

# Maximum plausible jackpot (CLP) for a single category, per game.
# Loto pozos can reach tens of billions of CLP; Kino totals are smaller.
_MAX_AMOUNT_CLP = 100_000_000_000  # 100.000 MM
_MIN_AMOUNT_CLP = 1_000_000  # at least 1 MM per reported category

# Kino rules: 14 numbers drawn from 1..25.
KINO_NUMBERS_COUNT = 14
KINO_MAX_NUMBER = 25


def _amounts_issues(montos: Mapping[str, Any]) -> list[str]:
    """Report issues for a mapping of category -> amount (CLP)."""
    issues: list[str] = []
    if not montos:
        issues.append("no_amounts")
        return issues
    for category, raw in montos.items():
        try:
            value = int(raw)
        except (TypeError, ValueError):
            issues.append(f"amount_not_int:{category}={raw!r}")
            continue
        if value < _MIN_AMOUNT_CLP:
            issues.append(f"amount_too_small:{category}={value}")
        if value > _MAX_AMOUNT_CLP:
            issues.append(f"amount_too_large:{category}={value}")
    return issues


def _sorteo_issues(sorteo: Any) -> list[str]:
    if sorteo is None:
        return []
    if isinstance(sorteo, bool) or not isinstance(sorteo, int) or sorteo <= 0:
        return [f"invalid_sorteo:{sorteo!r}"]
    return []


def _fecha_issues(fecha: Any) -> list[str]:
    if fecha is None:
        return []
    if not isinstance(fecha, str):
        return [f"invalid_fecha_type:{type(fecha).__name__}"]
    try:
        datetime.fromisoformat(fecha)
    except ValueError:
        return [f"invalid_fecha:{fecha!r}"]
    return []


def validate_amounts(montos: Mapping[str, Any]) -> list[str]:
    """Validate a single game's amount mapping (CLP). Returns issue codes."""
    return _amounts_issues(montos)


def validate_kino_numbers(numbers: Any) -> list[str]:
    """Validate a Kino winning-numbers list (14 unique numbers in 1..25)."""
    if not isinstance(numbers, list | tuple) or len(numbers) != KINO_NUMBERS_COUNT:
        return [
            f"kino_wrong_number_count:"
            f"{len(numbers) if isinstance(numbers, list | tuple) else type(numbers).__name__}"
        ]
    issues: list[str] = []
    seen: set[int] = set()
    for raw in numbers:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            issues.append(f"kino_non_numeric:{raw!r}")
            continue
        if value < 1 or value > KINO_MAX_NUMBER:
            issues.append(f"kino_out_of_range:{value}")
        if value in seen:
            issues.append(f"kino_duplicate:{value}")
        seen.add(value)
    return issues


def validate_pozo_payload(payload: Mapping[str, Any]) -> list[str]:
    """Validate a source payload (same shape produced by the fetchers)."""
    issues = _amounts_issues(payload.get("montos") or {})
    issues.extend(_sorteo_issues(payload.get("sorteo")))
    issues.extend(_fecha_issues(payload.get("fecha")))
    return issues


def validate_fecha_is_past(fecha: str, *, today: date | None = None) -> bool:
    """Return True when ``fecha`` (ISO) is today or in the past."""
    parsed = datetime.fromisoformat(fecha).date()
    return parsed <= (today or date.today())


__all__ = [
    "KINO_NUMBERS_COUNT",
    "KINO_MAX_NUMBER",
    "validate_amounts",
    "validate_fecha_is_past",
    "validate_kino_numbers",
    "validate_pozo_payload",
]
