# Plan 027: Consolidate the three JSONL readers and two writers into shared helpers

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/site.py polla_app/publish.py polla_app/pipeline.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (pure file I/O consolidation; behavior preserved by existing tests)
- **Depends on**: none (recommended after 024 — both touch `site.py`; if 024 hasn't landed, you may still do this plan, but flag the interaction in the report)
- **Category**: tech-debt
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Three hand-rolled JSONL readers and two writers exist across the package;
two of the readers (`site.py:_load_ndjson` and `publish.py:_load_normalized_ndjson`)
are the same dedup-by-`(sorteo, fecha)` loop copied verbatim, while
`pipeline.py:_load_previous_state` is a third reader that differs by
tolerating invalid lines. The two writers (`pipeline.py:_write_jsonl` and the
inline loop in `_persist_state`) duplicate the same dump+newline loop. Any
format change must be applied in 3-4 places, and the dedup/tolerance rules
already differ between readers — a corrupted line crashes `site`/`publish`
but is skipped by `pipeline`. One shared module fixes the divergence risk
and gives plan 024 (and future consumers) a single, tolerant reader.

## Current state

`polla_app/site.py:20-29`:

```python
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

`polla_app/publish.py:68-81` — `_load_normalized_ndjson`: identical loop
(comment differs: "Each line must be a valid JSON object. Records are keyed
by (sorteo, fecha) ...").

`polla_app/pipeline.py:80-93` — `_load_previous_state`: tolerant loop
(skips invalid lines with `LOGGER.warning`), no dedup.

`polla_app/pipeline.py:72-77` — `_write_jsonl`:

```python
def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")
```

`polla_app/pipeline.py:406-410` — `_persist_state` reimplements the same
write loop inline.

Repo convention: small pure helpers live at module level with docstrings;
`Mapping`/`Iterable` used for read-only params (see AGENTS.md typing rules
and e.g. `_write_jsonl` above).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Format | `black --check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/io.py` (create — new leaf module)
- `polla_app/site.py` — use shared readers
- `polla_app/publish.py` — use shared readers
- `polla_app/pipeline.py` — use shared readers/writers
- `tests/test_contracts.py` or a new `tests/test_io.py` — tests for the shared helpers

**Out of scope** (do NOT touch, even though they look related):
- Behavior changes: dedup semantics, tolerance, pruning — all preserved exactly
- `polla_app/validation.py`, `polla_app/stats.py` — no JSONL usage there
- The state-file game separation (plan 030) and the site history change (plan 024)

## Git workflow

- Branch: `advisor/027-jsonl-io-consolidation`
- Commit message style: `refactor(io): helpers compartidos de lectura/escritura JSONL`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create `polla_app/io.py`

New module with three functions:

```python
"""Shared JSONL (NDJSON) read/write helpers."""


def read_jsonl(path: Path, *, dedup_key: Callable[[dict[str, Any]], Any] | None = None, tolerant: bool = False) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts.

    - ``dedup_key``: when given, later records with the same key replace
      earlier ones (e.g. lambda r: (r.get("sorteo"), r.get("fecha"))).
    - ``tolerant``: skip invalid lines with a warning instead of raising.
    Missing files return [].
    """


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """Write rows as JSONL (ensure_ascii=False), creating parent dirs."""


def read_json(path: Path) -> Any:
    """Read a JSON file (missing file -> raise FileNotFoundError as today)."""
```

Implementation notes:
- `read_jsonl`: replicate `_load_previous_state`'s tolerant loop exactly;
  when `tolerant=False`, a malformed line raises `json.JSONDecodeError` like
  today's site/publish readers.
- `write_jsonl`: replicate `_write_jsonl` exactly.
- `read_json`: delegate to `json.loads(path.read_text(encoding="utf-8"))` —
  use it only where `_load_json` (publish.py:64-65) and site's inline reads
  already exist; do NOT hunt for new call sites beyond the readers/writers
  being consolidated.
- Import style: `from __future__ import annotations` is NOT used in this
  repo (removed in 2dbf160) — do not add it. Type hints per AGENTS.md:
  `Mapping`/`Iterable` from `collections.abc`.

**Verify**: `ruff check polla_app/io.py` → exit 0.

### Step 2: Migrate `site.py` and `publish.py` to the shared reader

- `site.py`: replace `_load_ndjson` with `read_jsonl(path, dedup_key=lambda r: (r.get("sorteo"), r.get("fecha")))`; update the two call sites (`build_site_payload` lines 65-66); delete the local function.
- `publish.py`: replace `_load_normalized_ndjson` body with the same shared call (keep the function as a thin wrapper if it has callers outside — check: it is used in `publish_to_google_sheets`; prefer deleting the wrapper and calling `read_jsonl` directly, matching site.py).

**Verify**: `pytest tests/test_site.py tests/test_publish.py -q` → all pass.

### Step 3: Migrate `pipeline.py`

- Replace `_load_previous_state` body with `read_jsonl(path, tolerant=True)` — the warning message changes from the current custom one to the shared one; that's fine, but check `tests/test_pipeline.py` for assertions on the old warning text (grep `"Invalid JSON line"`); if a test asserts it, update the assertion to the new message.
- Replace `_write_jsonl` body with a call to `write_jsonl`.
- In `_persist_state` (pipeline.py:406-410), replace the inline write loop with `write_jsonl(state_path, updated)`.
- Delete the now-unused local `_write_jsonl`/`_load_previous_state` definitions only if nothing else references them (grep both names).

**Verify**: `pytest tests/test_pipeline.py -q` → all pass; `grep -n "_write_jsonl\|_load_previous_state" polla_app/pipeline.py` → only the expected references (callers or the shared import).

### Step 4: Add unit tests for the shared helpers

Create `tests/test_io.py` (model on `tests/test_contracts.py` style — plain asserts, tmp_path):

1. `test_read_jsonl_missing_file` → `[]`
2. `test_read_jsonl_dedup_by_key` — write 3 lines, 2 with same `(sorteo,fecha)`; assert 2 records, later wins
3. `test_read_jsonl_tolerant_skips_bad_lines` — one garbage line; tolerant=True → 2 records + no raise
4. `test_read_jsonl_strict_raises_on_bad_line` — tolerant=False → `json.JSONDecodeError`
5. `test_write_jsonl_roundtrip` — write 2 rows, read back with `read_jsonl`, equal
6. `test_write_jsonl_creates_parent_dirs` — nested tmp_path works

**Verify**: `pytest tests/test_io.py -q` → 6 pass.

## Test plan

- New file `tests/test_io.py` with the 6 tests above.
- Existing suites (`test_site.py`, `test_publish.py`, `test_pipeline.py`) are the regression net for the migration — they must pass unchanged (except the one warning-text assertion, if it exists).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest -q` exits 0 (all suites incl. new `test_io.py` with 6 tests)
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -rn "def _load_ndjson\|def _load_normalized_ndjson" polla_app/` → no matches
- [ ] `grep -rn "json.dumps(row" polla_app/` → no matches outside `io.py`
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- A test asserts on the old tolerant-warning log text in a way that's load-bearing for the pipeline contract — update the assertion (test-only) and note it.
- Plan 024 has landed and added a second tolerant reader in `site.py` — migrate that one too (it's in scope).
- Any consumer depends on the exact `LOGGER` name in the warning (e.g. an obs test) — keep the shared logger name `polla_app.io` consistent and update assertions.

## Maintenance notes

- `read_jsonl`'s `tolerant` flag is the single knob for the "corrupt line" behavior — future consumers (e.g. site stats, report readers) should use it deliberately.
- If the state file gains a `game` field (plan 030), the dedup key for state reads may need to become `(game, sorteo, fecha)` — the helper's `dedup_key` param makes that a one-line change at the call site.
