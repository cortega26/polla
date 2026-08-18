"""Shared es-CL number parsing/formatting helpers.

Four consumers historically duplicated these with subtle differences
(pozos.py, stats.py, prices.py, site.py); the union of their semantics
lives here. Behavior is preserved exactly per consumer — when fixing a
separator edge case, fix it here once and extend the conformance tests.
"""

from .exceptions import ParseError


def parse_millones_to_clp(raw: str) -> int:
    """Parse Spanish-formatted MILLONES into integer CLP.

    Examples:
    - "690" -> 690_000_000
    - "4.300" -> 4_300_000_000 (dot as thousands separator)
    - "4,75" -> 4_750_000 (comma as decimal separator)
    - "1.234,56" -> 1_234_560_000
    - "4.300 MM" -> 4_300_000_000
    """

    cleaned = (raw or "").strip().lower()
    if not cleaned:
        raise ParseError("Empty monetary value", context={"raw": raw})

    # Detect explicit units
    multiplier = 1_000_000
    if cleaned.endswith("mm") or "millones" in cleaned:
        multiplier = 1_000_000
        cleaned = cleaned.replace("millones", "").replace("mm", "").strip()
    elif cleaned.endswith("mil"):
        # "1.000 mil" -> 1,000,000 (but in MILLONES context this is rare)
        # If the input expects millions, "mil" might be a suffix for an absolute value
        # that was accidentally passed. We'll honor the "mil" = 1000.
        multiplier = 1_000
        cleaned = cleaned.replace("mil", "").strip()
    elif cleaned.endswith("m") and not cleaned.endswith("mm"):
        # Single M usually means Millions in this context
        multiplier = 1_000_000
        cleaned = cleaned.rstrip("m").strip()

    # Remove currency and whitespace
    cleaned = cleaned.replace("$", "").replace(" ", "")

    # Detect separator intent
    if "." in cleaned and "," in cleaned:
        # Mixed: 1.234,56 -> 1234.56
        # Validate that dots are thousands (3 digits)
        parts = cleaned.split(".")
        for p in parts[1:-1]:
            if len(p) != 3:
                raise ParseError("Invalid thousands separator position", context={"raw": raw})
        if len(parts[-1].split(",")[0]) != 3:
            raise ParseError("Invalid last thousands separator", context={"raw": raw})
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # Only comma.
        parts = cleaned.split(",")
        if len(parts) > 2:
            # 1,234,567
            for p in parts[1:]:
                if len(p) != 3:
                    raise ParseError("Invalid multiple commas", context={"raw": raw})
            cleaned = cleaned.replace(",", "")
        elif len(parts) == 2 and len(parts[1]) == 3:
            # 4,300 -> 4300
            cleaned = cleaned.replace(",", "")
        else:
            # 4,75 -> 4.75
            cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        # Only dot.
        parts = cleaned.split(".")
        if len(parts) > 2:
            # 1.234.567
            for p in parts[1:]:
                if len(p) != 3:
                    raise ParseError("Invalid multiple dots", context={"raw": raw})
            cleaned = cleaned.replace(".", "")
        elif len(parts) == 2 and len(parts[1]) == 3:
            # 4.300 -> 4300
            cleaned = cleaned.replace(".", "")
        else:
            # 4.3 -> 4.3
            pass

    try:
        value = float(cleaned)
    except ValueError as exc:
        raise ParseError(
            f"Unable to parse monetary value: {raw}",
            original_error=exc,
            context={"raw": raw, "processed": cleaned},
        ) from exc

    return int(round(value * multiplier))


def to_number(raw: str) -> float | None:
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


def clean_clp(raw: str) -> int:
    return int(raw.replace(".", "").replace("$", "").replace(" ", ""))


def format_millones(value: int) -> str:
    """Format CLP as 'X.XXX' (millones) with Chilean grouping."""
    return f"{value / 1_000_000:,.0f}".replace(",", ".")
