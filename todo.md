# Todo List — Polla Scraper Hardening

## Phase 1: Core Correctness & Isolation
- [x] **BUG-03: Implement Source Isolation**
    - [x] Update `_collect_pozos` in `pipeline.py` to filter by source name.
    - [x] Update `_run_ingestion_for_sources` to pass requested names.
    - [x] Verify: Requesting "openloto" only fetches "openloto".
- [x] **BUG-01: Propagate Timeout/Retries to Polla Scraper**
    - [x] Update `get_pozo_polla` in `pozos.py` to use `timeout` for `wait_for_selector` and `click`.
    - [x] Pass `timeout` to `StealthyFetcher`.
    - [x] Verify: Polla scraper honors custom timeout.
- [x] **TEST-01/05: Resilience & Degraded Mode**
    - [x] Remove `# pragma: no cover` from `pipeline.py`.
    - [x] Implement `confidence` scoring in `_run_ingestion_for_sources`.
    - [x] Update `API_VERSION` to `v1.2` in `contracts.py`.
    - [x] Verify: Pipeline continues if one source fails (confidence: degraded).
    - [x] Verify: Pipeline fails if all sources fail.

## Phase 2: Observability & Hardening
- [x] **DEBT-02: Fix Over-eager Redaction**
    - [x] Refine `_should_redact_key` in `obs.py`.
    - [x] Verify: `"monkey"` is not redacted; `"api_key"` is.
- [x] **DEBT-03: Refactor Log Stream to Typed Protocol**
    - [x] Define `_LogStream` Protocol in `pipeline.py`.
    - [x] Update `_init_log_stream` return type.
    - [x] Remove `type: ignore` comments.
- [x] **DEBT-04/05: Improve Discrepancy Reporting**
    - [x] Populate `missing_sources` in `_merge_pozos`.
    - [x] Pass mismatches directly to `_build_report_payload`.
    - [x] Verify: `comparison_report.json` shows missing sources correctly.

## Phase 3: CLI UX & Notifications
- [x] **BUG-02: Deprecate --no-include-pozos**
    - [x] Add warning in `__main__.py`.
    - [x] Verify warning on execution.
- [x] **DEBT-01: Clarify CLI Help Texts**
    - [x] Update `force-publish` descriptions in `run` and `publish` commands.
- [x] **FEAT-02: Detailed Slack Notifications**
    - [x] Enhance `notifiers.py` with rich discrepancy formatting.
    - [x] Call notifier from pipeline on quarantine.
    - [x] Verify Slack payload structure via mock.

## Phase 4: Final Validation
- [x] **CI-03: Add Coverage Threshold**
    - [x] Add coverage config to `pyproject.toml`.
    - [x] Verify 80% threshold is met.
- [x] **DOCS-01/03: Update Documentation**
    - [x] README env vars and Mermaid diagram.
- [x] **Final E2E Verification**
    - [x] Run all tests in `tests/e2e/`.
