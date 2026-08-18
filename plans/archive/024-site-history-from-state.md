# Plan 024: Feed bounded draw history into the dashboard from `pipeline_state`

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/site.py polla_app/__main__.py polla_app/pipeline.py tests/test_site.py .github/workflows/pages.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (run before plan 027, which touches `site.py` too)
- **Category**: bug
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The dashboard's "Sorteos recientes" history is capped at `MAX_HISTORY_RECORDS
= 100` (`site.py:17`) but can never show more than ~2 draws, because it is
built from `normalized.jsonl` files that the pipeline truncates to exactly
one record per run (`pipeline.py:645`: `_write_jsonl(normalized_path, [record])`).
The machinery that *does* accumulate bounded per-draw history —
`pipeline_state/last_run.jsonl`, deduped by `(sorteo, fecha)` and pruned at
`MAX_STATE_RECORDS=1000` (`pipeline.py:389-410`) — is already cached across
CI runs (scrape.yml) but read only by `_compute_unchanged`. The fix makes
the dashboard's history real by reading the state file, and unlocks the
cross-run drift detection the backlog names as desired.

## Current state

`polla_app/site.py:17-29`:

```python
MAX_HISTORY_RECORDS = 100


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: dict[tuple[Any, Any], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        records[(record.get("sorteo"), record.get("fecha"))] = record
    return list(records.values())
```

`polla_app/site.py:52-73` (`build_site_payload`) — history is
`loto_records + kino_records` sorted by `fecha` desc, capped at
`MAX_HISTORY_RECORDS`. The Loto/Kino current sections are the last record of
each list, with `previous_payload` fallback for failed games.

`polla_app/__main__.py` `site` command (lines ~345-385) currently calls
`build_site_payload(...)` with `--normalized` / `--normalized-kino` /
`--summary` paths and an optional `--previous-data` JSON file. There is no
`--state-file` option on `site` today.

State records (from `_persist_state`, `pipeline.py:389-410`) are the full
normalized record shape: `sorteo`, `fecha`, `fuente`, `confidence`,
`premios`, `pozos_proximo`, `provenance`, plus `precios` when attached.
**State file mixes both games** (both Loto and Kino runs write
`pipeline_state/last_run.jsonl` — see plan 030). Records do NOT carry a
`game` field today, but Loto and Kino records are distinguishable by
category keys inside `pozos_proximo` (Kino labels all start with `Kino `,
e.g. `"Kino"`, `"ReKino"`, per kino.py:42-50; Loto labels are
`"Loto Clásico"`, `"Recargado"`, ...). This plan must not require a `game`
field (plan 030 introduces game separation later; this plan works with
what exists).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (site) | `pytest tests/test_site.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |
| Doctest | `pytest --doctest-glob='*.md' README.md docs -q` | 0 failed (exit 0 or 5 for no-tests) |

## Scope

**In scope** (the only files you should modify):
- `polla_app/site.py` — add state-file reading for history
- `polla_app/__main__.py` — add `--state-file` (and `--state-file-kino` if you need a second one; prefer one merged file first — see Step 1 decision) option to the `site` command, passed to `build_site_payload`
- `tests/test_site.py` — new tests
- `.github/workflows/pages.yml` — restore/cache `pipeline_state` like scrape.yml does, pass the new flag

**Out of scope** (do NOT touch, even though they look related):
- `pipeline.py` state mechanics (`_persist_state`, `MAX_STATE_RECORDS`) — plan 030
- `publish.py` — no changes
- The `site/data.json` JSON schema — this plan only *adds* history rows that already exist in the schema (the `history` array), no new top-level fields
- `site/index.html` / `site/app.js` — no frontend change required (the history table already renders whatever `history` contains)

## Git workflow

- Branch: `advisor/024-site-history-from-state`
- Commit message style: `feat(site): historial real de sorteos desde pipeline_state`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Read state into `build_site_payload`

In `polla_app/site.py`, change `build_site_payload` to accept an optional
`state_path: Path | None = None` keyword parameter. When provided and the
file exists, load it with the same tolerant line-skipping used by
`pipeline._load_previous_state` (pipeline.py:80-93 — skip invalid JSON
lines with a warning rather than crashing; **do not** import from
`pipeline.py`; replicate the 8-line tolerant loop locally or move it to a
shared helper only if plan 027 has already landed — otherwise inline it).

History semantics: for each game (Loto vs Kino), take the records from the
state file whose `pozos_proximo` keys indicate the game (Kino: any key
starting with `"Kino"` or `"ReKino"` etc. — the prefix `"Kino"` covers
`"Kino"`, `"Kino Gran Sueldo"`; `"ReKino"`, `"RequeteKino"` do not start
with `Kino` but are Kino-only labels — build the classification from the
union of Kino labels in `_POZO_FIELDS` values of kino.py:42-50: `Kino`,
`ReKino`, `RequeteKino`, `Chao Jefe $2 Millones`, `Chao Jefe $3 Millones`,
`Súper Combo Marraqueta`, `Kino Gran Sueldo`; any record whose
`pozos_proximo` has at least one of these keys is a Kino record, else Loto).

Then:
- `history` = merged `loto_records + kino_records` from the state file,
  **plus** the two current `normalized.jsonl` records (they may be fresher
  than the state file in the same run), deduped by `(sorteo, fecha)`,
  sorted by `fecha` desc, capped at `MAX_HISTORY_RECORDS` — same shape as
  today, so the frontend is untouched.
- Keep `loto_section`/`kino_section`/`current_prizes`/`current_prices`
  driven by the current `normalized.jsonl` records exactly as today.

**Verify**: `pytest tests/test_site.py -q` → all existing tests pass
(backward compatible — `state_path` defaults to `None`).

### Step 2: Wire the CLI and the workflow

In `polla_app/__main__.py`, add to the `site` command:

```python
@click.option(
    "--state-file",
    default=None,
    help="Pipeline state file (pipeline_state/last_run.jsonl) to source draw history from.",
)
```

and pass `state_path=Path(state_file) if state_file else None` into
`build_site_payload` (note: `build_site_payload` is called twice today —
once for stats at line ~361 and once inside `write_site_data` at line ~379;
see plan 038 for the double-build removal. For this plan, pass the new
argument at both call sites).

In `.github/workflows/pages.yml`, before the "Ingest Loto pozos" step, add a
cache-restore for `pipeline_state` (mirroring scrape.yml's "Restore pipeline
state" step: `actions/cache/restore@v5`, path `pipeline_state`, key
`pipeline-state-${{ github.ref_name }}-${{ github.run_number }}` with
`restore-keys` fallback), and add `--state-file pipeline_state/last_run.jsonl`
to the `polla site` invocation step (find it — it currently passes
`--normalized`, `--normalized-kino`, `--output`, `--previous-data`).

**Verify**: `pytest tests/test_site.py -q` → pass; manually
`python -m polla_app site --help` → shows `--state-file`.

### Step 3: Tests

In `tests/test_site.py`, add:

1. `test_build_site_payload_history_from_state_file` — write a state file
   with 3 Loto records (distinct `(sorteo, fecha)`, one matching the
   current normalized record), build the payload with `state_path`, assert
   `history` contains all 3 distinct draws in date-desc order.
2. `test_build_site_payload_state_mixed_games` — state file with 2 Loto and
   2 Kino records; assert history has 4 entries and the Kino entries are
   classified under the Kino keys (they must not be dropped).
3. `test_build_site_payload_state_tolerant_of_bad_lines` — state file with
   one garbage line among valid ones; assert no exception and valid history.
4. `test_site_cli_accepts_state_file` — via the existing `_invoke_site`
   helper (tests/test_site.py:14-24), add `--state-file` to the args and
   assert exit 0.

**Verify**: `pytest tests/test_site.py -q` → all pass (existing + 4 new).

## Test plan

- New tests listed in Step 3, in `tests/test_site.py`, modeled on the
  existing `_write_ndjson` + `build_site_payload` tests in that file.
- The state-file fixture format is one JSON object per line (same as
  `_write_ndjson` produces).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_site.py -q` exits 0 with 4 new tests present (`grep -c "state_file" tests/test_site.py` >= 4)
- [ ] `pytest -q` exits 0; `ruff check polla_app tests`; `black --check polla_app tests`; `mypy polla_app tests` all exit 0
- [ ] `python -m polla_app site --help` shows `--state-file`
- [ ] `grep -n "pipeline_state" .github/workflows/pages.yml` shows restore-cache and flag usage
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- You find that state records do not contain `pozos_proximo` (the classification would break) — report; the game-classification approach must change.
- Plan 027 has already landed and provides a shared `read_jsonl` — use it instead of inlining the tolerant loop.
- The `site` command's call structure differs from the two-calls description (e.g. after plan 038 lands, there is one call) — adapt the argument plumbing to the actual structure and note it in the report.

## Maintenance notes

- Plan 030 (state file per game) will change the state file layout; when it lands, revisit the game classification here — if a `game` field is added, use it instead of label sniffing.
- The history now reflects cross-run data; the `MAX_HISTORY_RECORDS=100` cap finally has meaning.
- Drift detection (backlog) can now be added on top of this history without new collection.
