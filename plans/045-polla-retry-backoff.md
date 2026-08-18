# Plan 045: Add exponential backoff to get_pozo_polla's retry loop

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

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (run after 044 — both touch pozos.py)
- **Category**: bug
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

`get_pozo_polla` has its own retry loop (pozos.py:316-342) that retries
back-to-back with **no delay between attempts** — unlike `net.py`, whose
`fetch_html` uses jittered exponential backoff (`_calculate_backoff`,
net.py:74-82, configurable via `POLLA_BACKOFF_FACTOR`). When polla.cl is
flaky or rate-limiting, the browser retries hammer it with three immediate
requests, defeating the politeness the rest of the pipeline implements, and
failing faster than a backoff would on a transient outage. This is the
third retry implementation in the codebase (net.py's fetch loop and
prices.py's browser fallback being the others) and the only one without
backoff.

## Current state

`polla_app/sources/pozos.py:316-342` (inside `get_pozo_polla`):

```python
        last_exc: Exception | None = None
        max_attempts = retries if retries is not None else 1
        for attempt in range(1, max_attempts + 1):
            try:
                page = fetcher.fetch(url, page_action=click_detalle, timeout=timeout)
                if page.status == 200:
                    break
                LOGGER.warning(
                    "polla.cl fetch failed (attempt %d/%d): status %d",
                    attempt,
                    max_attempts,
                    page.status,
                )
            except Exception as exc:
                last_exc = exc
                if attempt == max_attempts:
                    raise ParseError(
                        f"polla.cl fetch failed after {max_attempts} attempts"
                    ) from exc
                LOGGER.warning(
                    "polla.cl fetch error (attempt %d/%d): %s", attempt, max_attempts, exc
                )
        else:
            status_code = getattr(page, "status", 0) if "page" in locals() else 0
            raise ParseError(
                f"polla.cl fetch failed with status {status_code} after {max_attempts} attempts"
            )
```

Note the `else` on the `for` loop fires when the loop completes without
`break` (all attempts returned non-200); the non-200 branch currently does
NOT raise inside the loop, it just logs and continues — so a run of
non-200s reaches the `else` and raises. The `except` branch raises only on
the last attempt.

`net.py:74-82` — `_calculate_backoff(attempt, factor, max_seconds)` and the
backoff application in `fetch_html` (read it before mirroring). Backoff
uses `POLLA_BACKOFF_FACTOR` (default `30.0`) and caps at 300s.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_pozo_polla.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/sources/pozos.py` — the retry loop in `get_pozo_polla`
- `tests/test_pozo_polla.py` — a backoff-behavior test if the current test
  fixtures make it feasible (read the file first; if the fetcher is mocked
  such that timing can't be observed, add a lighter test that the loop
  sleeps between attempts — see Step 2)

**Out of scope** (do NOT touch, even though they look related):
- `net.py` — its backoff is correct; do not refactor it
- The `POLLA_BACKOFF_FACTOR` default or env semantics (plan 025 documents them; do not change the value)
- Reusing `fetch_html` for polla.cl (different fetch mechanism — StealthyFetcher with a page action; out of scope)

## Git workflow

- Branch: `advisor/045-polla-retry-backoff`
- Commit message style: `fix(sources): backoff exponencial en el reintento de polla.cl`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add backoff between attempts

In `get_pozo_polla`'s retry loop, before each non-first attempt (both the
non-200-continue branch and the exception branch), sleep with exponential
backoff. Mirror `net.py`'s behavior minimally:

```python
        import time

        max_attempts = retries if retries is not None else 1
        backoff_factor = float(os.getenv("POLLA_BACKOFF_FACTOR", "30.0"))
        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                delay = min(backoff_factor * 2 ** (attempt - 2), 300.0)
                LOGGER.info("polla.cl retry %d/%d in %.1fs", attempt, max_attempts, delay)
                time.sleep(delay)
            try:
                ...
```

Check whether `os` and `time` are already imported in pozos.py (top of
file) — `os` is imported for `POLLA_USER_AGENT` handling (`_effective_ua`,
pozos.py:230); `time` likely not — add `import time` (module-level, not
inside the function, per repo convention of top-level imports).

Apply the sleep before BOTH the non-200 continue path and the exception
path (they share the top of the loop, so the single `if attempt > 1:` block
covers both).

**Verify**: `pytest tests/test_pozo_polla.py -q` → all pass (existing tests
likely use `retries=1` or small; if a test uses retries>1 with the real
30s backoff it would be slow — check the file for how retries are passed and
set `POLLA_BACKOFF_FACTOR` in tests if needed, but only test-side).

### Step 2: Add a backoff test (if the fixtures allow)

Read `tests/test_pozo_polla.py` to see how the fetch is mocked. If the
fetcher is mockable and `retries` is passable, add:

1. `test_retry_sleeps_between_attempts` — mock the fetcher to fail N-1
   times then succeed; monkeypatch `time.sleep` to a recorder
   (`monkeypatch.setattr("polla_app.sources.pozos.time.sleep", recorder)`);
   set `POLLA_BACKOFF_FACTOR` to a tiny value via monkeypatch env; assert
   `len(recorder) == N-1` and each recorded delay is monotonic increasing.

If the current test file has no feasible seam (e.g. no mocked fetcher),
report that and keep the change covered by the full-suite regression tests
instead — do not invent a brittle test.

**Verify**: `pytest tests/test_pozo_polla.py -q` → all pass.

## Test plan

- New test per Step 2 if feasible; otherwise existing `tests/test_pozo_polla.py` + full suite are the regression net.
- The behavioral change is timing-only; no output change.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest -q` exits 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -n "time.sleep\|backoff_factor\|2 \*\* " polla_app/sources/pozos.py` → the backoff lines present
- [ ] `grep -n "^import time" polla_app/sources/pozos.py` → module-level import present (not a local import)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- A test asserts on the exact number/absence of sleep calls and you can't satisfy it without changing assertions that document intentional behavior — report the test.
- The retry loop structure differs from the excerpt (read it first) — adapt and note.
- `POLLA_BACKOFF_FACTOR` env is already read in pozos.py — reuse it; report if the read location differs.

## Maintenance notes

- This makes all three fetch paths back off consistently (net.py, prices.py browser fallback, polla.cl). If `POLLA_BACKOFF_FACTOR` semantics change (plan 025 only documents, does not change), revisit the hardcoded `300.0` cap here to mirror net.py's `max_seconds` behavior.
- Plan 044 touches pozos.py's `get_pozo_polla` return envelope — run 044 first or adapt line numbers; the retry loop is above the return, no overlap.
- If a future plan extracts a shared retry helper, this loop (and net.py's) should converge on it.