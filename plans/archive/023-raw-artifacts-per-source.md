# Plan 023: Preserve per-source raw artifacts in aggregate (`--sources pozos`) mode

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/pipeline.py tests/`
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

In the default production mode (`run --sources pozos`, which expands to
fetching both `openloto` and `polla`), every collected payload is written to
`raw_dir / "pozos.json"` — the last source's payload silently overwrites the
first's. The `openloto` raw payload is lost on every production run, so the
forensic trail for consensus disagreements (which quote per-source `sha256`)
is destroyed. The CLI help advertises "one per source" raw outputs; the
naming branch that would do it correctly only triggers in the non-default
`--sources openloto,polla` form.

## Current state

`polla_app/pipeline.py:628-638`:

```python
    # Write raw JSON artifacts (one per source)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for entry in collected:
        # Compatibility: if it's the only source, use its name for the test
        if len(requested_sources) == 1:
            src_name = requested_sources[0]
        else:
            from urllib.parse import urlparse

            src_name = urlparse(entry.get("fuente", "")).netloc.replace(".", "_") or "source"
        _write_json(raw_dir / f"{src_name}.json", entry)
```

In `run --sources pozos`, `requested_sources == ["pozos"]` (length 1), so
both the `openloto` and `polla` entries write to `raw_dir/pozos.json`.

Each collected entry is a source payload dict with a `"fuente"` field that
holds the source URL (see `polla_app/sources/common.py` `build_pozo_payload`
and the `openloto`/`polla` fetchers). Existing test that locks current
behavior: `tests/e2e/test_verification_suite.py:47-72` asserts that in a
single-source run (`--sources openloto`), `raw_dir` contains exactly one
file named `openloto.json` — that naming must be preserved for
single-source runs.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_pipeline.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/pipeline.py` — the raw-artifact naming block (lines 628-638)
- `tests/test_pipeline.py` — new regression tests

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/sources/*.py` — no fetcher changes
- The `raw_dir`/`--raw-dir` CLI contract — unchanged
- `tests/e2e/test_verification_suite.py` — single-source naming assertion stays valid; do not edit it
- Any change to `normalized.jsonl` semantics (handled by plan 024)

## Git workflow

- Branch: `advisor/023-raw-artifacts-per-source`
- Commit message style: `fix(pipeline): conservar un raw por fuente en modo agregado`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Name raw files by source identity, not run mode

Replace the loop body in `polla_app/pipeline.py:630-638` so the filename is
derived from the entry itself, while keeping single-source runs producing
`{source}.json` exactly as today. Suggested implementation:

```python
    # Write raw JSON artifacts (one per source): the source URL's netloc
    # identifies the source regardless of requested-sources mode, so the
    # aggregate mode ("pozos") no longer overwrites openloto with polla.
    raw_dir.mkdir(parents=True, exist_ok=True)
    from urllib.parse import urlparse

    for entry in collected:
        if len(requested_sources) == 1:
            # Compatibility: single-source runs keep the requested name
            src_name = requested_sources[0]
        else:
            src_name = urlparse(entry.get("fuente", "")).netloc.replace(".", "_") or "source"
        _write_json(raw_dir / f"{src_name}.json", entry)
```

(This keeps the single-source branch identical and only moves the
`urlparse` import out of the loop — the fix is in the branch condition,
which already derives the name per entry. Verify the behavior below; if the
aggregate entries both carry the same `fuente` netloc, then the names would
still collide — check what `entry["fuente"]` actually is for each fetcher
before finalizing: `grep -n '"fuente"' polla_app/sources/pozos.py` and
`polla_app/sources/common.py`.)

If — and only if — the two sources share the same `fuente` netloc, fall back
to a deterministic mapping: derive the name from the payload's `sha256`
prefix or from a per-source marker (`requested_sources` order aligned with
`collected`), e.g. `raw_dir / f"{requested_sources[0]}_{index}.json"`.
Do not improvise beyond these two options; report which one you used and
why.

**Verify**: `pytest tests/test_pipeline.py -q` → all pass.

### Step 2: Add aggregate-mode regression tests

In `tests/test_pipeline.py`, add a test that runs the pipeline with
`--sources pozos` semantics at the function level. Look at how existing
tests invoke `run_pipeline` (search `def run_pipeline` in the test file and
reuse the argument pattern, including stubbed `SOURCE_LOADERS` fetchers —
the pattern at `tests/test_e2e.py:39` uses `monkeypatch.setitem(pipeline.SOURCE_LOADERS, ...)`).

Test 1 — `test_raw_artifacts_preserved_in_aggregate_mode`: two fake
fetchers with distinct `fuente` URLs registered under `openloto` and
`polla`; call `run_pipeline(sources=["pozos"], ...)` with a fresh `raw_dir`;
assert `sorted(f.name for f in raw_dir.glob("*.json"))` contains both
source-specific names and NOT `pozos.json` (names depend on the netlocs used
in the stubs — assert on the two netloc-derived names).

Test 2 — `test_raw_artifact_single_source_name`: keep one fetcher
registered, `run_pipeline(sources=["openloto"], ...)`; assert exactly one
file named `openloto.json` exists (this mirrors the e2e assertion and pins
the compatibility branch).

**Verify**: `pytest tests/test_pipeline.py -q` → new tests pass alongside
existing ones (existing suite: 906-line file, expect ~60+ tests).

## Test plan

- New tests: the two above in `tests/test_pipeline.py`.
- Structural pattern: existing `run_pipeline` invocations in the same file;
  fetcher stubs like `tests/test_e2e.py:39`.
- Verification: `pytest tests/test_pipeline.py -q` all pass; full `pytest -q` green.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_pipeline.py -q` exits 0 with the two new tests present (`grep -c "test_raw_artifact" tests/test_pipeline.py` >= 2)
- [ ] `pytest -q` exits 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] Manual: `git diff` of the changed block shows no change to the single-source branch behavior
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The `fuente` values of the two fetchers are identical, making netloc-derived names collide and the fallback ambiguous — report rather than inventing a third naming scheme.
- An existing test asserts the old aggregate behavior (file `pozos.json` exists in aggregate mode) — then the plan's premise is wrong; report.
- The code at the locations in "Current state" doesn't match the excerpts.

## Maintenance notes

- `scrape.yml` uploads `artifacts/raw/` (via the `artifacts/` glob) — after this change, raw dirs in stored artifacts will contain two files instead of one; no consumer parses raw files today (they are forensic), so this is safe.
- If a future plan changes the `fuente` field format, this naming logic must be revisited (the fallback branch is the place to look).
