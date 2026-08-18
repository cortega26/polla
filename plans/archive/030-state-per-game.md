# Plan 030: Namespace the shared state file per game (Loto vs Kino)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/pipeline.py polla_app/__main__.py .github/workflows/scrape.yml .github/workflows/pages.yml tests/test_pipeline.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (additive; single-game runs keep identical behavior)
- **Depends on**: none (run after 024 if possible — 024 reads the state file; 030 changes its layout — see Maintenance notes)
- **Category**: bug
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Both games write the same state file: `scrape.yml:117` (Loto) and
`scrape.yml:139` (Kino) both pass `--state-file pipeline_state/last_run.jsonl`.
`_persist_state` dedupes on the game-blind key `(sorteo, fecha)`
(pipeline.py:398-401) and `_compute_unchanged` matches any prior record
with the same key regardless of game (pipeline.py:424-440). Two silent
failure modes: a Kino draw whose `(sorteo, fecha)` coincides with a Loto
record's replaces it (and vice versa), disabling unchanged-detection; and
the 1000-record budget is shared, halving each game's memory. The
read-modify-write is also unlocked (unlike `publish`, which takes
`_PublishLock`), so two overlapping workflow runs can lose a record. This
plan separates state per game at the workflow level (the minimal,
contract-safe fix) and namespaces the dedup key with a `game` field for
defense in depth.

## Current state

`polla_app/pipeline.py:389-411` (`_persist_state`):

```python
    key = (new_record.get("sorteo"), new_record.get("fecha"))
    updated = [
        record for record in previous_records if (record.get("sorteo"), record.get("fecha")) != key
    ]
    updated.append(dict(new_record))
    # Prune oldest entries (insertion order is chronological).
    if len(updated) > MAX_STATE_RECORDS:
        updated = updated[-MAX_STATE_RECORDS:]
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as handle:
        for record in updated:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
```

`pipeline.py:413-440` (`_compute_unchanged`): iterates `previous_records`,
matching on `prev.get("sorteo") == sorteo and prev.get("fecha") == fecha`.

Workflow state paths:
- `scrape.yml:117` — Loto: `--state-file pipeline_state/last_run.jsonl`
- `scrape.yml:139` — Kino: `--state-file pipeline_state/last_run.jsonl` (same!)
- `pages.yml` — restores `pipeline_state` (per plan 024) and passes the flag to `site`

`pipeline.py` knows which game a run is: `requested_sources[0] == "kino"`
vs Loto (`"pozos"`/`"openloto"`/`"polla"`). There is no `game` field in
records today. Plan 024's `site` history reader classifies records by
label-sniffing — this plan should not break that.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (pipeline) | `pytest tests/test_pipeline.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `.github/workflows/scrape.yml` — per-game state file paths (Loto keeps `last_run.jsonl`; Kino moves to `last_run_kino.jsonl` — or both move; keep Loto unchanged for continuity with plan 024's cache key)
- `.github/workflows/pages.yml` — if it references the state path, mirror the change
- `polla_app/pipeline.py` — add a `game` field to persisted records and namespace `_persist_state`/`_compute_unchanged` matching on it
- `tests/test_pipeline.py` — new/extended tests

**Out of scope** (do NOT touch, even though they look related):
- Adding a lock around state read-modify-write (the `_PublishLock` pattern) — separate concern; note it in the report if you think it's urgent
- `publish.py`, `site.py` (except where plan 024's cache restore already exists)
- Changing `MAX_STATE_RECORDS`
- Plan 024's label-based game classification — keep it working (see Step 2)

## Git workflow

- Branch: `advisor/030-state-per-game`
- Commit message style: `fix(pipeline): estado por juego — dedupe con campo game y archivos separados`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Per-game state files in workflows

- `scrape.yml:117` — Loto keeps `--state-file pipeline_state/last_run.jsonl` (unchanged).
- `scrape.yml:139` — Kino changes to `--state-file pipeline_state/last_run_kino.jsonl`.
- `pages.yml` — if the `site` step passes `--state-file pipeline_state/last_run.jsonl` (from plan 024), it stays for Loto; Kino history (plan 024's state-based history reads one file today) will keep working via the Loto file — note this limitation in the report and in Maintenance notes (plan 024's history reader can later read both files).

**Verify**: `grep -n "state-file" .github/workflows/scrape.yml` → Loto line unchanged, Kino line ends with `last_run_kino.jsonl`.

### Step 2: Namespace records by game in `pipeline.py`

In `_run_ingestion_for_sources` (the function that builds the record at
pipeline.py:608-616 and calls `_persist_state`/`_compute_unchanged` at
640-646), determine the game once:

```python
    game = "kino" if requested_sources[0] == "kino" else "loto"
