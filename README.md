# Polla App — Alternative Lottery Source Ingestor

This project normalises **Loto Chile** results without touching `polla.cl`. It
parses public news articles (24Horas) and community aggregators to produce
a consistent JSON structure containing per-categoría payouts and próximo pozo
estimates.

## Features

- ✅ **No WAF interaction** – HTTP requests are performed with `requests` and a
  descriptive User-Agent, honouring `robots.txt`.
- 📰 **Draw source** – Parse 24Horas result articles.
- 💰 **Próximo pozo enrichment** – Fetch jackpot estimates from OpenLoto and
  ResultadosLotoChile, keeping provenance metadata.
- 🧪 **Deterministic tests** – Parsers are covered with fixture-based unit tests.
- 🛠️ **CLI tooling** – Inspect draw URLs, list recent 24Horas posts, and fetch
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

### End-to-end pipeline (ingest + compare)

Run the multi-source pipeline, write artifacts, and compute a publish decision:

```bash
python -m polla_app run \
  --sources all \
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

- Sources: `all` includes `24h`. The `24h` URL is auto-discovered (latest).
- Override URLs via `--source-url` (repeatable) or `ALT_SOURCE_URLS` env var (JSON):

```bash
python -m polla_app run \
  --sources all \
  # Optionally pin a specific 24h URL (otherwise latest is auto-discovered)
  --source-url 24h=https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322

# Or with env var (JSON mapping)
export ALT_SOURCE_URLS='{"24h": "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322"}'
python -m polla_app run --sources all
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

### Parse a draw

```bash
python -m polla_app ingest --source 24h "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322"
```

- `--source` accepts `24h`.
- `--no-pozos` disables próximo pozo enrichment.
- `--compact` prints the record on a single JSON line.

### List recent 24Horas result posts

```bash
python -m polla_app list-24h --limit 5
```

### Fetch próximo pozo estimates

```bash
python -m polla_app pozos
```

## Data Model

Each draw record emitted by `ingest` follows this schema:

```json
{
  "sorteo": 5322,
  "fecha": "2025-09-16",
  "fuente": "https://www.24horas.cl/…",
  "premios": [
    {"categoria": "Loto 6 aciertos", "premio_clp": 0, "ganadores": 0},
    {"categoria": "Quina (5)", "premio_clp": 757970, "ganadores": 3}
  ],
  "pozos_proximo": {
    "Loto Clásico": 690000000,
    "Recargado": 180000000,
    "Total estimado": 4300000000
  },
  "provenance": {
    "source": "24h",
    "url": "https://www.24horas.cl/…",
    "ingested_at": "2025-09-17T02:15:00+00:00",
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
