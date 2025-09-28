# Polla App — Próximo Pozo Aggregator

[![Docs](https://github.com/cortega26/polla/actions/workflows/docs.yml/badge.svg)](https://github.com/cortega26/polla/actions/workflows/docs.yml)

Aggregates the próximo pozo (jackpot estimates) for Loto Chile from community sources — without hitting `polla.cl`. It fetches and parses aggregator pages, merges categories, and outputs a consistent JSON record and a publish decision.

## Highlights

- No WAF interaction: polite `requests` client with descriptive UA and `robots.txt` checks.
- Pozos‑only: ResultadosLotoChile (primary) + OpenLoto (fallback) with provenance.
- Clean CLI: run pipeline, print estimates, or publish to Google Sheets.
- Deterministic tests: fixture‑based unit/integration tests.

## Install

```bash
pip install -r requirements.txt
# dev tools
pip install -r requirements-dev.txt
```

## Quickstart

- Run pozos pipeline and generate artifacts:

```bash
python -m polla_app run \
  --sources pozos \
  --normalized artifacts/normalized.jsonl \
  --comparison-report artifacts/comparison_report.json \
  --summary artifacts/run_summary.json
```

- Print current estimates (JSON):

```bash
python -m polla_app pozos
```

### Configuration

- `ALT_SOURCE_URLS` (optional): JSON mapping to override source URLs, e.g.

```bash
set ALT_SOURCE_URLS={"openloto":"https://mirror/openloto.html"}
```

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

Required environment:
- `GOOGLE_SPREADSHEET_ID` — spreadsheet key
- Credentials via one of:
  - `service_account.json` file in the working directory, or
  - `GOOGLE_SERVICE_ACCOUNT_JSON` (JSON string), or
  - `GOOGLE_CREDENTIALS` / `CREDENTIALS` (JSON string)

If the decision requests quarantine, the canonical worksheet is skipped; discrepancies are still written when `--allow-quarantine` is set.

## Data Model

Normalized record written by the pipeline:

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

## Python API

See `docs/API.md` for programmatic usage of `run_pipeline`, `publish_to_google_sheets`, and the source/HTTP helpers.

## Development

```bash
pytest -q            # run tests
ruff check .         # lint
black .              # format
python scripts/benchmark_pozos_parsing.py  # micro-benchmarks
```

## CI

Workflows:
- Ingest + compare + conditional publish: `.github/workflows/scrape.yml`
- Dry-run verification (no publish): `.github/workflows/update.yml`
- Secret checks: `.github/workflows/verify-secret.yml`

Repository secrets:
- `GOOGLE_SPREADSHEET_ID`
- Optionally: `GOOGLE_SERVICE_ACCOUNT_JSON` (if not using `service_account.json`)
- Optional: `ALT_SOURCE_URLS` (JSON mapping)

## Migration Notes

This branch is pozos‑only. Article scraping and Playwright have been removed.

- Replace `python -m polla_app scrape` with `python -m polla_app run`.
- Remove Playwright steps from CI.
- Provide Google secrets as above.

## License

MIT
