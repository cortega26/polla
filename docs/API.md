# Python API

Programmatic entry points for integrating the pipeline into other tooling.

Sanity check doctest:

> > > from polla_app.sources import pozos
> > > isinstance(pozos.OPENLOTO_URL, str)
> > > True

## Pipeline

`polla_app.pipeline.run_pipeline(...)`

| Parameter                | Type                | Description                                                       |
| ------------------------ | ------------------- | ----------------------------------------------------------------- |
| `sources`                | `Sequence[str]`     | List of sources to ingest: `"pozos"`, `"polla"`, or `"openloto"`. |
| `source_overrides`       | `Mapping[str, str]` | Case-insensitive mapping of `{ "openloto": url, "polla": url }`.  |
| `raw_dir`                | `Path`              | Directory where per-source raw outputs will be written.           |
| `normalized_path`        | `Path`              | Path to the normalized NDJSON output file.                        |
| `comparison_report_path` | `Path`              | Path to the comparison report JSON file.                          |
| `summary_path`           | `Path`              | Path to the machine-readable run summary.                         |
| `state_path`             | `Path`              | File used to persist the last successful normalized record.       |
| `log_path`               | `Path`              | Structured log file emitted by the pipeline.                      |
| `retries`                | `int`               | Number of retries per source (default 3).                         |
| `timeout`                | `int`               | HTTP timeout in seconds (default 30).                             |
| `fail_fast`              | `bool`              | Abort on the first source failure.                                |
| `mismatch_threshold`     | `float`             | Max ratio of category mismatches tolerated before quarantine.     |
| `include_pozos`          | `bool`              | Include próximo pozo enrichment (deprecated, always True).        |
| `force_publish`          | `bool`              | Force ingestion and state update even if data is unchanged.       |

**Returns**: A dictionary containing `status` (publish/skip/quarantine), `publish_reason`, and `max_deviation`.

### Example

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

---

## Publishing

`polla_app.publish.publish_to_google_sheets(...)`

| Parameter                | Type   | Description                                                          |
| ------------------------ | ------ | -------------------------------------------------------------------- |
| `normalized_path`        | `Path` | Path to the normalized NDJSON file produced by the pipeline.         |
| `comparison_report_path` | `Path` | Path to the comparison report JSON file.                             |
| `summary`                | `dict` | Optional run summary JSON to honour publish/quarantine decisions.    |
| `worksheet_name`         | `str`  | Worksheet name to update with canonical data (default "Normalized"). |
| `discrepancy_tab`        | `str`  | Worksheet name used to store comparison mismatches.                  |
| `dry_run`                | `bool` | Skip calls to the Google Sheets API and only print actions.          |
| `force_publish`          | `bool` | Override quarantine and publish regardless of discrepancies.         |
| `allow_quarantine`       | `bool` | Write discrepancies even if the canonical update is skipped.         |

---

## Sources

| Function                           | Description                                                                                        |
| ---------------------------------- | -------------------------------------------------------------------------------------------------- |
| `get_pozo_openloto(url, **kwargs)` | Returns a dict with `montos`, `fuente`, `fetched_at`, `sorteo`, `fecha` from OpenLoto.             |
| `get_pozo_polla(url, **kwargs)`    | Returns a dict with `montos`, `fuente`, `fetched_at`, `sorteo`, `fecha` from Polla/ResultadosLoto. |

---

## HTTP Helpers

`polla_app.net.fetch_html(url: str, ua: str, timeout: int = 20) -> FetchMetadata`

- Politely fetches HTML with robots.txt checks and jittered exponential backoff on 429.
- Backoff is configurable via `POLLA_MAX_RETRIES` and `POLLA_BACKOFF_FACTOR`.
- Returns `FetchMetadata(url, user_agent, fetched_at, html)`; `sha256` property provides body hash for bit-perfect deduplication.

---

## Exceptions

| Class                   | Description                                                           |
| ----------------------- | --------------------------------------------------------------------- |
| `ScriptError`           | Base class with `error_code`, `context` and structured `log_error()`. |
| `ConfigError`           | Raised for missing Google credentials or spreadsheet ID.              |
| `RobotsDisallowedError` | Raised when robots policy forbids a fetch.                            |
