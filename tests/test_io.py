import json
from pathlib import Path
from typing import Any

import pytest

from polla_app.io import read_jsonl, write_jsonl


def _dedup_key(record: dict[str, Any]) -> tuple[Any, Any]:
    return (record.get("sorteo"), record.get("fecha"))


def test_read_jsonl_missing_file(tmp_path: Path) -> None:
    assert read_jsonl(tmp_path / "missing.jsonl") == []


def test_read_jsonl_dedup_by_key(tmp_path: Path) -> None:
    path = tmp_path / "state.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"sorteo": 1, "fecha": "2025-01-01", "pozos": 100}),
                json.dumps({"sorteo": 2, "fecha": "2025-01-02", "pozos": 200}),
                json.dumps({"sorteo": 1, "fecha": "2025-01-01", "pozos": 300}),
            ]
        ),
        encoding="utf-8",
    )
    records = read_jsonl(path, dedup_key=_dedup_key)
    assert len(records) == 2
    by_key = {_dedup_key(r): r for r in records}
    assert by_key[(1, "2025-01-01")]["pozos"] == 300
    assert by_key[(2, "2025-01-02")]["pozos"] == 200


def test_read_jsonl_tolerant_skips_bad_lines(tmp_path: Path) -> None:
    path = tmp_path / "state.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"sorteo": 1, "fecha": "2025-01-01"}),
                "not-json",
                json.dumps({"sorteo": 2, "fecha": "2025-01-02"}),
            ]
        ),
        encoding="utf-8",
    )
    records = read_jsonl(path, tolerant=True)
    assert len(records) == 2


def test_read_jsonl_strict_raises_on_bad_line(tmp_path: Path) -> None:
    path = tmp_path / "state.jsonl"
    path.write_text(
        "\n".join([json.dumps({"sorteo": 1, "fecha": "2025-01-01"}), "not-json"]),
        encoding="utf-8",
    )
    with pytest.raises(json.JSONDecodeError):
        read_jsonl(path)


def test_write_jsonl_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    rows = [{"sorteo": 1, "fecha": "2025-01-01"}, {"sorteo": 2, "fecha": "2025-01-02"}]
    write_jsonl(path, rows)
    assert read_jsonl(path) == rows


def test_write_jsonl_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deep" / "out.jsonl"
    write_jsonl(path, [{"sorteo": 1, "fecha": "2025-01-01"}])
    assert path.exists()
    assert read_jsonl(path) == [{"sorteo": 1, "fecha": "2025-01-01"}]
