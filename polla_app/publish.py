"""Utilities to publish validated data to Google Sheets."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .exceptions import ConfigError

# Optional at import time to allow dry-run in tests without gspread installed
gspread: Any
try:
    import gspread
except Exception:  # pragma: no cover - import guard for environments without gspread
    gspread = None

LOGGER = logging.getLogger(__name__)


def _load_credentials() -> Any:
    if gspread is None:
        raise RuntimeError(
            "gspread is not installed; install requirements (pip install -r requirements.txt) "
            "or run publish in --dry-run mode"
        )
    raw = Path.cwd() / "service_account.json"
    credentials_env = None
    if raw.exists():  # pragma: no cover - developer override
        credentials_env = raw.read_text(encoding="utf-8")
    if credentials_env is None:
        credentials_env = (
            os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
            or os.getenv("GOOGLE_CREDENTIALS")
            or os.getenv("CREDENTIALS")
        )
    if not credentials_env:
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is required")
    try:
        payload = json.loads(credentials_env)
    except json.JSONDecodeError as exc:  # pragma: no cover - misconfiguration guard
        raise ConfigError("Invalid GOOGLE_SERVICE_ACCOUNT_JSON payload") from exc
    return gspread.service_account_from_dict(payload)


def _normalise_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    return summary or {}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_normalized_ndjson(path: Path) -> list[dict[str, Any]]:
    """Load NDJSON file into a list of dicts.

    Each line must be a valid JSON object.
    """
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _record_to_rows(record: Mapping[str, Any]) -> list[list[Any]]:
    """Convert a normalized record into tabular rows for Sheets.

    - If `premios` is present, emit the canonical 8‑column row format.
    - Otherwise (pozos‑only), emit two‑column rows of category and amount.
    """
    pozos = json.dumps(record.get("pozos_proximo", {}), ensure_ascii=False)
    provenance = json.dumps(record.get("provenance", {}), ensure_ascii=False)
    rows: list[list[Any]] = []
    premios = record.get("premios", []) or []
    if premios:
        for premio in premios:
            rows.append(
                [
                    record.get("sorteo"),
                    record.get("fecha"),
                    record.get("fuente"),
                    premio.get("categoria"),
                    premio.get("premio_clp"),
                    premio.get("ganadores"),
                    pozos,
                    provenance,
                ]
            )
        return rows

    # Pozos-only mode: emit one row per category with jackpot amount
    for categoria, monto in (record.get("pozos_proximo", {}) or {}).items():
        rows.append([categoria, int(monto)])
    return rows


def _mismatch_rows(report: Mapping[str, Any]) -> list[list[Any]]:
    """Convert mismatch entries into a tabular form for the discrepancy tab."""
    rows: list[list[Any]] = []
    for mismatch in report.get("mismatches", []):
        rows.append(
            [
                report.get("last_draw", {}).get("sorteo"),
                mismatch.get("categoria"),
                json.dumps(mismatch.get("consensus", {}), ensure_ascii=False),
                json.dumps(mismatch.get("disagreeing", {}), ensure_ascii=False),
                ", ".join(mismatch.get("missing_sources", [])),
            ]
        )
    return rows


def _parse_publish_decision(
    *, report: Mapping[str, Any], summary_payload: Mapping[str, Any], force_publish: bool
) -> tuple[bool, str]:
    """Resolve whether canonical update is allowed and the effective status."""
    decision = report.get("decision", {})
    status = str(decision.get("status", "")).lower()
    publish_allowed = status.startswith("publish")

    if summary_payload:
        publish_allowed = bool(summary_payload.get("publish", publish_allowed))
        status = str(summary_payload.get("decision", {}).get("status", status)).lower()

    if not publish_allowed and not force_publish:
        LOGGER.info("Run is quarantined; canonical worksheet will not be updated")
    return publish_allowed, status


def _canonical_rows_header(rows: Iterable[Iterable[Any]]) -> list[str]:
    """Return the header row matching the row width of `rows`."""
    row_width = len(next(iter(rows), []))  # type: ignore[arg-type]
    if row_width == 2:
        return ["categoria", "pozo_clp"]
    return [
        "sorteo",
        "fecha",
        "fuente",
        "categoria",
        "premio_clp",
        "ganadores",
        "pozos_proximo",
        "provenance",
    ]


def _get_or_create_worksheet(spreadsheet: Any, name: str) -> Any:
    """Return existing worksheet by name or create it if missing."""
    try:
        return spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=name, rows="200", cols="10")


def _update_canonical_worksheet(spreadsheet: Any, worksheet_name: str, rows: list[list[Any]]) -> int:
    """Write canonical rows and return the number of updated rows."""
    if not rows:
        return 0
    header = _canonical_rows_header(rows)
    ws = _get_or_create_worksheet(spreadsheet, worksheet_name)
    ws.clear()
    ws.update([header] + rows)
    return len(rows)


def _update_discrepancy_sheet(
    spreadsheet: Any, discrepancy_tab: str, report: Mapping[str, Any], mismatch_rows: list[list[Any]], *, allow_quarantine: bool
) -> None:
    """Write mismatch rows or a placeholder if `allow_quarantine` is set."""
    if not mismatch_rows and not allow_quarantine:
        return
    ws = _get_or_create_worksheet(spreadsheet, discrepancy_tab)
    headers = ["sorteo", "categoria", "consensus", "disagreeing", "missing_sources"]
    payload: list[list[Any]] = [headers]
    if mismatch_rows:
        payload.extend(mismatch_rows)
    else:
        payload.append([report.get("last_draw", {}).get("sorteo"), "", "", "", ""])
    ws.clear()
    ws.update(payload)


def publish_to_google_sheets(
    *,
    normalized_path: Path,
    comparison_report_path: Path,
    summary: dict[str, Any] | None,
    worksheet_name: str,
    discrepancy_tab: str,
    dry_run: bool,
    force_publish: bool,
    allow_quarantine: bool,
) -> dict[str, Any]:
    """Publish normalized data to Google Sheets."""

    normalized = _load_normalized_ndjson(normalized_path)
    if not normalized:
        raise RuntimeError("Normalized dataset is empty; nothing to publish")

    report = _load_json(comparison_report_path)
    summary_payload = _normalise_summary(summary)
    rows = _record_to_rows(normalized[0])
    mismatch_rows = _mismatch_rows(report)

    publish_allowed, status = _parse_publish_decision(
        report=report, summary_payload=summary_payload, force_publish=force_publish
    )

    result: dict[str, Any] = {
        "updated_rows": 0,
        "discrepancy_rows": len(mismatch_rows),
        "status": status,
        "publish_allowed": publish_allowed or force_publish,
    }

    if dry_run:
        LOGGER.info("Dry-run enabled; skipping Google Sheets API calls")
        spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID") or os.getenv(
            "GOOGLE_SHEETS_SPREADSHEET_ID"
        )
        if spreadsheet_id:
            result["spreadsheet_id"] = spreadsheet_id
        result.update({"worksheet": worksheet_name, "discrepancy_tab": discrepancy_tab})
        return result

    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise ConfigError("GOOGLE_SPREADSHEET_ID environment variable is required")

    client = _load_credentials()
    spreadsheet = client.open_by_key(spreadsheet_id)

    if publish_allowed or force_publish:
        result["updated_rows"] = _update_canonical_worksheet(spreadsheet, worksheet_name, rows)

    _update_discrepancy_sheet(
        spreadsheet, discrepancy_tab, report, mismatch_rows, allow_quarantine=allow_quarantine
    )

    return result


__all__ = ["publish_to_google_sheets"]
