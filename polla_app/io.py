"""Shared JSONL (NDJSON) read/write helpers."""

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


def read_jsonl(
    path: Path,
    *,
    dedup_key: Callable[[dict[str, Any]], Any] | None = None,
    tolerant: bool = False,
) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts.

    - ``dedup_key``: when given, later records with the same key replace
      earlier ones (e.g. lambda r: (r.get("sorteo"), r.get("fecha"))).
    - ``tolerant``: skip invalid lines with a warning instead of raising.
    Missing files return [].
    """
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                if not tolerant:
                    raise
                LOGGER.warning("Invalid JSON line in %s; ignoring", path)
    if dedup_key is None:
        return records
    keyed: dict[Any, dict[str, Any]] = {}
    for record in records:
        keyed[dedup_key(record)] = record
    return list(keyed.values())


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Write rows as JSONL (ensure_ascii=False), creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def read_json(path: Path) -> Any:
    """Read a JSON file (missing file -> raise FileNotFoundError as today)."""
    return json.loads(path.read_text(encoding="utf-8"))
