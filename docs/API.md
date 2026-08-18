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
| `sources`                | `Sequence[str]`     | List of sources to ingest: `"pozos"`, `"polla"`, `"openloto"`, `"kino"` — use one game per invocation. |
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
| `include_prices`         | `bool`              | Fetch live prices for the game and attach them to the normalized record (default False). Cuando `include_prices=True`, se obtienen los precios vivos del juego y se adjuntan al registro normalizado. |

**Returns**: A dictionary (the run summary, also written to `summary_path`) with:
`run_id`, `generated_at`, `decision` (with `status` ∈ publish/publish_forced/skip/quarantine,
`confidence`, `total_categories`, `mismatched_categories`, `reason`), `prizes_changed`,
`normalized_path`, `comparison_report`, `raw_dir`, `state_path`, `publish` (bool),
`publish_reason`, and `api_version`. `max_deviation` no es un key del resumen: vive
dentro de cada `mismatch` del comparison report.

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

---

## Kino (Lotería de Concepción)

`polla_app.sources.kino.get_pozo_kino(url=PENDON_URL, *, ua, timeout, retries)`

Fetches próximo pozo estimates from the official pendón (`pendon-kino.loteria.cl/pendonkino`).
Returns the same payload shape as the Loto fetchers (`fuente`, `fetched_at`, `sha256`,
`estimado`, `montos`, `sorteo`, `fecha`). Category labels are prefixed with `Kino `
so they never collide with Loto categories in the consensus engine.

## Dashboard data

`polla_app.site.write_site_data(loto_path, output, kino_path=None, summary_path=None, previous_payload=None)`

Aggregates the latest Loto/Kino records (deduplicated by `(sorteo, fecha)`) into the
static dashboard payload consumed by `site/index.html` (see `docs/DATA-STORE.md`).

## Validation

`polla_app.validation.validate_pozo_payload(payload)` returns a list of issue codes
(`amount_too_small`, `amount_too_large`, `invalid_sorteo`, `invalid_fecha`, ...).
`validate_kino_numbers(numbers)` checks 14 unique numbers in 1..25. Validation runs
inside the pipeline before a payload is accepted; invalid payloads are rejected
(quarantined / logged), never published silently.

---

## Esquemas de artefactos

Claves de nivel superior de cada artefacto emitido por `run_pipeline` (ver
`tests/test_contracts.py` para las claves asertadas).

### artifacts/normalized.jsonl

Una línea por juego (record normalizado; `game` distingue Loto de Kino, plan 030):

```
sorteo, fecha, game, fuente, confidence, premios, pozos_proximo, provenance,
precios (cuando include_prices=True)
```

### artifacts/comparison_report.json

```
run:        {id, generated_at, sources, timeout, retries, fail_fast}
last_draw:  {sorteo, fecha}
decision:   {status, confidence, total_categories, mismatched_categories, reason}
mismatches: [ ... ]   (cada mismatch incluye su propio max_deviation)
api_version
```

### artifacts/run_summary.json

```
run_id, generated_at, decision{...}, prizes_changed, publish (bool),
publish_reason, normalized_path, comparison_report, raw_dir, state_path,
api_version
```
