# Plan 038: Remove wasted work — Kino soup sanity check and double site-payload build

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/sources/kino.py polla_app/__main__.py polla_app/site.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW (behavior-preserving; one advisory log line changes)
- **Depends on**: none (if 024 has landed, the `site` command has a `--state-file` option and possibly one `build_site_payload` call — adapt Step 2 to the live structure and note it)
- **Category**: perf
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Two small pieces of wasted work:

1. `sources/kino.py:144-147` builds a full `BeautifulSoup` parse of the
   entire Kino pendón page purely to emit a warning line, after the data has
   already been extracted from `__NEXT_DATA__` (which raises on missing/
   erroring content at kino.py:79-83, 130-133). The DOM parse is the
   dominant CPU cost on the Kino path for one advisory log.
2. The `site` command builds the dashboard payload twice: once for
   `write_site_stats` (__main__.py:361-366) and once inside
   `write_site_data` (__main__.py:379-385), which calls `build_site_payload`
   again with identical arguments. Besides duplicate I/O (re-reading the
   NDJSON files), the two payloads can diverge (different `generated_at`).

## Current state

`polla_app/sources/kino.py:142-147`:

```python
    # Sanity-check the embedded HTML with BeautifulSoup only to confirm the
    # page rendered content (defensive against a stub page without data).
    soup = BeautifulSoup(metadata.html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "Kino" not in text and "kino" not in text:
        LOGGER.warning("Kino pendón page content looks unexpected (missing 'Kino' text)")
```

(with `from bs4 import BeautifulSoup` at kino.py:26)

`polla_app/__main__.py:361-385` (read the exact lines before editing — the
`site` command):

```python
    payload = build_site_payload(...)          # ~line 361
    write_site_stats(payload=payload, ...)     # ~line 366
    ...
    write_site_data(
        output=..., previous_payload=...,      # ~line 379
        ...                                     # internally calls build_site_payload again
    )
```

`polla_app/site.py:135-136` — `write_site_data` calls `build_site_payload(...)`
with the same arguments.

Test coverage to keep green: `tests/test_site.py` (CliRunner-based; the
`_invoke_site` helper monkeypatches `write_site_stats` to a no-op, so the
double build is exercised via `write_site_data`), `tests/test_kino.py`
(fixture-based Kino parsing incl. the warning path), `tests/test_health.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (kino) | `pytest tests/test_kino.py -q` | all pass |
| Tests (site) | `pytest tests/test_site.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/sources/kino.py` — replace the soup sanity check
- `polla_app/site.py` — let `write_site_data` accept a prebuilt payload
- `polla_app/__main__.py` — build once, pass it to both writers
- `tests/test_site.py`, `tests/test_kino.py` — adjust only if assertions reference the removed behavior

**Out of scope** (do NOT touch, even though they look related):
- The `stats.json`/`data.json` output shapes — unchanged
- Plan 024's history changes (state-file reading) — if landed, keep them; this plan only removes the *duplicate* build
- `tests/test_health.py` — no changes

## Git workflow

- Branch: `advisor/038-small-perf-wins`
- Commit message style: `perf(kino,site): sin soup-parse para el warning; un solo build del payload del dashboard`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Replace the soup sanity check in kino.py

Replace the block at kino.py:142-147 with a substring check on the raw
HTML (the same "Kino" text the soup was looking for):

```python
    # Advisory sanity check on the raw HTML (no full DOM parse needed).
    if "Kino" not in metadata.html and "kino" not in metadata.html:
        LOGGER.warning("Kino pendón page content looks unexpected (missing 'Kino' text)")
```

Remove the now-unused `from bs4 import BeautifulSoup` import (kino.py:26).

**Verify**: `pytest tests/test_kino.py -q` → all pass (check whether any
test asserts the warning text — if the fixture page is real, the warning
never fires; add a tiny test that the warning fires for a stub HTML without
"Kino" if it's cheap: use `caplog` with `_fetch_pozo_kino`'s internals or
skip — only if the existing tests make it natural).

### Step 2: Single payload build in the `site` command

1. In `polla_app/site.py`, change `write_site_data` to accept
   `payload: Mapping[str, Any] | None = None`; when `payload` is provided,
   skip the internal `build_site_payload` call; when `None`, fall back to
   building it (backward compatibility for any other callers — grep for
   `write_site_data(` across the repo and tests).
2. In `polla_app/__main__.py`'s `site` command, build the payload once and
   pass it to both `write_site_stats` and `write_site_data`.

**Verify**: `pytest tests/test_site.py -q` → all pass (the `_invoke_site`
helper asserts on `data.json` content — behavior identical); `grep -n
"build_site_payload" polla_app/__main__.py polla_app/site.py` → exactly one
call in `__main__.py` (the site command) plus the fallback inside
`write_site_data` and `build_site_payload`'s definition.

## Test plan

- Adjust existing tests only if they assert the removed double-build or the
  removed warning path (verify by running them first; they should pass
  unchanged).
- If plan 024 has landed and added a `state_path` parameter to
  `build_site_payload`, the `write_site_data` fallback must forward it —
  keep the signature aligned.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "BeautifulSoup" polla_app/sources/kino.py` → no matches
- [ ] `grep -n "build_site_payload" polla_app/__main__.py` → exactly 1 call site
- [ ] `pytest tests/test_kino.py tests/test_site.py -q` → all pass
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- A test asserts the warning-log path with the soup (fixture asserts on the old log) — update the fixture/test to the new check and note it.
- `write_site_data` has callers besides `__main__.py` and `tests/` that would break with the new optional param — report the callers; adding the optional param is backward compatible, so this should not happen.
- Plan 024 changed the `site` command structure such that the two-calls description no longer matches — adapt to the live structure and note it.

## Maintenance notes

- The Kino warning is now advisory on raw HTML only; the real guards are the `__NEXT_DATA__` parse errors (unchanged).
- If the dashboard adds a third writer (e.g. a drift report), it should reuse the single payload from `__main__.py` rather than rebuilding.
- This plan is a prerequisite-free cleanup; it makes plan 024's payload changes simpler when they land.
