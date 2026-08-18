# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [3.2.0] - 2026-08-14

### Added

- **Kino (Lotería de Concepción):** nuevo parser `sources/kino.py` sobre el pendón
  oficial (`pendon-kino.loteria.cl/pendonkino`, `__NEXT_DATA__`, sin navegador),
  con validación, dedupe e integración total en el pipeline (`--sources kino`,
  comando `kino`, health online, CI con hoja propia "Kino").
- **Dashboard público estático:** `site/` (HTML/CSS/JS sin dependencias) + comando
  `polla site` que genera `site/data.json`; deploy en GitHub Pages vía
  `.github/workflows/pages.yml`.
- **Estadísticas de juego en el dashboard:** `stats.py` sincroniza la hoja pública
  de referencia (CSV vía `gviz/tq`, respetando robots.txt) a `site/stats.json`:
  probabilidades, combinaciones, precios y retorno esperado por categoría,
  filtrables por juego (env `POLLA_STATS_URL`).
- **Validación por juego:** `validation.py` centraliza los chequeos de montos,
  sorteo y fecha (rango 1 MM–100.000 MM, fechas ISO); aplica en pipeline y health.
- **Retries reales:** `fetch_html` reintenta timeouts y errores de conexión (no
  solo HTTP 429), con backoff y jitter.
- **`fail_fast` funcional:** `--fail-fast` aborta ante la primera falla de fuente
  (antes era un parámetro muerto).
- **Lock anti-concurrencia:** `_PublishLock` (flock) evita publishes simultáneos;
  envs `POLLA_PUBLISH_LOCK_PATH` / `POLLA_PUBLISH_LOCK_TIMEOUT`.
- **Decisión de almacenamiento:** `docs/DATA-STORE.md` (Sheets + dashboard, sin migración).

### Changed

- **Consenso sin ceros fantasma:** categorías ausentes ya no votan `0` en el
  consenso (openloto/polla); `--sources all` rechazado: cada juego (Loto/Kino)
  se ingesta en una invocación separada.
- **Estado rotativo:** `pipeline_state/last_run.jsonl` se deduplica por
  `(sorteo, fecha)` y se acota a `MAX_STATE_RECORDS` (1000), frenando el
  crecimiento ilimitado.
- **Publish multi-record:** se publica el primer record de cada juego (deduplicado);
  las hojas `Proximo Pozo` y `Kino` no comparten categorías.
- **Makefile:** `make run` ejecuta el pipeline real (antes invocaba un comando eliminado);
  nuevo `make run-kino`.

### Fixed

- `_compute_unchanged`: un `break` prematuro impedía comparar records previos del
  mismo sorteo (ahora devuelve la decisión correcta).
- Health `--online`: validación centralizada y fuente Kino incluida.
- **Precios vivos por sorteo**: la tabla de estadísticas mostraba el precio de la
  hoja manual; ahora `sources/prices.py` scrapea la estructura oficial en cada
  corrida — Loto (polla.cl/es/view/juego/loto, server-rendered): Loto $1.000,
  Recargado +$500, Revancha +$300, Desquite +$200, Jubilazo +$500, Multiplicar
  +$500, Jubilazo 50 años +$500; y Kino (hub kino.loteria.cl, `__NEXT_DATA__` por
  sorteo): Kino $1.000, ReKino +$500, RequeteKino +$500, Chao Jefe $2M +$500,
  Chao Jefe $3M +$500, Súper Combo Marraqueta +$500 ($3.500 total) — con delta y
  acumulado por categoría, y retorno esperado recalculado con premio y precio
  reales. Sin mapeo o fuente no disponible → "—"/"(ref)".
- `fetch_html` acepta `extra_headers` (necesarios para el hub de Kino).

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
