# Plan 043: Make the Kino price-hub extraction tolerant of missing variants

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/sources/prices.py polla_app/pipeline.py tests/test_prices.py tests/test_pipeline.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (skipping only the missing variant; additive, mirrors the pendón's behavior)
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The Kino price hub extraction is all-or-nothing: `_extract_kino_prices`
raises `ParseError` if any of the six hub price fields is absent or `<= 0`
(prices.py:188-194), and `_attach_prices` converts that into "prices
skipped for this run" (pipeline.py:262-264). The same game's pendón parser
deliberately tolerates missing/zero variants (kino.py:98-106 skips them),
and a variant can legitimately be unpublished for a draw (e.g. "Súper
Combo Marraqueta"). The asymmetry means one missing variant kills all six
prices — every Kino row in the dashboard's stats renders "—" even though
five of six prices were available.

## Current state

`polla_app/sources/prices.py:186-196`:

```python
    prices: dict[str, dict[str, int]] = {}
    cumulative = 0
    for field, label in _KINO_PRICE_FIELDS:
        value = draw.get(field)
        if not isinstance(value, int | float) or value <= 0:
            raise ParseError(
                f"Kino hub price field {field} missing for sorteo {draw.get('NumeroSorteo')}",
                context={"draw": draw},
            )
        cumulative += int(value)
        prices[label] = {"delta_clp": int(value), "acumulado_clp": cumulative}
    return {
        "precios": prices,
        "sorteo": draw.get("NumeroSorteo"),
        "fecha": draw.get("FechaSorteo"),
        "cumulative": cumulative,
    }
```

The tolerant pattern to mirror — `polla_app/sources/kino.py:98-106`:

```python
def _extract_montos(outputs: dict[str, Any]) -> dict[str, int]:
    """Map pendón outputs to CLP amounts, skipping zero/absent estimates."""
    montos: dict[str, int] = {}
    for field, label in _POZO_FIELDS.items():
        value = outputs.get(field)
        if not isinstance(value, int | float) or value <= 0:
            continue
        montos[label] = int(value) * 1_000_000
    return montos
```

Consumers of the payload's `precios` dict: `pipeline.py` `_attach_prices`
(262-264) and `site.py` (`current_prices` from `last_loto["precios"]` /
Kino equivalents) — both iterate the dict; missing keys just don't render.
`tests/test_prices.py:30-69` covers the standard structure and the
missing-structure error; `tests/test_pipeline.py:825-906` covers the Kino
price sorteo match/mismatch.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_prices.py tests/test_pipeline.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/sources/prices.py` — `_extract_kino_prices` tolerance
- `tests/test_prices.py` — new cases

**Out of scope** (do NOT touch, even though they look related):
- The Loto price extraction (`_extract_prices`) — its monotonicity guard stays (plan 026 tests it)
- `_extract_kino_prices`'s other guard: when NO variant parses at all, the current behavior (prices dict empty → downstream skips prices) is acceptable — but decide below whether an explicit error is better
- The pendón parser (kino.py) — unchanged

## Git workflow

- Branch: `advisor/043-kino-prices-tolerance`
- Commit message style: `fix(prices): precios Kino tolerantes a variantes ausentes (como el pendón)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Skip missing/zero variants instead of raising

Replace the loop body in `_extract_kino_prices` (prices.py:188-196) so
absent or `<= 0` fields are skipped with a log line, mirroring
`kino.py:_extract_montos`:

```python
    for field, label in _KINO_PRICE_FIELDS:
        value = draw.get(field)
        if not isinstance(value, int | float) or value <= 0:
            LOGGER.info(
                "Kino hub price field %s absent for sorteo %s; skipping",
                field,
                draw.get("NumeroSorteo"),
            )
            continue
        cumulative += int(value)
        prices[label] = {"delta_clp": int(value), "acumulado_clp": cumulative}
```

Keep the "no prices at all" behavior explicit: after the loop, if `not prices`,
raise the existing-style `ParseError` ("Kino hub exposed no valid price
fields") — the pipeline's skip-on-ParseError (pipeline.py:262-264) then
behaves exactly as today for the fully-missing case.

**Verify**: `pytest tests/test_prices.py -q` → all pass (existing
missing-structure test still raises via the new no-prices guard — check its
assertion message and update only if it asserts the old message text).

### Step 2: Add the regression tests

In `tests/test_prices.py`, add:

1. `test_extract_kino_prices_skips_missing_variant` — build a minimal
   `next_data` dict with `initialSorteos.data[0]` containing 5 of the 6
   fields (omit e.g. `PrecioComboMarraqueta`); assert the result has 5
   prices, the cumulative math only sums the present ones, and no exception.
2. `test_extract_kino_prices_zero_variant_skipped` — one field present but
   `0` (or negative); assert it's skipped like the pendón does.
3. `test_extract_kino_prices_all_missing_raises` — all fields absent →
   `pytest.raises(ParseError)`.

Model the fixture shape on the existing `_extract_kino_prices` tests in
that file (read them first — `_extract_kino_prices(next_data)` takes the
parsed dict directly).

**Verify**: `pytest tests/test_prices.py -q` → all pass (existing + 3 new);
`pytest tests/test_pipeline.py -q` → all pass (Kino integration tests
unchanged).

## Test plan

- New tests per Step 2 in `tests/test_prices.py`.
- `tests/test_pipeline.py:825-906` (Kino price match/mismatch) must pass
  unchanged — the payload shape (`precios` dict, `sorteo`, `fecha`,
  `cumulative`) is unchanged.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_prices.py -q` exits 0 with 3 new tests (`grep -c "skips_missing_variant\|zero_variant\|all_missing" tests/test_prices.py` >= 3)
- [ ] `pytest tests/test_pipeline.py -q` exits 0
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -n "raise ParseError" polla_app/sources/prices.py` → the only remaining raise in `_extract_kino_prices` is the no-prices guard
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- An existing test asserts the old per-field ParseError message (then update the assertion to the new no-prices guard, test-only, and note it).
- The hub fixture in `tests/fixtures/sources/prices/` contains a draw where a field is legitimately `<= 0` and the current code path relies on the old error — report the fixture before changing behavior.
- `_attach_prices` (pipeline.py:262-264) treats an empty `precios` differently than expected — read it first; if it differs, adapt the no-prices guard to keep the "prices skipped" outcome identical.

## Maintenance notes

- This mirrors the pendón's tolerance (kino.py:98-106); the two Kino price paths are now consistent — if the hub omits a variant for a draw, the dashboard shows the five real prices and no "—" for the sixth (the row just lacks that category).
- Plan 039 (category registry) makes `_KINO_PRICE_FIELDS` imported — the loop here reads the same canonical tuple; no conflict.
- If the hub ever returns `None` for a field that must exist (structure change), the "all missing" guard raises and the pipeline degrades loudly — the intended fail-safe.
