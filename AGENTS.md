# AGENTS – Working Agreement for Code Changes

This repository uses AGENTS.md to guide AI/automation and humans on how to make safe, high‑quality changes quickly. Everything here applies to the entire repo.

## Prime Directives
- Keep public behavior stable unless explicitly requested. Avoid breaking changes.
- Prefer minimal, surgical diffs that fix the root cause.
- All linters, type checks, tests, and docs doctests must pass.
- Do not leak secrets. Redact sensitive data in logs and examples.
- Document non‑obvious code with concise, helpful docstrings.

## Project Overview
- Language: Python 3.10+
- Package: `polla_app` – alternative‑source ingestion for Chilean Loto (pozos only)
- CLI entry: `python -m polla_app` with commands: `run`, `publish`, `pozos`, `health`
- Tests: `pytest -q` (unit, integration, doctests)
- Style: Black, Ruff (including pep8‑naming), Mypy (strict-ish)
- Observability: structured JSON logs with correlation IDs, spans, and metrics
- Contracts: artifacts/results include `api_version` (see `polla_app/contracts.py`)

## What to Change (and What Not)
- OK: bug fixes, test additions, small refactors that preserve behavior, performance improvements that keep outputs the same, docs changes.
- ASK FIRST: adding new dependencies, changing CLI flags or outputs, network‑heavy features, schema or API changes (see Contracts).
- DO NOT: commit secrets, hardcode credentials, add flakey/online tests, remove existing public flags or keys without a migration.

## Versioning & Contracts
- Package version single‑source: `polla_app/__init__.py: __version__`.
  - `pyproject.toml` reads it dynamically (`[tool.setuptools.dynamic]`). Don’t add another version constant.
- Artifact/result API version: `polla_app/contracts.py: API_VERSION`.
  - If you add fields: keep them additive and update tests & docs. If you must remove/rename, bump `API_VERSION` and provide migration notes.
- Deprecations: keep backward‑compat aliases for at least one MINOR version (e.g., `_normalise_*` → `_normalize_*`).

## Environment & Config (12‑Factor)
- Inputs via env vars (don’t hardcode):
  - `GOOGLE_SPREADSHEET_ID` (required for publish, not for dry‑run)
  - Credentials: `service_account.json` file OR `GOOGLE_SERVICE_ACCOUNT_JSON` OR `GOOGLE_CREDENTIALS`/`CREDENTIALS`
  - `ALT_SOURCE_URLS` (JSON mapping for source overrides)
  - `POLLA_USER_AGENT` (override HTTP UA)
  - `POLLA_RATE_LIMIT_RPS` (optional per‑host rate limit)

## Observability
- Use `polla_app.obs`:
  - `set_correlation_id` and correlation propagation is handled by the pipeline logger.
  - `span(name, log, attrs=...)` around meaningful phases.
  - `metric(name, log, kind=..., value=..., tags=...)` for counters/gauges.
  - `sanitize(...)` is applied before writing logs; don’t bypass unless necessary.
- Logs must be structured JSON; avoid logging secrets or large payloads.

## Error Handling
- Use the taxonomy in `polla_app/exceptions.py`:
  - `ConfigError` for missing/invalid config
  - `RobotsDisallowedError` for robots.txt denials (subclasses PermissionError)
  - `ScriptError` base provides `error_code`, `context`, `log_error()`
- Error messages should be actionable and safe (no secret values).

## Source Parsers
- DRY: prefer shared helpers (e.g., `_fetch_pozos`) and precompiled regexes.
- Respect robots.txt and env UA override.
- Never add network calls to tests; stub or provide fixtures.

## CLI
- `run`: pozos‑only ingestion; preserves state; emits artifacts and JSON logs.
- `publish`: dry‑run by default in tests; requires spreadsheet + credentials to write.
- `pozos`: prints current estimates.
- `health`: offline/online health checks with structured output.
- Add new commands only if they are testable and documented.

## Testing & CI
- Run locally:
  - `ruff check .`
  - `black .`
  - `mypy polla_app tests`
  - `pytest -q`
  - Doctests for docs: `pytest --doctest-glob='*.md' README.md docs -q`
- CI workflows:
  - `tests.yml`: Ruff, Black (check), Mypy, Pytest
  - `docs.yml`: doctests (installs package with `pip install -e .`)
  - `health.yml`: daily offline health
- Tests must be deterministic; use fixtures and monkeypatching for IO/HTTP.

## Coding Standards
- Keep functions small and single‑purpose; write docstrings for non‑obvious logic.
- Use typing everywhere (Mapping/Iterable for read‑only params).
- Names: snake_case for functions/vars; CapWords for classes; avoid abbreviations.
- Do not introduce global mutable state except via controlled caches (e.g., rate limiter). Guard with tests.

## Contracts: When Schema Changes Are Needed
1. Propose change, indicating:
   - Affected artifacts/fields
   - Backward compatibility strategy
   - API version impact (`API_VERSION` bump only if breaking)
2. Add/extend tests in `tests/test_contracts.py` to lock new schema.
3. Update docs in `docs/VERSIONING.md` and README if user‑visible.
4. Ship with additive fields wherever possible.

## Release Checklist (Human‑run)
- [ ] All CI checks green (tests, docs doctests, health offline)
- [ ] Bump `polla_app.__version__` and add CHANGELOG entry
- [ ] Verify artifacts include correct `api_version`
- [ ] Sanity check `health --online` in a safe environment

## Performance Guidelines
- Avoid unnecessary network or parsing work.
- Reuse precompiled regexes and cached robots.txt parsers.
- Use opt‑in `POLLA_RATE_LIMIT_RPS` to be a good citizen when sources are polled frequently.

## Security & Privacy
- Never log tokens or credentials; rely on redaction.
- Treat environment values as sensitive unless documented otherwise.
- Do not add telemetry that sends data to third parties.

## Documentation
- Keep README concise with runnable snippets.
- Update `docs/API.md`, `docs/SLOs.md`, and `docs/VERSIONING.md` when changing APIs, reliability SLOs, or contracts.
- Prefer doctest‑style examples for small code snippets.

---
Following this guide ensures consistent, safe updates that respect user trust, testing, and operations. If a change requires bending these rules, document the exception and rationale in the PR description and the code.