```

Add `"game": game` to the `record` dict (additive field — check
`tests/test_contracts.py` for schema assertions; adding a field is additive
per the repo's API_VERSION policy, but update `test_contracts.py` if it
asserts the exact key set).

Then:
- `_persist_state`: key on `(new_record.get("game"), sorteo, fecha)`; when removing duplicates, match all three.
- `_compute_unchanged`: add a `game: str` keyword parameter; match `prev.get("game") == game` in addition to sorteo/fecha. For backward compatibility with state files written before this change (no `game` field), treat records without a `game` field as matching any game **only** when the current record's game matches the file's dominant game — simpler: treat missing `game` as `"loto"` for Loto runs and skip for Kino runs (Kino runs previously shared the file, so their old records would be misattributed — acceptable: they'll be re-added once, one-time dedup blip). Document whichever choice you make in the report and in a code comment.

**Verify**: `pytest tests/test_pipeline.py -q` → all pass; check
`tests/test_contracts.py` for the record schema and update if it enumerates keys.

### Step 3: Tests

In `tests/test_pipeline.py`:

1. `test_persist_state_namespaces_by_game` — write two records with the
   same `(sorteo, fecha)` but `game` "loto" vs "kino" via `_persist_state`
   on a fresh path; assert both survive (2 lines).
2. `test_compute_unchanged_ignores_other_game` — previous record with same
   sorteo/fecha but different `game` → returns False.
3. `test_compute_unchanged_same_game_matches` — same game + same
   sorteo/fecha + same sha → True.
4. If feasible: a `run_pipeline`-level test running Loto then Kino with
   identical sorteo/fecha against the same state file → second run's
   decision is not a false "unchanged skip".

**Verify**: `pytest tests/test_pipeline.py -q` → all pass (existing + 3-4 new).

## Test plan

- New tests in `tests/test_pipeline.py` per Step 3, modeled on the existing
  `_persist_state`/`_compute_unchanged` tests in that file (search for
  `_persist_state(` in the test file for the fixture pattern).
- `tests/test_site.py` (plan 024) must still pass — the `game` field is
  additive and label-sniffing still works.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "last_run_kino" .github/workflows/scrape.yml` shows the Kino path
- [ ] `grep -n '"game"' polla_app/pipeline.py` shows the record field and the keying
- [ ] `pytest tests/test_pipeline.py -q` exits 0 with the new tests present (`grep -c "game" tests/test_pipeline.py` >= 3)
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `test_contracts.py` asserts an exact record key set and you cannot satisfy both additive-field and contract tests — report (contract update is the expected resolution, but only with the reviewer's confirmation that it's additive).
- Plan 024's `site` history reader breaks because it relied on a single state file — adjust its call site to also read `last_run_kino.jsonl` (in scope only if 024 has landed; otherwise note it).
- The workflow cache key for `pipeline_state` in pages.yml/scrape.yml needs a change to include the new file — the cache path is the whole directory, so it should already cover it; verify and report if not.

## Maintenance notes

- Plan 024 reads the state file for history; after this plan, Kino history requires reading `last_run_kino.jsonl` too — a follow-up edit in `site.py` (track in the report).
- Old state files (pre-`game`) are handled by the compatibility rule in Step 2 — expect a one-time dedup blip on the first run after deploy; not harmful.
- If a third game is ever added, the pattern is: per-game state file + `game` field — no lockstep edits beyond the workflow path.
- The unlocked read-modify-write remains a latent race for overlapping runs; if that ever bites, the fix is `_PublishLock`-style flock on the state file (noted, not done here).
