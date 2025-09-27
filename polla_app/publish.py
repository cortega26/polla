"""Utilities to publish validated data to Google Sheets."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import gspread

LOGGER = logging.getLogger(__name__)


def _load_credentials() -> gspread.Client:
    raw = Path.cwd() / "service_account.json"
    credentials_env = None
    if raw.exists():  # pragma: no cover - developer override
        credentials_env = raw.read_text(encoding="utf-8")
    if credentials_env is None:
        credentials_env = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not credentials_env:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable is required")
    try:
        payload = json.loads(credentials_env)
    except json.JSONDecodeError as exc:  # pragma: no cover - misconfiguration guard
        raise RuntimeError("Invalid GOOGLE_SERVICE_ACCOUNT_JSON payload") from exc
    return gspread.service_account_from_dict(payload)


def _normalise_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    return summary or {}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _record_to_rows(record: dict[str, Any]) -> list[list[Any]]:
    pozos = json.dumps(record.get("pozos_proximo", {}), ensure_ascii=False)
    provenance = json.dumps(record.get("provenance", {}), ensure_ascii=False)
    rows: list[list[Any]] = []
    for premio in record.get("premios", []):
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


def _mismatch_rows(report: dict[str, Any]) -> list[list[Any]]:
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

    normalized = [
        json.loads(line)
        for line in normalized_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if not normalized:
        raise RuntimeError("Normalized dataset is empty; nothing to publish")

    report = _load_json(comparison_report_path)
    summary_payload = _normalise_summary(summary)

    decision = report.get("decision", {})
    status = str(decision.get("status", "")).lower()
    publish_allowed = status.startswith("publish")

    if summary_payload:
        publish_allowed = bool(summary_payload.get("publish", publish_allowed))
        status = str(summary_payload.get("decision", {}).get("status", status)).lower()

    if not publish_allowed and not force_publish:
        LOGGER.info("Run is quarantined; canonical worksheet will not be updated")
    rows = _record_to_rows(normalized[0])
    mismatch_rows = _mismatch_rows(report)

    result = {
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
        raise RuntimeError("GOOGLE_SPREADSHEET_ID environment variable is required")

    client = _load_credentials()
    spreadsheet = client.open_by_key(spreadsheet_id)

    if publish_allowed or force_publish:
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows="200", cols="10")
        worksheet.clear()
        worksheet.update(
            [
                [
                    "sorteo",
                    "fecha",
                    "fuente",
                    "categoria",
                    "premio_clp",
                    "ganadores",
                    "pozos_proximo",
                    "provenance",
                ]
            ]
            + rows
        )
        result["updated_rows"] = len(rows)

    if mismatch_rows or allow_quarantine:
        try:
            discrepancy_ws = spreadsheet.worksheet(discrepancy_tab)
        except gspread.WorksheetNotFound:
            discrepancy_ws = spreadsheet.add_worksheet(title=discrepancy_tab, rows="200", cols="10")
        headers = ["sorteo", "categoria", "consensus", "disagreeing", "missing_sources"]
        payload = [headers]
        if mismatch_rows:
            payload.extend(mismatch_rows)
        else:
            payload.append([report.get("last_draw", {}).get("sorteo"), "", "", "", ""])
        discrepancy_ws.clear()
        discrepancy_ws.update(payload)

    return result


__all__ = ["publish_to_google_sheets"]
