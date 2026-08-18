# Plan 041: Narrow `_get_or_create_worksheet`'s exception handling to not-found only

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/publish.py tests/test_publish.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (error-handling only; success paths unchanged)
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

`_get_or_create_worksheet` wraps `spreadsheet.worksheet(name)` in
`except Exception` — catching not just gspread's not-found error but also
network/auth/API failures. A transient API failure during the lookup gets
masked into a confusing "worksheet already exists" error from
`add_worksheet`, or — if the add happens to succeed — creates a duplicate
"Normalized" worksheet that subsequent publishes will target. Genuine
outages surface as wrong errors and the publish job fails for the wrong
reason.

## Current state

`polla_app/publish.py:215-220`:

```python
def _get_or_create_worksheet(spreadsheet: Any, name: str) -> Any:
    """Return existing worksheet by name or create it if missing."""
    try:
        return spreadsheet.worksheet(name)
    except Exception:  # noqa: BLE001 – gspread.WorksheetNotFound when not installed
        return spreadsheet.add_worksheet(title=name, rows="200", cols="10")
```

The comment even identifies the intended exception (`WorksheetNotFound`).
gspread's class hierarchy: `gspread.exceptions.WorksheetNotFound` exists in
all supported gspread versions (>=6.1.0). Tests that exercise this path:
`tests/test_publish.py` — the "canonical single-call write" tests
(test_publish.py:272-327) and the discrepancy-tab tests
(test_publish.py:52-132) mock `spreadsheet.worksheet(...)` — check how the
mocks raise before editing (grep `worksheet` and `WorksheetNotFound` in
tests/test_publish.py).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Confirm gspread import | `python -c "from gspread.exceptions import WorksheetNotFound; print('ok')"` | prints ok |
| Tests (publish) | `pytest tests/test_publish.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/publish.py` — the except clause
- `tests/test_publish.py` — add the regression test

**Out of scope** (do NOT touch, even though they look related):
- The `except Exception` at publish.py:237 (read-failure-as-empty in `_update_canonical_worksheet`) — that one's behavior (treat as empty, still write) is deliberate; leave it
- Any other publish error handling
- gspread's `add_worksheet` signature — unchanged

## Git workflow

- Branch: `advisor/041-worksheet-notfound-narrow`
- Commit message style: `fix(publish): solo crear worksheet cuando falta (no enmascarar errores de API)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Narrow the except clause

Replace:

```python
    except Exception:  # noqa: BLE001 – gspread.WorksheetNotFound when not installed
        return spreadsheet.add_worksheet(title=name, rows="200", cols="10")
```

with:

```python
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=name, rows="200", cols="10")
```

Verify `gspread` is imported at module top (publish.py imports gspread
conditionally — check the import block around lines 10-25; if `gspread` is
None-guarded, use the fully qualified name via a local import inside the
function or keep the module-level import as-is; the `_load_credentials`
function already references the module-level `gspread` name, so the
attribute access is safe when gspread is installed).

**Verify**: `pytest tests/test_publish.py -q` → all pass.

### Step 2: Add the regression test

In `tests/test_publish.py`, add:

1. `test_get_or_create_worksheet_creates_when_missing` — mock
   `spreadsheet.worksheet` to raise `gspread.exceptions.WorksheetNotFound`,
   assert `add_worksheet` is called and its result returned (mirror the
   existing mocking style in the file — if the existing tests use a fake
   spreadsheet object, extend it with the raise behavior).
2. `test_get_or_create_worksheet_propagates_api_errors` — mock `worksheet`
   to raise a non-not-found exception (e.g. `ConnectionError("boom")` or
   `gspread.exceptions.APIError("boom")`), assert the exception propagates
   (pytest.raises) and `add_worksheet` is NOT called.

**Verify**: `pytest tests/test_publish.py -q` → all pass (existing + 2 new).

## Test plan

- New tests per Step 2, modeled on the existing fake-spreadsheet pattern in
  tests/test_publish.py.
- The propagation test locks the fix: API errors no longer masquerade as
  worksheet-creation attempts.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "WorksheetNotFound" polla_app/publish.py` → present in the except clause; `grep -n "except Exception" polla_app/publish.py` → only the deliberate one at ~line 237 remains
- [ ] `pytest tests/test_publish.py -q` exits 0 with 2 new tests (`grep -c "get_or_create_worksheet" tests/test_publish.py` >= 2)
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- gspread is imported conditionally in a way that makes `gspread.exceptions` unavailable at that point (None-guard) — report; use the documented conditional-import pattern already in the file instead of inventing one.
- An existing test mocks `worksheet` raising a bare `Exception` (would now propagate) — report the test; it must be updated to raise `WorksheetNotFound` or a specific error, which is a test-only fix.

## Maintenance notes

- When gspread is upgraded (plan 032's lockfile), re-verify `WorksheetNotFound`'s module path — it's stable across gspread 6.x.
- The sibling `except Exception` at publish.py:237 remains intentional (read failure → proceed); a reviewer should not "fix" it without a plan.
