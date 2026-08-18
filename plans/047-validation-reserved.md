# Plan 047: Lock the Kino-numbers validator contract as reserved for the results feature

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/validation.py tests/test_validation.py docs/GAMES.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

`validate_amounts` (validation.py:66-69) and `validate_kino_numbers`
(validation.py:71-88) plus `KINO_NUMBERS_COUNT`/`KINO_MAX_NUMBER` are
exported in `validation.py`'s `__all__` but have **zero production callers** —
production imports only `validate_pozo_payload` (pipeline.py:19,
__main__.py:20). They're dead public surface today. BUT `validate_kino_numbers`
is not cruft: it is the pre-built validation ingredient for the Kino
results feature, which `docs/GAMES.md:35-36` explicitly identifies as the
next expansion (currently blocked by the authenticated results hub). Plain
deletion would discard a working, tested building block. This plan resolves
the ambiguity by documenting the reservation and locking the contract with
a test, so the API is neither silently dead nor accidentally removed.

## Current state

`polla_app/validation.py:66-88`:

```python
def validate_amounts(montos: Mapping[str, Any]) -> list[str]:
    """Validate a single game's amount mapping (CLP). Returns issue codes."""
    return _amounts_issues(montos)


def validate_kino_numbers(numbers: Any) -> list[str]:
    """Validate a Kino winning-numbers list (14 unique numbers in 1..25)."""
    if not isinstance(numbers, list | tuple) or len(numbers) != KINO_NUMBERS_COUNT:
        return [
            f"kino_wrong_number_count:"
            f"{len(numbers) if isinstance(numbers, list | tuple) else type(numbers).__name__}"
        ]
    issues: list[str] = []
    seen: set[int] = set()
    for raw in numbers:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            issues.append(f"kino_non_numeric:{raw!r}")
            continue
        if value < 1 or value > KINO_MAX_NUMBER:
            issues.append(f"kino_out_of_range:{value}")
        if value in seen:
            issues.append(f"kino_duplicate:{value}")
        seen.add(value)
    return issues
```

`validation.py:96-104` (`__all__`) lists `KINO_NUMBERS_COUNT`,
`KINO_MAX_NUMBER`, `validate_amounts`, `validate_kino_numbers`,
`validate_pozo_payload`.

`docs/GAMES.md:32-36`:

```
1. **Resultados de LOTO** ... es la siguiente expansión con mejor relación valor/esfuerzo
2. **Kino números** está bloqueado por el hub autenticado (rckino.loteria.cl redirige
   a la home sin sesión); usar solo pozos del pendón hasta que haya endpoint público.
```

`tests/test_validation.py` already covers `validate_kino_numbers` (count,
range, duplicates, non-numeric) — the code is tested; what's missing is the
intent documentation.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_validation.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/validation.py` — docstrings marking the two functions as reserved
- `tests/test_validation.py` — add a contract test locking the constants' values
- `docs/GAMES.md` — one line pointing at the reservation (optional but recommended)

**Out of scope** (do NOT touch, even though they look related):
- Deleting `validate_kino_numbers`/`validate_amounts` — this plan deliberately keeps them
- `validate_pozo_payload` — production-used; untouched
- The authenticated-hub problem itself (blocked upstream; not fixable in this repo)

## Git workflow

- Branch: `advisor/047-validation-reserved`
- Commit message style: `docs(validation): marcar validadores de números como reservados (feature de resultados)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Document the reservation in the docstrings

Update the two docstrings:

```python
def validate_amounts(montos: Mapping[str, Any]) -> list[str]:
    """Validate a single game's amount mapping (CLP). Returns issue codes.

    Reserved for the results/numbers feature (see docs/GAMES.md); today the
    production path uses ``validate_pozo_payload`` only.
    """
```

```python
def validate_kino_numbers(numbers: Any) -> list[str]:
    """Validate a Kino winning-numbers list (14 unique numbers in 1..25).

    Reserved for the Kino-numbers expansion (docs/GAMES.md). Not called by
    the production pipeline yet — do not delete without removing the GAMES.md
    expansion note.
    """
```

**Verify**: `grep -n "Reserved" polla_app/validation.py` → both functions annotated.

### Step 2: Lock the constants' contract

In `tests/test_validation.py`, add a test:

```python
def test_kino_number_constants_contract() -> None:
    """The constants backing validate_kino_numbers are part of its contract."""
    from polla_app.validation import KINO_MAX_NUMBER, KINO_NUMBERS_COUNT
    assert KINO_NUMBERS_COUNT == 14
    assert KINO_MAX_NUMBER == 25
```

**Verify**: `pytest tests/test_validation.py -q` → all pass (existing + new).

### Step 3: Cross-reference in GAMES.md

In `docs/GAMES.md` line 35-36, append to the "Kino números" recommendation a
pointer: "(El validador `validate_kino_numbers` ya está implementado en
`polla_app/validation.py` y reservado para esta expansión.)"

**Verify**: `grep -n "validate_kino_numbers" docs/GAMES.md` → present.

## Test plan

- New contract test (Step 2) in `tests/test_validation.py`.
- Existing tests already cover the validators' behavior; this plan adds the
  intent documentation and the constants lock.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest -q` exits 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -n "Reserved" polla_app/validation.py` → 2 occurrences
- [ ] `grep -n "test_kino_number_constants_contract" tests/test_validation.py` → present
- [ ] `grep -n "validate_kino_numbers" docs/GAMES.md` → present
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- A production caller of `validate_kino_numbers`/`validate_amounts` appears that the audit missed (grep first) — then the "reserved" framing is wrong; report and this plan becomes unnecessary (the functions are used).
- The constants differ from 14/25 in the code — report the real values; the test must match the code, not the plan.

## Maintenance notes

- When the Kino-results or LOTO-results feature ships, this reservation becomes production use; the contract test stays as the lock.
- The LOTO results expansion (GAMES.md:32-34) will need a *different* validator (Loto draws differ from Kino's 14-of-25) — do not reuse `validate_kino_numbers` for LOTO numbers.
- If a future dead-code sweep (e.g. plan 028's spirit) flags these again, the GAMES.md pointer and docstrings are the reason they stay.