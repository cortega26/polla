# Plan 020: Reject any mixed Loto+Kino source combination at CLI/pipeline entry

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/pipeline.py tests/test_phase3_hardening.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

`_normalize_sources` rejects only `"all"` and the literal `pozos`+`kino`
combination. But `--sources kino,openloto` (both keys exist in
`SOURCE_LOADERS`) slips through, so one run collects a Kino payload and a Loto
payload into a single record: `sorteo`/`fecha` come from the first collected
payload, categories from both games get merged, and that mixed record can be
persisted and published to the Google Sheet. This is exactly the
cross-game contamination the guard (commit b46b5e1) exists to prevent — a
Kino draw's `sorteo` with Loto categories, or vice versa, reaching the
public sheet with a green pipeline.

## Current state

`polla_app/pipeline.py:41-60`:

```python
def _normalize_sources(requested: Sequence[str]) -> list[str]:
    lowered = {item.lower() for item in requested}
    if "all" in lowered or ("pozos" in lowered and "kino" in lowered):
        raise ValueError(
            "Mixing 'pozos' and 'kino' in one run is not supported: each game "
            "must run as a separate invocation (--sources pozos, then --sources kino) "
            "so sorteo/fecha and sheets stay per game"
        )
    if "pozos" in lowered:
        # "pozos" is the Loto aggregate; it absorbs redundant per-source requests
        return ["pozos"]

    normalised: list[str] = []
    for item in requested:
        key = item.lower()
        if key not in SOURCE_LOADERS:
            raise ValueError(f"Unsupported source '{item}'. Available: {', '.join(SOURCE_LOADERS)}")
        if key not in normalised:
            normalised.append(key)
    return normalised
```

The registry (`pipeline.py:783-790`) maps: `pozos`, `openloto`, `polla`
(all Loto) and `kino`. So `{"kino", "openloto"}` passes both checks and is
returned as `["kino", "openloto"]`.

The existing test that locks the current (incomplete) behavior is
`tests/test_phase3_hardening.py:91-112` (`test_normalize_sources_deduplication`):
it asserts `["pozos","kino"]` and `["all"]` raise, but nothing asserts a
per-source Loto name combined with `kino`.

Repo convention: this is the only place where the games-mixing rule lives;
the error message format ("each game must run as a separate invocation ...")
is asserted by tests via `pytest.raises(ValueError, match="separate invocation")`
— keep that phrase in the message.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint | `ruff check polla_app tests` | exit 0 |
| Format check | `black --check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |
| Tests (targeted) | `pytest tests/test_phase3_hardening.py -q` | all pass (2 old + 1 new) |
| Tests (full) | `pytest -q` | all pass |

## Scope

**In scope** (the only files you should modify):
- `polla_app/pipeline.py` — the guard condition in `_normalize_sources`
- `tests/test_phase3_hardening.py` — new assertions

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/__main__.py` — no CLI change needed; `run_pipeline` already routes through `_normalize_sources`
- The `--sources all` behavior — already rejected; do not change the message
- `sources/kino.py`, `sources/pozos.py` — no changes

## Git workflow

- Branch: `advisor/020-mixed-games-guard` (match repo convention: merged `advisor/*` branches)
- Commit message style (Spanish, conventional): `fix(pipeline): rechazar combinaciones mixtas kino+fuentes de Loto`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Tighten the guard

In `polla_app/pipeline.py`, replace the guard condition:

```python
    if "all" in lowered or ("pozos" in lowered and "kino" in lowered):
```

with a condition that also rejects `kino` combined with any per-source Loto
name. The Loto names are `pozos`, `openloto`, `polla` (the keys of
`SOURCE_LOADERS` minus `kino`). Suggested replacement:

```python
    loto_sources = {"pozos", "openloto", "polla"}
    if "all" in lowered or ("kino" in lowered and bool(lowered & loto_sources)):
```

Keep the same `raise ValueError(...)` message (must still match
`"separate invocation"`). The existing rejection of `["all", "openloto"]`
still holds because `"all" in lowered` is checked first.

**Verify**: `pytest tests/test_phase3_hardening.py -q` → all pass, including the new cases from Step 2.

### Step 2: Extend the regression tests

In `tests/test_phase3_hardening.py`, inside `test_normalize_sources_deduplication`
(after the existing `pytest.raises` blocks, before the "pozos collapses" assertions),
add:

```python
    # Any Loto source combined with kino is a mixed-game run and must be rejected
    for mixed in (["kino", "openloto"], ["openloto", "kino"], ["kino", "polla"], ["polla", "kino"]):
        with pytest.raises(ValueError, match="separate invocation"):
            _normalize_sources(mixed)
```

Keep the existing assertions untouched (including
`assert sorted(_normalize_sources(["openloto", "polla"])) == ["openloto", "polla"]`,
which must still pass — two Loto sources are fine).

**Verify**: `pytest tests/test_phase3_hardening.py -q` → 1 test function, all
assertions green; `pytest -q` → full suite green.

## Test plan

- New tests: the 4 mixed combinations above in `test_normalize_sources_deduplication` (tests/test_phase3_hardening.py).
- Structural pattern: the existing `with pytest.raises(ValueError, match="separate invocation")` blocks in the same function.
- The behavior is covered at the unit level; no e2e/CI workflow changes.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_phase3_hardening.py -q` exits 0 with the new assertions present
- [ ] `pytest -q` exits 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] Manual check: `python -c "from polla_app.pipeline import _normalize_sources; _normalize_sources(['kino','openloto'])"` raises `ValueError` containing "separate invocation"
- [ ] `python -c "from polla_app.pipeline import _normalize_sources; print(_normalize_sources(['openloto','polla']))"` prints `['openloto', 'polla']` (unchanged)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The code at the locations in "Current state" doesn't match the excerpts (codebase drifted).
- The existing test `test_normalize_sources_deduplication` fails after your edit in a way you can't explain.
- You discover a fourth Loto source key in `SOURCE_LOADERS` (then the hardcoded set must include it — extend `loto_sources` and re-run).

## Maintenance notes

- If a new Loto source (e.g. `resultados`) is added to `SOURCE_LOADERS` later, it must be added to the `loto_sources` set here — the test with the mixed combinations is the guard for that.
- The same game-separation rule is enforced by CI workflows (separate `run` invocations per game); this plan closes the local/CLI hole only.
- Plan 030 (state file per game) also touches the game-boundary theme but edits `_persist_state`/workflows, not this function — no conflict.
