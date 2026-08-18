"""Conformance suite for the shared es-CL number helpers (``polla_app.numbers``)."""

import pytest

from polla_app.exceptions import ParseError
from polla_app.numbers import clean_clp, format_millones, parse_millones_to_clp, to_number


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("690", 690_000_000),
        ("$ 690", 690_000_000),
        ("4.300", 4_300_000_000),
        ("4,75", 4_750_000),
        ("1.234,56", 1_234_560_000),
        ("4300", 4_300_000_000),
        ("$ 4.300", 4_300_000_000),
        ("0,5", 500_000),
        ("4.300 MM", 4_300_000_000),
        ("4,3 M", 4_300_000),
        (
            "1.000.000 Mil",
            1_000_000_000,
        ),  # Mil as thousands of Millions (not used much, but testing suffix)
        ("7500", 7_500_000_000),
    ],
)
def test_parse_millones_to_clp_valid(raw: str, expected: int) -> None:
    assert parse_millones_to_clp(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " ",
        "$",
        "abc",
        "1.2.3.4",  # Ambiguous
    ],
)
def test_parse_millones_to_clp_invalid(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_millones_to_clp(raw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("99.999", 99_999_000_000),  # large thousands separator (dot = thousands)
        ("0,1", 100_000),  # sub-million (comma = decimal)
        ("1.234.567", 1_234_567_000_000),  # three-part dot-separated thousands
    ],
)
def test_parse_millones_to_clp_large_ranges(raw: str, expected: int) -> None:
    assert parse_millones_to_clp(raw) == expected


def test_to_number_variants() -> None:
    assert to_number("1 en 3.000.000") == 3000000.0
    assert to_number("12,5%") == 12.5
    assert to_number("N/A") is None
    assert to_number("-") is None
    assert to_number("1.234,56") == 1234.56


def test_clean_clp() -> None:
    assert clean_clp("$1.000") == 1000
    assert clean_clp("1 000") == 1000


def test_format_millones() -> None:
    assert format_millones(1_234_560_000) == "1.235"


def test_mixed_separator_cross_check() -> None:
    assert parse_millones_to_clp("1.234,56") == 1_234_560_000
    assert to_number("1.234,56") == 1234.56
