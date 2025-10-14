# Polla App — Reliable jackpot ingestion for Chilean Loto ops

Aggregate próximo pozo estimates from vetted community mirrors, enforce provenance, and publish Google Sheets updates without touching `polla.cl`.

[![Tests](https://github.com/cortega26/polla/actions/workflows/tests.yml/badge.svg)](https://github.com/cortega26/polla/actions/workflows/tests.yml) [![Docs](https://github.com/cortega26/polla/actions/workflows/docs.yml/badge.svg)](https://github.com/cortega26/polla/actions/workflows/docs.yml) [![Health](https://github.com/cortega26/polla/actions/workflows/health.yml/badge.svg)](https://github.com/cortega26/polla/actions/workflows/health.yml) [![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3100/) [![License](https://img.shields.io/github/license/cortega26/polla)](license.md) [![Last commit](https://img.shields.io/github/last-commit/cortega26/polla)](https://github.com/cortega26/polla/commits/main)

## Features
- Orchestrates multi-source ingestion with deterministic fallbacks (`resultadoslotochile.com` primary, OpenLoto backup) and provenance baked into every artifact.
- Publishes structured JSONL outputs, comparison reports, and summaries ready for downstream dashboards.
- Ships a Click-based CLI (`run`, `publish`, `pozos`, `health`) with guardrails for dry-runs and quarantine handling.
- Observes every run with correlation IDs, spans, and metrics so on-call engineers get actionable logs.
- Keeps scraping polite via robots.txt enforcement, customisable user agents, and optional rate limiting.
- Locks behaviour with fixture-driven pytest suites and doctests executed in CI for documentation drift.
- Simplifies day-to-day DX with Make targets, Black/Ruff/Mypy automation, and GitHub Actions parity.

> ```python
> # Keeps pozos-only mode backward compatible while sunsetting legacy flags.
> _normalise_sources = _normalize_sources
> ```

## Tech Stack
- Python 3.10+, Click CLI, Requests + BeautifulSoup parsers
- Google Sheets integration via `gspread` + `google-auth`
- Testing: Pytest (+ doctests), Faker fixtures
- Tooling: Ruff, Black, Mypy, GitHub Actions (tests, docs, health)

## Architecture at a Glance
```mermaid
flowchart LR
  A[CLI command] --> B[Pipeline Orchestrator]
  B --> C{Source loader}
  C -->|ResultadosLotoChile| D[Primary scrape]
  C -->|OpenLoto fallback| E[Fallback scrape]
  D --> F[Normalizer]
  E --> F[Normalizer]
  F --> G[Artifacts\\n\\(JSONL, reports, state\\)]
  G --> H{Publish?}
  H -->|Yes| I[Google Sheets via gspread]
  H -->|No| J[Quarantine + logs]
  B --> K[Structured logging\\n\\(spans + metrics\\)]
```

## Quick Start
1. Ensure Python 3.10+ is available (use `pyenv local 3.10.13` or your preferred manager).
2. Create an isolated environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
3. Run the pozos pipeline locally:
   ```bash
   python -m polla_app run \
     --sources pozos \
     --normalized artifacts/normalized.jsonl \
     --comparison-report artifacts/comparison_report.json \
     --summary artifacts/run_summary.json
   ```
4. Optional: dry-run publishing to Google Sheets once credentials are configured:
   ```bash
   python -m polla_app publish \
     --normalized artifacts/normalized.jsonl \
     --comparison-report artifacts/comparison_report.json \
     --summary artifacts/run_summary.json \
     --worksheet "Normalized" \
     --discrepancy-tab "Discrepancies" \
     --dry-run
   ```

### Configuration
| Name | Type | Default | Required | Description |
| --- | --- | --- | --- | --- |
| `GOOGLE_SPREADSHEET_ID` | string | — | For `publish` | Target worksheet key for Google Sheets publishing. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON string | — | Conditional | Inline service account credentials (alternative to file). |
| `GOOGLE_CREDENTIALS` / `CREDENTIALS` | JSON string | — | Conditional | Legacy env vars recognised for service account auth. |
| `service_account.json` | file | — | Conditional | Disk-based credentials if env vars are not supplied. |
| `ALT_SOURCE_URLS` | JSON string | `{}` | No | Override source URLs for mirrors or testing. |
| `POLLA_USER_AGENT` | string | Library default | No | Custom HTTP user agent for polite scraping. |
| `POLLA_RATE_LIMIT_RPS` | float | unset | No | Per-host requests-per-second throttle. |

## Quality & Tests
- `pytest -q` – executes unit/integration suites with offline fixtures; expect `N passed` in <10s.
- `ruff check polla_app tests` – enforces linting, naming, and import hygiene.
- `mypy polla_app` – verifies strict typing (3rd-party stubs ignored where unavailable).
- `black --check polla_app tests` – maintains consistent formatting.
- `pytest --doctest-glob='*.md' README.md docs -q` – ensures documentation examples stay executable.

CI mirrors these commands through `.github/workflows/tests.yml` and `.github/workflows/docs.yml` so local runs match automation. Add `pytest --cov=polla_app` when you need a coverage report.[^coverage]

## Performance & Reliability
- Scheduled `health.yml` workflow exercises offline health checks daily to catch data source drift before operators do.
- `scripts/benchmark_pozos_parsing.py` offers a quick regression guard for parsing speed—keep median scrape under 150ms on commodity hardware.
- Structured metrics emitted via `polla_app.obs.metric` simplify alerting and feed SLO reviews (`docs/SLOs.md`).

## Roadmap
- Wire Codecov and fail PRs below agreed coverage thresholds.[^coverage]
- Expand publish command to surface mismatch deltas via Slack/webhooks for quicker operator response.
- Harden retry strategy with exponential backoff and jitter shared across sources.
- Add smoke-test fixtures for newly emerging aggregator mirrors.

## Why It Matters
- Demonstrates operational empathy: dry-run defaults, quarantine support, and explicit provenance reduce on-call stress.
- Highlights disciplined scraping practices respectful of third-party infrastructure and legal boundaries.
- Shows ability to automate reliability checks end-to-end (health workflow, observability hooks, structured metrics).
- Illustrates developer-experience focus through reproducible CLI, Make targets, and strict typing/linting gates.
- Proves comfort with secure credential handling when integrating with Google Workspace APIs.

## Contributing & License
Contributions are welcome—see [CONTRIBUTING.md](CONTRIBUTING.md) for style, testing, and review expectations.

This project is distributed under the [MIT License](license.md).

[^coverage]: TODO: Enable Codecov (or GitHub Actions coverage summary) to visualise and gate coverage in CI.
