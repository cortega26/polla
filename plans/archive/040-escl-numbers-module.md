# Plan 040: Consolidate the four es-CL number parsers/formatters into one module

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

- **Priority**: P3
- **Effort**: M
- **Risk**: MED — this is the money path; each port must preserve behavior exactly (int vs float, millones multiplier, separator intent)
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Four implementations of the same es-CL number convention live in four
modules with subtly different semantics: `pozos.py:60-145`
`_parse_millones_to_clp` (85 lines, millones → int CLP, mixed
`1.234,56` support), `stats.py:34-45` `_to_number` (CSV cells → float,
handles `1 en`, `%`, `N/A`), `prices.py:84-85` `_clean_clp` (strip `$`,
dots, spaces → int), and `site.py:32-34` `_format_millones` (int → "X.XXX"
millones display string). A separator edge case discovered in one source
must be fixed in four places, and the parsers have already drifted
(only `_parse_millones_to_clp` handles mixed separators; `_to_number` and
`_clean_clp` interpret ambiguous input differently). Money parsing is the
correctness-critical core of this repo.

## Current state

- `polla_app/sources/pozos.py:60-145` — `_parse_millones_to_clp(raw) -> int` (see the full function in the file: unit detection `mm`/`millones`/`mil`/`m`, separator-intent heuristics with `ParseError` on invalid thousands positions, `float()` conversion, `int(round(value * multiplier))`).
- `polla_app/stats.py:34-45` — `_to_number(raw) -> float | None` (strips `$`/`%`, handles `1 en X`, `N/A`/`na`/`-`, dots→thousands, comma→decimal; returns `None` on unparsable).
- `polla_app/sources/prices.py:84-85` — `_clean_clp(raw) -> int` (`int(raw.replace(".","").replace("$","").replace(" ",""))`).
- `polla_app/site.py:32-34` — `_format_millones(value) -> str` (`f"{value / 1_000_000:,.0f}".replace(",", ".")`).
- Existing conformance suite: `tests/test_monetary_parser.py` (covers `_parse_millones_to_clp` incl. `""`, `"$"`, `"abc"`, `"1.2.3.4"` — plan 042 extends it), plus tests for the other three in `tests/test_stats.py`, `tests/test_prices.py`, `tests/test_site.py`.
- Repo convention: DRY per AGENTS.md; `Mapping`/`Iterable` for read-only params; snake_case; no `from __future__ import annotations`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_monetary_parser.py tests/test_stats.py tests/test_prices.py tests/test_site.py tests/test_pozo_polla.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/numbers.py` (create — new leaf module)
- `polla_app/sources/pozos.py` — `_parse_millones_to_clp` becomes a thin wrapper or is replaced at call sites
- `polla_app/stats.py` — `_to_number` replaced
- `polla_app/sources/prices.py` — `_clean_clp` replaced
- `polla_app/site.py` — `_format_millones` replaced
- `tests/test_monetary_parser.py` — move/extend the conformance suite to the shared module

**Out of scope** (do NOT touch, even though they look related):
- Changing any *behavior* — int vs float, millones multiplier, `None` returns: all preserved exactly
- `tests/test_prices.py`'s `_extract_prices` structure — untouched
- The `_to_number` `"1 en"` handling — copied verbatim
- Plan 042 (trailing-dot tolerance) — separate, but this plan should make room for it (see Maintenance notes)

## Git workflow

- Branch: `advisor/040-escl-numbers-module`
- Commit message style: `refactor(numbers): parser/formateador es-CL unificado (sin cambio de comportamiento)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create `polla_app/numbers.py` with the union of semantics

Move the four functions into the new module with their exact current
bodies (transcribe them — do not "improve" them):

```python
"""Shared es-CL number parsing/formatting helpers.

Four consumers historically duplicated these with subtle differences
(pozos.py, stats.py, prices.py, site.py); the union of their semantics
lives here. Behavior is preserved exactly per consumer — when fixing a
separator edge case, fix it here once and extend the conformance tests.
"""


def parse_millones_to_clp(raw: str) -> int: ...   # body from pozos.py:60-145 (verbatim)


def to_number(raw: str) -> float | None: ...       # body from stats.py:34-45 (verbatim)


def clean_clp(raw: str) -> int: ...                # body from prices.py:84-85 (verbatim)


def format_millones(value: int) -> str: ...        # body from site.py:32-34 (verbatim)
```

