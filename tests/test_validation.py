"""Tests for the game-aware validation module."""

from __future__ import annotations

from polla_app.validation import (
    validate_amounts,
    validate_kino_numbers,
    validate_pozo_payload,
)


def test_validate_amounts_ok() -> None:
    assert validate_amounts({"Loto": 1_000_000_000, "Kino": 8_370_000_000}) == []


def test_validate_amounts_rejects_zero_and_negative() -> None:
    issues = validate_amounts({"Loto": 0, "Revancha": -5})
    assert any(i.startswith("amount_too_small") for i in issues)


def test_validate_amounts_rejects_absurd_values() -> None:
    issues = validate_amounts({"Loto": 120_000_000_000})
    assert any(i.startswith("amount_too_large") for i in issues)


def test_validate_amounts_rejects_non_numeric() -> None:
    issues = validate_amounts({"Loto": "cuarenta"})
    assert any(i.startswith("amount_not_int") for i in issues)


def test_validate_amounts_empty() -> None:
    assert "no_amounts" in validate_amounts({})


def test_validate_kino_numbers_ok() -> None:
    numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    assert validate_kino_numbers(numbers) == []


def test_validate_kino_numbers_wrong_count() -> None:
    issues = validate_kino_numbers([1, 2, 3])
    assert any(i.startswith("kino_wrong_number_count") for i in issues)


def test_validate_kino_numbers_out_of_range() -> None:
    issues = validate_kino_numbers(list(range(1, 14)) + [26])
    assert any(i.startswith("kino_out_of_range") for i in issues)


def test_validate_kino_numbers_duplicates() -> None:
    issues = validate_kino_numbers([1] * 14)
    assert any(i.startswith("kino_duplicate") for i in issues)


def test_validate_kino_numbers_non_numeric() -> None:
    issues = validate_kino_numbers(list(range(1, 13)) + ["x", 14])
    assert any(i.startswith("kino_non_numeric") for i in issues)


def test_validate_pozo_payload_integrates_checks() -> None:
    payload = {
        "montos": {"Loto": 1_000_000_000},
        "sorteo": 5464,
        "fecha": "2026-08-13",
    }
    assert validate_pozo_payload(payload) == []

    payload["sorteo"] = -1
    payload["fecha"] = "not-a-date"
    issues = validate_pozo_payload(payload)
    assert any(i.startswith("invalid_sorteo") for i in issues)
    assert any(i.startswith("invalid_fecha") for i in issues)


def test_validate_pozo_payload_accepts_missing_optional_fields() -> None:
    # sorteo/fecha may be legitimately absent on some sources
    payload = {"montos": {"Loto": 1_000_000_000}}
    assert validate_pozo_payload(payload) == []
