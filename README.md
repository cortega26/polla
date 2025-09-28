# Polla App — Próximo Pozo Aggregator

This project aggregates the **próximo pozo** for Loto Chile without touching
`polla.cl`. It reads community aggregator pages and emits a simple, consistent
JSON record with per‑categoría jackpot.

## Features

- **No WAF interaction** – HTTP requests are performed with `requests` and a
  descriptive User-Agent, honouring `robots.txt`.
- **Próximo pozo only** – Fetch jackpot estimates from
  ResultadosLotoChile (primary) and OpenLoto (fallback), keeping provenance.
- **Deterministic tests** – Parsers are covered with fixture-based unit tests.
- **CLI tooling** – Inspect draw URLs, list recent 24Horas posts, and fetch
  pozo estimates directly from the command line.

## Installation

```bash
pip install -r requirements.txt
```

For local development with formatting and linting tools:

```bash
pip install -r requirements-dev.txt
```

## Usage

### Run the pipeline

Run the multi-source pipeline, write artifacts, and compute a publish decision:

```bash
python -m polla_app run \
  --sources pozos \
  --retries 3 \
  --timeout 30 \
  --no-fail-fast \
  --raw-dir artifacts/raw \
  --normalized artifacts/normalized.jsonl \
  --comparison-report artifacts/comparison_report.json \
  --summary artifacts/run_summary.json \
  --state-file pipeline_state/last_run.jsonl \
  --log-file logs/run.jsonl \
  --mismatch-threshold 0.2 \
  --include-pozos
```

- Sources: use `pozos` (default) to fetch from ResultadosLotoChile + OpenLoto.
  `openloto` forces fallback‑only mode.

```bash
python -m polla_app run --sources pozos
```

- Artifacts written under `artifacts/` and decision emitted as `artifacts/comparison_report.json` and `artifacts/run_summary.json`.

### Publish to Google Sheets

```bash
python -m polla_app publish \
  --normalized artifacts/normalized.jsonl \
  --comparison-report artifacts/comparison_report.json \
  --summary artifacts/run_summary.json \
  --worksheet "Normalized" \
  --discrepancy-tab "Discrepancies" \
  --dry-run
```

Environment required:
- `GOOGLE_SHEETS_CREDENTIALS` (service account JSON)
- `GOOGLE_SPREADSHEET_ID` (spreadsheet key)

If the decision status is `quarantine`, the canonical worksheet is skipped and mismatches are written to the discrepancy tab.

### Inspect current estimates

```bash
python -m polla_app pozos
```

### Fetch próximo pozo estimates

```bash
python -m polla_app pozos
```

## Data Model

Each pipeline run writes a normalized record with this schema:

```json
{
  "sorteo": 5322,
  "fecha": "2025-09-16",
  "fuente": "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/",
  "premios": [],
  "pozos_proximo": {
    "Loto Clásico": 690000000,
    "Recargado": 180000000,
    "Jubilazo $500.000": 480000000
  },
  "provenance": {
    "pozos": {"primary": {"fuente": "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/"}}
  }
}
```

## Development

### Tests

```bash
pytest -q
```

### Formatting & Linting

```bash
black polla_app tests
ruff check polla_app tests

## CI

GitHub Actions workflows are provided:

- Ingest + compare + conditional publish: `.github/workflows/scrape.yml`
- Dry-run verification (no publish): `.github/workflows/update.yml`
- Secret checks: `.github/workflows/verify-secret.yml`

Set these in your repository settings:
- Secrets: `GOOGLE_SHEETS_CREDENTIALS`, `GOOGLE_SPREADSHEET_ID`
- Optional Vars: `ALT_SOURCE_URLS` (JSON mapping like `{ "24h": "https://…" }`)

## Migration

This release removes the Playwright-based scraper and switches to an alt-source
HTTP pipeline.

- Replace any `python -m polla_app scrape` calls with `python -m polla_app run`.
- Remove Playwright installation steps from CI (`playwright install`, `install-deps`).
- Ensure repo secrets are configured: `GOOGLE_SHEETS_CREDENTIALS` and `GOOGLE_SPREADSHEET_ID`.
- Optionally set `ALT_SOURCE_URLS` (JSON) to pin source URLs (e.g., a 24Horas article).
```

## License

MIT
