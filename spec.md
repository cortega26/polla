# Specification — Polla Scraper Wave 2 Hardening

## Goals

The objective of this phase is to transition the `polla` scraper from a functional prototype to a robust, observable, and maintainable production pipeline. Key focus areas are source isolation, failure resilience, and enhanced data integrity verification.

### 1. Robust Source Orchestration

- **Source Isolation**: Ensure that requesting a specific source (e.g., `--sources polla`) only triggers that source, preventing redundant network calls.
- **Full Parameter Propagation**: Connect `timeout` and `retries` CLI parameters to all fetchers, including the Playwright-based `polla` native scraper.
- **Resilience**: Implement "Degraded Mode" where the pipeline survives single-source failures if others succeed, and provides clear, actionable errors when all fail.

### 2. Enhanced Observability & Integrity

- **Confidence Scoring**: Add a `confidence` field to normalized records (`full`, `degraded`, or `single_source`) to communicate data reliability to downstream consumers.
- **Strict Redaction**: Fix over-eager redaction that masks non-sensitive fields containing the substring "key".
- **Mismatch Diagnostics**: Populate `missing_sources` in discrepancy reports and refactor report generation to be more cohesive and typed.

### 3. Operational Excellence

- **Slack Notifications**: Integrate detailed Slack alerts for "Quarantine" events, including specific mismatched categories and values.
- **CLI UX**: Update help strings for clarity on `force-publish` and formally deprecate non-functional flags like `--no-include-pozos`.

---

## Implementation Details

### Component: `polla_app/sources/pozos.py`

- **`get_pozo_polla`**:
  - Accept `timeout` and `retries`.
  - Pass `timeout` to `page.wait_for_selector` and `page.locator().click()`.
  - Pass `retries` (if applicable) or handle retry logic within the Scrapling context.

### Component: `polla_app/pipeline.py`

- **`_collect_pozos`**:
  - Update signature to accept a specific `name` to collect, or filter internal `POZO_SOURCES` based on a provided filter list.
- **`_run_ingestion_for_sources`**:
  - Calculate `confidence` based on the ratio of successful vs. requested sources.
  - Call `notifiers.notify_slack` (or a specialized `notify_quarantine`) when `decision_status == "quarantine"`.
- **`_merge_pozos`**:
  - Logic to identify which sources are missing data for a category that exists in others, populating `missing_sources`.

### Component: `polla_app/obs.py`

- **`_should_redact_key`**:- Change substring match for `"key"` to a word-boundary or exact match check (e.g., `key_l == "key"` or `key_l.endswith("_key")`).

### Component: `polla_app/notifiers.py`

- Implement `notify_quarantine(summary, mismatches)` with a rich Slack block layout.

---

## Verification Plan

### 1. Source Isolation & Parameters

- **Test**: Run `polla run --sources openloto` and verify (via mock) that `get_pozo_polla` is never called.
- **Test**: Run `polla run --timeout 12` and verify that the `polla` scraper uses `12s` for its internal waits.

### 2. Failure Resilience (Degraded Mode)

- **Test**: Mock `openloto` to fail and `polla` to succeed. Verify:
  - Pipeline exit code is 0.
  - `confidence` in output is `"degraded"`.
  - Artifacts are generated.

- **Test**: Mock all sources to fail. Verify:
  - Pipeline raises `RuntimeError` with a descriptive message.
  - No partial artifacts are left in a broken state.

### 3. Data Integrity & Redaction

- **Test**: Inject a field named `"monkey"` into a log payload. Verify it is NOT redacted.
- **Test**: Inject a category mismatch between sources. Verify `comparison_report.json` contains the list of `missing_sources` for that category.

### 4. CLI & UX

- **Test**: Run `polla run --no-include-pozos`. Verify a `DeprecationWarning` is printed to `stderr`.
- **Test**: Verify `--help` output for `run` and `publish` commands accurately describes `force-publish` behavior.

### 5. E2E Pipeline

- **Test**: Full run with mocked HTML fixtures for all sources. Verify `normalized.jsonl` has the correct `API_VERSION` (v1.2) and all expected fields.
