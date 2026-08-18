# Plan 039: Consolidate the per-game category registries into one source of truth

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/sources/kino.py polla_app/sources/prices.py polla_app/stats.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: MED (label strings are the contract with the sheet and the site; keep them byte-identical)
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The Kino category set exists in three places and has already drifted:
`kino.py:42-50` (`_POZO_FIELDS`) includes `"Kino Gran Sueldo"`, but
`prices.py:48-55` (`_KINO_PRICE_FIELDS`) and `stats.py:143-150`
(`_KINO_CATEGORIES`) do not. A pendón prize for Gran Sueldo would render in
the Kino ticket (site.py reads the record's `pozos_proximo`) with no stats
row and no live price — exactly the "category published but not presented"
asymmetry the stats layer exists to prevent. Loto labels are likewise split
across `pozos.py:20-33`, `prices.py:62-70`, `stats.py:128-136`, and the
img-src mapping in `pozos.py:391-409`. Every category change requires
lockstep edits in 6+ files, and the next game addition would inherit the
same problem.

## Current state

`polla_app/sources/kino.py:42-50` — `_POZO_FIELDS: dict[str, str]` maps
pendón field → canonical label:
`Kino`, `ReKino`, `RequeteKino`, `Chao Jefe $2 Millones`,
`Chao Jefe $3 Millones`, `Súper Combo Marraqueta`, `Kino Gran Sueldo`.

`polla_app/sources/prices.py:48-55` — `_KINO_PRICE_FIELDS` (hub field →
label): same first six labels, **no `Kino Gran Sueldo`**.

`polla_app/stats.py:143-150` — `_KINO_CATEGORIES`: the same six labels
(verify exact contents when editing).

`polla_app/sources/pozos.py:20-33` — `_LABEL_PATTERNS` (label → regex) for
Loto: `Loto Clásico`, `Recargado`, `Revancha`, `Desquite`,
`Jubilazo $1.000.000`, `Jubilazo $500.000`, `Jubilazo 50 años $1.000.000`,
`Jubilazo 50 años $500.000`, `Total estimado`.

`polla_app/sources/prices.py:62-70` — `_CATEGORY_ORDER`: `Loto Clásico`,
`Recargado`, `Revancha`, `Desquite`, `Jubilazo`, `Multiplicar`,
`Jubilazo 50 años` (note: `Multiplicar` and `Jubilazo` — different label
shapes than pozos.py's; the mapping between them is not 1:1).

`polla_app/stats.py:128-136` — `_PRICE_CATEGORY_MAP` (stats-sheet category
→ pipeline categories, incl. the `_sum_prizes` aggregation).

Repo convention: labels must never collide across games (Kino keeps the
`Kino `/`Kino`-distinct naming, see AGENTS.md "Source Parsers" section and
the kino.py docstring).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_kino.py tests/test_prices.py tests/test_stats.py tests/test_contracts.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |
| Label drift check | `python - <<'PY'
from polla_app.sources.kino import _POZO_FIELDS
from polla_app.sources.prices import _KINO_PRICE_FIELDS
from polla_app.stats import _KINO_CATEGORIES
kino = set(_POZO_FIELDS.values())
prices = {label for _, label in _KINO_PRICE_FIELDS}
stats = set(_KINO_CATEGORIES)
print("only in kino.py:", sorted(kino - prices - stats))
print("only in prices:", sorted(prices - kino - stats))
print("only in stats:", sorted(stats - kino - prices))
PY` | after the fix: all three sets printed empty |

## Scope

**In scope** (the only files you should modify):
- `polla_app/sources/common.py` (or a new `polla_app/sources/categories.py`) — the single source of truth
- `polla_app/sources/kino.py`, `polla_app/sources/prices.py` — import from it
- `polla_app/stats.py` — import from it
- `tests/test_contracts.py` — a test asserting the registry is consistent (and lock the current label sets)

**Out of scope** (do NOT touch, even though they look related):
- Changing any label string — the sheet/site consumers key on the exact strings
- `pipeline.py`'s consensus logic (it treats labels as opaque keys)
- The Loto price structure (`_CATEGORY_ORDER`) — it is a different shape (price-block order, not a label set); consolidate only where a true 1:1 set exists
- Fixing the "Kino Gran Sueldo has no price" gap itself — that's a data/upstream question; this plan only makes the drift *visible* and impossible to recreate

## Git workflow

- Branch: `advisor/039-category-registry`
- Commit message style: `refactor(sources): registro único de categorías por juego (Kino/Loto)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create the single source of truth

In `polla_app/sources/categories.py` (new module — leaf, imports nothing
from the package besides typing), define:

```python
"""Canonical category label registries per game.

Single source of truth for category labels. Consumers (kino.py, prices.py,
stats.py, site.py) import from here; the strings ARE the contract with the
Google Sheet and the dashboard — never rename a label here without a
migration.
"""

KINO_CATEGORY_LABELS: frozenset[str] = frozenset({
    "Kino", "ReKino", "RequeteKino", "Chao Jefe $2 Millones",
    "Chao Jefe $3 Millones", "Súper Combo Marraqueta", "Kino Gran Sueldo",
})

# pendón field -> canonical label (kino.py's _POZO_FIELDS, moved here)
KINO_POZO_FIELDS: dict[str, str] = {...transcribe from kino.py:42-50...}

# hub field -> canonical label (prices.py's _KINO_PRICE_FIELDS, moved here)
KINO_PRICE_FIELDS: tuple[tuple[str, str], ...] = {...transcribe from prices.py:48-55...}
```

**Decision point**: include `Kino Gran Sueldo` in `KINO_PRICE_FIELDS`? Do
NOT add it — the hub has no such field today; the price set remains the six
fields, and the consistency test (Step 3) will assert
`set of price labels ⊆ KINO_CATEGORY_LABELS`, with the known gap
documented in the test (not silently closed).

**Verify**: the module imports cleanly: `python -c "import polla_app.sources.categories"` → exit 0.

### Step 2: Route the three modules through it

- `kino.py`: replace `_POZO_FIELDS` definition with
  `from .categories import KINO_POZO_FIELDS as _POZO_FIELDS` (keep the
  local name to avoid touching call sites, or update call sites — prefer
  keeping the local alias for a minimal diff).
- `prices.py`: replace `_KINO_PRICE_FIELDS` with the import alias.
- `stats.py`: replace `_KINO_CATEGORIES` with
  `from .sources.categories import KINO_CATEGORY_LABELS` adapted to the
  local expected type (list/set — match the existing usage in stats.py:
  read how `_KINO_CATEGORIES` is consumed first).

**Verify**: `pytest tests/test_kino.py tests/test_prices.py tests/test_stats.py -q` → all pass.

### Step 3: Lock the consistency with a contract test

In `tests/test_contracts.py`, add:

```python
def test_kino_category_registries_consistent() -> None:
    from polla_app.sources.categories import (
        KINO_CATEGORY_LABELS, KINO_POZO_FIELDS, KINO_PRICE_FIELDS,
    )
    pozo_labels = set(KINO_POZO_FIELDS.values())
    price_labels = {label for _, label in KINO_PRICE_FIELDS}
    assert pozo_labels <= KINO_CATEGORY_LABELS
    assert price_labels <= KINO_CATEGORY_LABELS
    # "Kino Gran Sueldo" is pendón-only today (no hub price field) — if the
    # hub adds it, extend KINO_PRICE_FIELDS.
    assert price_labels == KINO_CATEGORY_LABELS - {"Kino Gran Sueldo"}
```

**Verify**: `pytest tests/test_contracts.py -q` → new test passes with the
documented gap.

## Test plan

- New contract test (Step 3) in `tests/test_contracts.py`.
- Existing suites (`test_kino.py`, `test_prices.py`, `test_stats.py`) are
  the regression net for the import migration.
- The drift-check command in the Commands table must print empty sets after
  the fix (for the price/pozo vs category comparison, accounting for the
  documented Gran Sueldo gap).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_contracts.py tests/test_kino.py tests/test_prices.py tests/test_stats.py -q` exits 0
- [ ] The drift-check command prints empty `only in ...` sets (with the Gran Sueldo gap documented in the test, not in the console output)
- [ ] `grep -rn "_POZO_FIELDS\s*=\|_KINO_PRICE_FIELDS\s*=\|_KINO_CATEGORIES\s*=" polla_app/` → no direct definitions outside `categories.py`
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any label string differs between the three current registries in a way you can't reconcile (e.g. an extra label in stats.py you didn't expect) — report the exact differences before consolidating.
- A consumer of `_KINO_CATEGORIES` needs a list (indexed access) while you provided a frozenset — adapt the type at the import site, not by mutating the canonical set.
- The Loto-side consolidation (pozos/prices/stats label sets) turns out to require a mapping table that doesn't exist (e.g. `Multiplicar` has no pozos.py label) — leave Loto out of this plan and report; do not invent mappings.

## Maintenance notes

- Adding a new category = one edit in `categories.py` + updating `KINO_PRICE_FIELDS` if the hub publishes it + a one-line contract-test change; the drift check will flag any miss.
- The known Gran Sueldo gap (pendón prize without hub price) stays documented in the contract test; when the hub adds the field, close it there.
- Plans 024 (site history) and 030 (state per game) don't touch these labels, but site.py's Kino detection (label sniffing) can later import `KINO_CATEGORY_LABELS` instead of duplicating the list.
