# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [3.1.0] - 2026-03-28

### Added

- **Consensus Engine:** Majority-vote logic for jackpots when scraping multiple sources.
- **Data Provenance:** SHA-256 content hashing for original HTML sources, stored in artifacts.
- **Slack Notifications:** Automated run summaries and discrepancy alerts via webhooks.
- **Enhanced Health Checks:** Range-based validation for monetary amounts in `health --online`.
- **Configurability:** Environment support for `POLLA_429_BACKOFF_SECONDS` and `SLACK_WEBHOOK_URL`.

### Changed

- **Unified Pipeline:** Refactored multiple ingestion handlers into a single, high-integrity orchestrator.
- **Redaction Logic:** Restricted masking to confirmed sensitive keys (preserving URLs in logs).
- **Dry-run Visibility:** `publish --dry-run` now reports the exact tabular payload for audit.

### Fixed

- **Monetary Parser:** Deterministic handling of Chilean decimal/thousand separators (dots vs commas).
- **Graceful Fail-fast:** Improved error taxonomy and controlled parsing failures.

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