Exceptions: `parse_millones_to_clp` raises `ParseError` — the new module
must import it from `..exceptions` (or `.exceptions` depending on layout;
`numbers.py` sits at `polla_app/numbers.py`, so
`from .exceptions import ParseError`). Check for import cycles: exceptions.py
imports only stdlib — safe.

**Verify**: `python -c "import polla_app.numbers"` → exit 0; `pytest tests/test_monetary_parser.py -q` → pass (point it at the new module in Step 2).

### Step 2: Port the four call sites (thin wrappers)

For each consumer, replace the function definition with a wrapper that
keeps the local name (minimal diff, call sites untouched) OR update call
sites to the new names and delete the locals — **prefer the wrapper
approach for pozos.py/stats.py/prices.py/site.py** so no call site changes:

```python
from ..numbers import parse_millones_to_clp as _parse_millones_to_clp
```

Adjust relative imports per module (`polla_app/sources/pozos.py` uses
`..numbers`, `polla_app/site.py` uses `.numbers`, `polla_app/stats.py`
uses `.numbers`). Delete the old bodies. Keep the existing docstrings'
examples where they help; the module-level docstrings in numbers.py
already carry them.

**Verify**: `pytest tests/test_monetary_parser.py tests/test_stats.py tests/test_prices.py tests/test_site.py tests/test_pozo_polla.py -q` → all pass (no behavior change).

### Step 3: Consolidate the conformance tests

Move the `_parse_millones_to_clp` test cases from `tests/test_monetary_parser.py`
into a new `tests/test_numbers.py` (or keep the file and import the new
names — prefer a new `tests/test_numbers.py` and a thin re-export from the
old file if anything else imports it; check with `grep -rn "test_monetary_parser" tests/`). Add coverage for the union:

1. `test_to_number_variants` — `"1 en 3.000.000"`, `"12,5%"`, `"N/A"`, `"-"`, `"1.234,56"` → expected float/None per the current `_to_number` behavior (transcribe from tests/test_stats.py's existing cases if present).
2. `test_clean_clp` — `"$1.000"` → 1000; `"1 000"` → 1000.
3. `test_format_millones` — `1_234_560_000` → `"1.235"` (verify the rounding behavior of the current `f"{...:,.0f}"` — transcribe the exact expected values from tests/test_site.py's existing assertions).

**Verify**: `pytest tests/test_numbers.py tests/test_monetary_parser.py -q` → all pass.

## Test plan

- New `tests/test_numbers.py` with the union cases (transcribed expected values from the existing per-module tests).
- All four consumer suites must pass unchanged — they are the behavior lock.
- Add one cross-check: parse `"1.234,56"` with `parse_millones_to_clp` and `to_number` and assert both honor the mixed separator (documenting that the shared module preserves each function's distinct return type).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_numbers.py tests/test_monetary_parser.py tests/test_stats.py tests/test_prices.py tests/test_site.py tests/test_pozo_polla.py -q` exits 0
- [ ] `grep -rn "def _parse_millones_to_clp\|def _to_number\|def _clean_clp\|def _format_millones" polla_app/` → no function definitions outside `numbers.py` (only import aliases)
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any consumer test fails after the port — the wrapper approach should be behavior-preserving; if a test fails, the transcription differed; report the diff rather than "fixing" behavior.
- Importing `numbers.py` from a `sources/` module creates a cycle (exceptions → obs → ... ) — report; do not rearrange imports beyond the two obvious options (top-level import vs local import).
- `tests/test_monetary_parser.py` is imported by other tests (then keep it as a re-export shim) — report the importers.

## Maintenance notes

- Plan 042 (trailing-dot tolerance) edits `parse_millones_to_clp` — after this plan that's a one-file change plus a test in `tests/test_numbers.py`.
- Any future es-CL edge case (e.g. `$1.000.000.-` suffixes, European decimal style) gets one fix + one conformance test.
- The distinct return contracts (int CLP / float / None) are documented in the module docstring — reviewers should treat a signature change there as a contract change.
