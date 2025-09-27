# Changelog

All notable changes to this project are documented in this file.

## [3.0.0] - 2025-09-27

- Alt-source ingestion pipeline replaces browser-based scraper.
- New CLI entry points:
  - `python -m polla_app run` (ingest + compare + artifacts)
  - `python -m polla_app publish` (publish to Google Sheets)
- Parsers: T13, 24Horas, and próximo pozo (OpenLoto, ResultadosLotoChile).
- HTTP layer switched to `requests` with polite UA + robots.txt checks.
- Workflows updated to call new CLI and publish conditionally.
- Dependencies: `beautifulsoup4`, `requests`, `gspread`, `google-auth`.
- Removed legacy Playwright-based modules and standalone scripts.

### Migration notes

- Replace any `python -m polla_app scrape` usages with `python -m polla_app run`.
- Secrets required: `GOOGLE_SHEETS_CREDENTIALS` and `GOOGLE_SPREADSHEET_ID`.
- Optional var: `ALT_SOURCE_URLS` (JSON mapping for per-source URL overrides).
- Remove Playwright install steps from CI; they are no longer needed.
