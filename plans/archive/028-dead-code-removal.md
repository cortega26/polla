# Plan 028: Remove dead code (helpers, params, no-op flags) — no CLI surface changes

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/ tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW — with one explicit exception handled by a STOP condition: the user-visible `--include-pozos` CLI flag is **out of scope** (it stays; only its dead plumbing is removed)
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Five dead items mislead future edits: `_clean_rows` (stats.py) is
superseded by inline cleaning; `get_correlation_id` (obs.py) has no callers;
`NetworkError` (exceptions.py) is never raised or imported; the
`record_source` parameter of `_build_report_payload` is passed at every call
site but never referenced in the body; and the `include` threading through
`_collect_from_sources`/`_collect_pozos`/`_collect_kino` is always `True`
from the only call site — the `if not include: return tuple()` branch is
dead. Each dead item is a place a future fix gets applied to the wrong copy,
and the `include_pozos` parameter of `run_pipeline` is a public API toggle
that does nothing.

## Current state

- `polla_app/stats.py:48-52` — `_clean_rows(reader)` with zero callers.
- `polla_app/obs.py:25-26` — `get_correlation_id()` with zero callers.
- `polla_app/exceptions.py:59-60` — `class NetworkError(ScriptError)` with zero references (grep `NetworkError` across the package).
- `polla_app/pipeline.py:443-478` — `_build_report_payload(..., record_source, ...)` — parameter accepted (line 454) but never used in the body; called at line 667 with `record_source=record["fuente"]`.
- `polla_app/pipeline.py:120-121` (inside `_collect_from_sources`, read the exact lines before editing — the audit shows `if not include: return tuple()` with `include` passed down to `_collect_pozos`/`_collect_kino`), and the only call site at pipeline.py:568 passes `loader(True, ...)`.
- `polla_app/pipeline.py:740` — `include_pozos: bool` parameter of `run_pipeline`, never referenced in the body. The CLI flag `--include-pozos/--no-include-pozos` (`__main__.py:148-152, 184-190`) still parses it and prints a deprecation warning on `False` — **this flag and its warning stay** (user-visible; AGENTS.md requires a migration for removal).

Verify zero callers with grep before deleting each item.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Zero-caller check | `grep -rn "_clean_rows\|get_correlation_id\|NetworkError\|record_source" polla_app/ tests/` | only the definitions + known call sites (after Step 1: definitions gone) |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/stats.py` — delete `_clean_rows`
- `polla_app/obs.py` — delete `get_correlation_id`
- `polla_app/exceptions.py` — delete `NetworkError`
- `polla_app/pipeline.py` — drop `record_source` param; drop the `include` threading; drop `include_pozos` from `run_pipeline` signature (update the single call site in `__main__.py:229`)

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/__main__.py` — the `--include-pozos/--no-include-pozos` CLI option and its deprecation warning stay (only the `include_pozos=include_pozos` kwarg at the `run_pipeline` call is removed, and only if the signature drops the param)
- `run_pipeline` public signature beyond `include_pozos` — everything else stays
- Tests: do NOT delete tests that reference these items; fix them to match the API (e.g. if a test calls `run_pipeline(include_pozos=...)`, remove that kwarg from the test)

## Git workflow

- Branch: `advisor/028-dead-code-removal`
- Commit message style: `refactor: eliminar helpers y parámetros muertos (sin cambios de CLI)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Verify zero callers, then delete the four dead items

1. `grep -rn "_clean_rows" polla_app/ tests/` — confirm only `stats.py:48` definition.
2. `grep -rn "get_correlation_id" polla_app/ tests/` — confirm only `obs.py:25`.
3. `grep -rn "NetworkError" polla_app/ tests/` — confirm only `exceptions.py:59`.
4. Delete each. Do NOT touch `set_correlation_id` (it is used by pipeline.py:753).

**Verify**: `ruff check polla_app tests` → exit 0; `grep -rn "_clean_rows\|get_correlation_id\|NetworkError" polla_app/ tests/` → no matches.

### Step 2: Drop `record_source` from `_build_report_payload`

- Remove the parameter from the signature (pipeline.py:454).
- Remove `record_source=record["fuente"],` from the call site (pipeline.py:667).

**Verify**: `grep -rn "record_source" polla_app/ tests/` → no matches; `pytest tests/test_pipeline.py -q` → all pass (check whether any test constructs the report payload directly with `record_source=`; if so, remove the kwarg there too — test-only edit, in scope).

### Step 3: Remove the `include` threading

Read `pipeline.py:100-165` (the `_collect_from_sources` and `_collect_pozos`/`_collect_kino` region) before editing. Remove the `include` parameter from each function in the chain and the dead `if not include: return tuple()` branch. Update the loader registry lambdas at pipeline.py:786-788 if they pass `include` (they call `_collect_pozos(*a, **k, only="openloto")` — check the current signature).

**Verify**: `pytest tests/test_pipeline.py -q` → all pass; `grep -n "include" polla_app/pipeline.py` → no matches for the removed threading (remaining hits should only be `include_prices`/`include_pozos`).

### Step 4: Drop `include_pozos` from `run_pipeline` and fix the CLI call site

- Remove `include_pozos: bool,` from `run_pipeline`'s signature (pipeline.py:740).
- In `polla_app/__main__.py:229`, remove the `include_pozos=include_pozos,` kwarg from the `run_pipeline(...)` call. **Do not touch** the option definition, the `if not include_pozos:` deprecation block, or the `include_pozos: bool` parameter of the `run` command function itself.
- Update any test that calls `run_pipeline(..., include_pozos=...)` (grep tests).

**Verify**: `pytest -q` → all pass; `mypy polla_app tests` → exit 0.

## Test plan

- No new tests — existing suites are the regression net.
- If any test referenced the removed APIs, the only edits allowed are removing those references (test-only).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -rn "_clean_rows\|get_correlation_id\|NetworkError\|record_source" polla_app/ tests/` → no matches
- [ ] `grep -rn "include_pozos" polla_app/pipeline.py` → no matches; `grep -n "include_pozos" polla_app/__main__.py` → only the option definition, the deprecation block, and the `run` command parameter remain
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `python -m polla_app run --help` still shows `--include-pozos` (flag preserved)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any item has callers you didn't expect (the grep contradicts the audit) — report the call sites and stop that item.
- Removing `include` threading requires touching `__main__.py` beyond the single kwarg line — report; the CLI surface is guarded.
- A test change would need to assert *new* behavior rather than just dropping a reference — report.

## Maintenance notes

- The `--include-pozos` flag remains a documented no-op; a future plan may remove it entirely (that is a CLI change requiring its own plan per AGENTS.md).
- `set_correlation_id`/`_CORRELATION_ID` stay — they're the live half of the correlation plumbing.
- After this plan, `run_pipeline`'s signature shrinks by one param; plan 030 (state file per game) and 024 (site history) must not resurrect `include_pozos`.
