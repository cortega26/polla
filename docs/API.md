# Python API

Programmatic entry points for integrating the pipeline into other tooling.

Sanity check doctest:

>>> from polla_app.sources import pozos
>>> isinstance(pozos.OPENLOTO_URL, str)
True

## Pipeline

`polla_app.pipeline.run_pipeline(*, sources, source_overrides, raw_dir, normalized_path, comparison_report_path, summary_path, state_path, log_path, retries, timeout, fail_fast, mismatch_threshold, include_pozos, force_publish=False) -> dict`

- Sources: `"pozos"`, `"resultadoslotochile"`, or `"openloto"`. Sources use a unified registry for consistent results.
- `source_overrides`: case‑insensitive mapping of `{ "openloto": url, "resultadoslotochile": url }`.
- Returns a result with `status` (publish/skip/quarantine), `publish_reason`, and `max_deviation`.

Example:

```python
from pathlib import Path
from polla_app.pipeline import run_pipeline

summary = run_pipeline(
    sources=["pozos"],
    source_overrides={},
    raw_dir=Path("artifacts/raw"),
    normalized_path=Path("artifacts/normalized.jsonl"),
    comparison_report_path=Path("artifacts/comparison_report.json"),
    summary_path=Path("artifacts/run_summary.json"),
    state_path=Path("pipeline_state/last_run.jsonl"),
    log_path=Path("logs/run.jsonl"),
    retries=2,
    timeout=20,
    fail_fast=True,
    mismatch_threshold=0.25,
    include_pozos=True,
)
print(summary["publish"])  # True/False
print(summary["publish_reason"])  # e.g. "updated_or_new_amounts"
```

## Publishing

`polla_app.publish.publish_to_google_sheets(*, normalized_path, comparison_report_path, summary, worksheet_name, discrepancy_tab, dry_run, force_publish, allow_quarantine) -> dict`

- Reads artifacts produced by the pipeline and updates Google Sheets.
- Credentials are loaded from `service_account.json` (cwd) or the `GOOGLE_SERVICE_ACCOUNT_JSON`/`GOOGLE_CREDENTIALS` envs.

Example (dry‑run):

```python
from pathlib import Path
from polla_app.publish import publish_to_google_sheets

result = publish_to_google_sheets(
    normalized_path=Path("artifacts/normalized.jsonl"),
    comparison_report_path=Path("artifacts/comparison_report.json"),
    summary=Path("artifacts/run_summary.json").read_text() and None,
    worksheet_name="Normalized",
    discrepancy_tab="Discrepancies",
    dry_run=True,
    force_publish=False,
    allow_quarantine=True,
)
print(result)
```

## Sources

`polla_app.sources.get_pozo_openloto(url: str = DEFAULT, *, ua: str = DEFAULT, timeout: int = 20) -> dict`

`polla_app.sources.get_pozo_resultadosloto(url: str = DEFAULT, *, ua: str = DEFAULT, timeout: int = 20) -> dict`

Return a dict with `montos` per category, `fuente`, `fetched_at`, and best‑effort `sorteo`/`fecha`.

## HTTP Helpers

`polla_app.net.fetch_html(url: str, ua: str, timeout: int = 20) -> FetchMetadata`

- Politely fetches HTML with robots.txt checks and jittered exponential backoff on 429.
- Backoff is configurable via `POLLA_MAX_RETRIES` and `POLLA_BACKOFF_FACTOR`.
- Returns `FetchMetadata(url, user_agent, fetched_at, html)`; `sha256` property provides body hash for bit-perfect deduplication.

## Exceptions

`polla_app.exceptions.ScriptError` — base class with `error_code`, `context` and structured `log_error()`.

`ConfigError` — configuration/env problems (e.g., missing Google credentials or spreadsheet ID).

`RobotsDisallowedError` — raised when robots policy forbids a fetch (subclasses `PermissionError`).
