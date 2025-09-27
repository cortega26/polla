from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

from google.oauth2 import service_account
from googleapiclient.discovery import build


def load_service(creds_json: str):
    info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build("sheets", "v4", credentials=creds)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def to_long_rows(record: dict[str, Any]) -> Iterable[list[Any]]:
    sorteo = record.get("sorteo")
    fecha = record.get("fecha")
    fuente = record.get("fuente")
    for p in record.get("premios", []) or []:
        yield [sorteo, fecha, fuente, p.get("categoria"), p.get("premio_clp"), p.get("ganadores")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="artifacts/normalized.jsonl")
    ap.add_argument("--comparison", default="artifacts/comparison_report.json")
    ap.add_argument("--spreadsheet-id")
    ap.add_argument("--sheet-name", default="AltData")
    ap.add_argument("--discrepancy-tab", default="Discrepancies")
    args = ap.parse_args()

    creds_env = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("CREDENTIALS")
    if not creds_env:
        raise SystemExit("Missing GOOGLE_SERVICE_ACCOUNT_JSON or CREDENTIALS env var")

    spreadsheet_id = args.spreadsheet_id or os.getenv("GOOGLE_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise SystemExit("Missing --spreadsheet-id or GOOGLE_SPREADSHEET_ID env var")

    service = load_service(creds_env)

    # Load comparison report if present
    mismatch = False
    comp_path = Path(args.comparison)
    if comp_path.exists():
        try:
            report = json.loads(comp_path.read_text(encoding="utf-8"))
            mismatch = bool(report.get("mismatch"))
        except Exception:
            mismatch = False

    data_path = Path(args.data)
    records = read_jsonl(data_path)
    if not records:
        raise SystemExit("No records in normalized.jsonl; nothing to publish")

    if mismatch:
        # Append raw JSON for audit into discrepancy tab
        payload = [[json.dumps(r, ensure_ascii=False)] for r in records]
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{args.discrepancy_tab}!A:A",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": payload},
        ).execute()
        return

    # Publish canonical rows (long format)
    header = [["sorteo", "fecha", "fuente", "categoria", "premio_clp", "ganadores"]]
    rows = list(to_long_rows(records[0]))
    if not rows:
        raise SystemExit("Record has no premios; nothing to publish")

    # Write header (best-effort) followed by append rows
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{args.sheet_name}!A1:F1",
        valueInputOption="RAW",
        body={"values": header},
    ).execute()

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{args.sheet_name}!A:F",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


if __name__ == "__main__":
    main()
