# Plan 042: Tolerate trailing punctuation in openloto prize strings

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/sources/pozos.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (per-label skip can only reduce data, never publish wrong amounts)
- **Depends on**: none (runs cleanly after plan 040 — both touch `_parse_millones_to_clp`; if 040 has landed, apply the fix inside `polla_app/numbers.py` and its test in `tests/test_numbers.py` instead)
- **Category**: bug
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The openloto parser is all-or-nothing per label: `_extract_amounts` calls
`_parse_millones_to_clp(match.group(1))` with no exception handling
(pozos.py:148-156), and the greedy capture `[\d\.,]+` (pozos.py:40) can
swallow a trailing dot — e.g. Chilean currency style `$1.000.000.-` or a
sentence-final `$1.000.000.`. The parse then raises `ParseError`
(pozos.py:98-103, 122-127) and the error propagates out of `_fetch_pozos`,
dropping the **entire openloto source** (pipeline.py:159-162) and degrading
the run to `single_source` or aborting. The polla DOM parser handles the
same condition by catching and silently skipping the category
(pozos.py:366-371, 385-389) — the openloto path should be as tolerant.

## Current state

`polla_app/sources/pozos.py:40` (inside the `_LABEL_REGEX` dict
comprehension):

```python
        pattern + r"[^0-9$]{0,50}\$?([\d\.,]+)",
```

`polla_app/sources/pozos.py:148-156`:

```python
def _extract_amounts(text: str, *, allow_total: bool = True) -> dict[str, int]:
    amounts: dict[str, int] = {}
    for label, regex in _LABEL_REGEX.items():
        if not allow_total and label == "Total estimado":
            continue
        match = regex.search(text)
        if match:
            amounts[label] = _parse_millones_to_clp(match.group(1))
    return amounts
```

`_parse_millones_to_clp` failure modes on trailing-dot input: with
`"1.000.000."` the dot-only branch (pozos.py:120-134) sees 3 parts, checks
`len(parts[1:])` — `"000"` is 3 (passes), then `float("1.000.000.")` raises
`ValueError` → `ParseError` (pozos.py:136-143).

The tolerant pattern already in the repo: polla's DOM parser skips
unparseable categories with a log line (pozos.py:366-371 — read it and
mirror its message style).

Tests: `tests/test_monetary_parser.py:41-46` covers `""`, `"$"`, `"abc"`,
`"1.2.3.4"` but not `"1.000.000."` / `"4.300.-"`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_pozo_polla.py tests/test_monetary_parser.py tests/test_pipeline.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/sources/pozos.py` — `_extract_amounts` tolerance (or `_parse_millones_to_clp` stripping — decide in Step 1)
- `tests/test_monetary_parser.py` (or `tests/test_numbers.py` if plan 040 landed) — new cases

**Out of scope** (do NOT touch, even though they look related):
- The polla DOM parser (already tolerant)
- The consensus/quarantine logic
- Changing the regex to exclude trailing dots *by itself* (the tolerance must be in the parse layer so every caller benefits)

## Git workflow

- Branch: `advisor/042-trailing-dot-tolerance`
- Commit message style: `fix(sources): tolerar punto/puntuación final en montos de openloto`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Decide the tolerance layer (parse-level)

Preferred: strip trailing non-numeric separators at the top of
`_parse_millones_to_clp`, right after `cleaned = (raw or "").strip().lower()`:

```python
    cleaned = cleaned.rstrip(".").rstrip("-").strip()
```

This fixes the root cause for every caller (including a future results
parser). Verify against `_parse_millones_to_clp("1.000.000.")` →
`1_000_000_000_000` (1.000.000 millones) and `"4.300.-"` →
`4_300_000_000`. **Important**: only strip trailing characters — never
internal dots (they are thousands separators).

Alternative if you find the strip breaks an existing case: wrap the
per-label call in `_extract_amounts` with `try/except ParseError` logging
the skipped label (mirroring pozos.py:366-371). Do one of the two — prefer
the strip; if you choose the try/except instead, say why in the report.

**Verify**: `python -c "from polla_app.sources.pozos import _parse_millones_to_clp; print(_parse_millones_to_clp('1.000.000.'))"` → `1000000000000`.

### Step 2: Add the regression tests

In `tests/test_monetary_parser.py` (or `tests/test_numbers.py` if 040
landed), add:

1. `test_parse_trailing_dot` — `"1.000.000."` → `1_000_000_000_000`
2. `test_parse_trailing_dash_dot` — `"4.300.-"` → `4_300_000_000`
3. If you used the try/except approach: a source-level test in
   `tests/test_pozo_polla.py` feeding `_extract_amounts` text with a
   trailing-dot amount plus a valid one, asserting the valid label parses
   and the broken one is skipped without raising.

**Verify**: `pytest tests/test_monetary_parser.py tests/test_pozo_polla.py -q` → all pass.

## Test plan

- New cases per Step 2, modeled on the existing `test_monetary_parser.py`
  parametrized cases.
- Full suite green (the pipeline tests exercise the whole openloto path
  with fixtures — they must pass unchanged).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_monetary_parser.py tests/test_pozo_polla.py -q` exits 0 with the new cases (`grep -c "trailing" tests/test_monetary_parser.py` >= 2, or in tests/test_numbers.py if 040 landed)
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `python -c "from polla_app.sources.pozos import _parse_millones_to_clp; print(_parse_millones_to_clp('1.000.000.'))"` prints `1000000000000`
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The `rstrip` approach changes an existing passing case (check `"1.2.3.4"` — trailing `4` is not stripped; internal dots untouched — run the full monetary suite; if something regresses, switch to the try/except approach and report).
- Plan 040 has moved the function to `polla_app/numbers.py` — apply the fix there and update this plan's paths in the report.
- The polla DOM skip pattern (pozos.py:366-371) differs from the described behavior when you read it — adapt the mirror and note it.

## Maintenance notes

- If the upstream ever emits `$1.000.000.-` (with the dash before the dot), the strip handles it; if it emits trailing text like `1.000.000.- aprox.`, the regex capture still stops at the dot — revisit the capture pattern only if a fixture shows it.
- The consensus engine treats a skipped label as a missing source category — consistent with how polla's parser already behaves.
- Keep the strip minimal: no internal rewriting of the string beyond trailing punctuation.
