# Plan 026: Close five small test gaps on money-adjacent guards

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/net.py polla_app/pipeline.py polla_app/sources/prices.py polla_app/notifiers.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (test-only plan; zero production code changes)
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Five decision-path guards that protect money-adjacent outputs (published
amounts, dashboard prices, Slack noise, retry politeness) have zero test
coverage. A regression in any of them would ship with green CI: the rate
limiter (`POLLA_RATE_LIMIT_RPS`) with its function-object state, the
SHA-256 dedup short-circuit that can skip a *changed* draw or re-publish an
*unchanged* one, the 429/502/504 retry statuses (the exact reason 5XX retry
was added in commit 462217f), the Loto price monotonicity guard, and the
Slack skip-when-unchanged branch.

## Current state

1. **Rate limiter** — `polla_app/net.py:129-151`: `_rate_limit_if_needed`
   sleeps `min_interval - delta` per host, keyed by `urlparse(url).netloc`,
   state stored on the function object (`fetch_html._last_seen`). Zero
   references to `RATE_LIMIT` in tests.
2. **SHA-256 dedup** — `polla_app/pipeline.py:429-431`: `_compute_unchanged`
   returns `True` early when `curr_sha == prev_sha`. State files in tests
   are hand-written without `provenance`, so this branch never executes.
3. **Retry matrix** — `polla_app/net.py:92`: `_RETRYABLE_STATUS = (429, 500, 502, 503, 504)`.
   `tests/test_hardening_net.py:78-142` covers 500/503/404/Timeout/ConnectionError only.
   The 429 path is special: `net.py:156-157` raises `requests.HTTPError("Too Many Requests", response=response)` with the response attached, and the retry branch reads it (net.py:174-179).
4. **Loto price monotonicity** — `polla_app/sources/prices.py:124-129`:
   `_extract_prices` raises `ParseError` when a derived delta is `<= 0`.
5. **Slack skip branch** — `polla_app/notifiers.py:28-30`:
   ```python
   if status == "skip" and not summary.get("prizes_changed"):
       return
   ```

Test patterns to reuse: `tests/test_hardening_net.py` `_fail_once` helper
(lines 12-24) + `monkeypatch.setattr("polla_app.net.requests.Session", ...)`
and `monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")` to keep backoff
fast; `tests/test_pipeline.py` for state-file based `_compute_unchanged`
tests; `tests/test_prices.py:30-69` for `_extract_prices` tests;
`tests/test_phase4.py:47-68` for `notify_slack` tests (uses
`requests.post` mocking).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_hardening_net.py tests/test_pipeline.py tests/test_prices.py tests/test_phase4.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `tests/test_hardening_net.py` — rate limiter + retry matrix tests
- `tests/test_pipeline.py` — SHA dedup tests
- `tests/test_prices.py` — monotonicity test
- `tests/test_phase4.py` — Slack skip-branch tests

**Out of scope** (do NOT touch, even though they look related):
- Any production code — this plan is test-only. If a test exposes a real bug, report it and stop that step (do not fix production code here; that becomes a new plan).
- The e2e suite and network tests (plans 021/022).

## Git workflow

- Branch: `advisor/026-small-test-gaps`
- Commit message style: `test: cubrir rate limiter, dedup SHA, reintentos 429/502/504, monotonicidad y skip de Slack`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Rate limiter tests (test_hardening_net.py)

Add to `tests/test_hardening_net.py`:

1. `test_rate_limit_spaces_same_host` — `monkeypatch.setenv("POLLA_RATE_LIMIT_RPS", "2")`; fake `time.sleep` via `monkeypatch.setattr("polla_app.net.time.sleep", recorder)`; call `fetch_html("https://a.test/1", ...)` then `fetch_html("https://a.test/2", ...)` with the same robots-stub + Session stub as existing tests; assert `len(recorded_sleeps) == 1` and `recorded_sleeps[0] >= 0.5 - 0.01` (1/2 rps = 0.5s minimum gap).
2. `test_rate_limit_does_not_space_different_hosts` — same setup, URLs `https://a.test/` and `https://b.test/` → `recorded_sleeps == []`.
3. `test_rate_limit_ignores_invalid_env` — `monkeypatch.setenv("POLLA_RATE_LIMIT_RPS", "abc")` → no sleep recorded (invalid value ignored per net.py:137-139).
4. `test_rate_limit_state_reset_between_tests` — if feasible, assert `fetch_html._last_seen` is a dict (cleanup concern); at minimum ensure the monkeypatched `time.sleep` recorder is restored (monkeypatch handles it).

**Verify**: `pytest tests/test_hardening_net.py -q` → all pass including 3 new.

### Step 2: SHA-256 dedup tests (test_pipeline.py)

Add:

1. `test_compute_unchanged_matches_on_sha` — build a record with
   `provenance.pozos.primary.sha256 = "abc"` and a previous state list
   containing a record with the same sorteo/fecha and the same sha
   (but *different* amounts, to prove the SHA path short-circuits):
   assert `_compute_unchanged(prev, sorteo=..., fecha=..., current_record=...) is True`.
2. `test_compute_unchanged_falls_back_to_amounts_when_sha_differs` — same
   sorteo/fecha, different sha, identical amounts → True; different sha and
   different amounts → False.
3. `test_run_pipeline_skips_unchanged_draw` (optional but valuable) —
   run `run_pipeline` twice with identical stubbed fetcher payloads against
   the same `state_path`/`normalized_path`; assert the second run's summary
   has `"publish"` false / decision status `"skip"`. Follow the existing
   `run_pipeline` invocation pattern in test_pipeline.py (stub
   `SOURCE_LOADERS` and `_attach_prices`).

**Verify**: `pytest tests/test_pipeline.py -q` → all pass including the new tests.

### Step 3: Retry matrix tests (test_hardening_net.py)

Parameterize the existing `_fail_once` pattern over the missing statuses:

1. `test_fetch_html_retries_on_429` — `_fail_once` raising
   `requests.HTTPError("Too Many Requests", response=<resp with status 429>)`
   once, then success; with `POLLA_BACKOFF_FACTOR=0.001` and `retries=2`;
   assert result html returned (mimic the existing timeout test, including
   the `monkeypatch.setattr("polla_app.net.requests.Session", ...)` stub).
2. Same for 502 and 504 (can be a `@pytest.mark.parametrize("status", [429, 502, 504])` with the exception constructed per status: for 429 build the HTTPError-with-response; for 502/504 use a plain `requests.HTTPError` after a status-bearing response or a fake response with `raise_for_status` that raises HTTPError — look at how the existing 500/503 tests construct the failure and mirror exactly).

**Verify**: `pytest tests/test_hardening_net.py -q` → 429/502/504 cases pass.

### Step 4: Loto price monotonicity test (test_prices.py)

Add `test_extract_prices_rejects_non_monotonic` — feed `_extract_prices`
text whose cumulative prices decrease (e.g. the standard block but with a
later value lower than an earlier one, such as `Loto $1.000`, `Loto + Recargado $1.500`, `Loto + Revancha $1.200` — check `_CUMULATIVE_RE` requires `$` before the number and that values pass the `<= 10_000` filter); assert `pytest.raises(ParseError)` and `"not monotonic"` in the message. Build the input by copying the fixture page structure from `tests/fixtures/sources/prices/` if that helps.

**Verify**: `pytest tests/test_prices.py -q` → all pass including the new test.

### Step 5: Slack skip-branch tests (test_phase4.py)

Add:

1. `test_notify_slack_skips_unchanged_without_request` — set
   `SLACK_WEBHOOK_URL` env; mock `requests.post` with a recorder
   (follow the existing mocking pattern in test_phase4.py); call
   `notify_slack({"decision": {"status": "skip"}, "prizes_changed": False}, webhook=...)` (match the real signature — read notifiers.py first); assert the recorder was never called.
2. `test_notify_slack_posts_when_skip_but_prizes_changed` — same but
   `prizes_changed: True` → recorder called once.

**Verify**: `pytest tests/test_phase4.py -q` → all pass including the 2 new.

## Test plan

- New tests: 3-4 (Step 1) + 2-3 (Step 2) + 1-3 parametrized (Step 3) + 1 (Step 4) + 2 (Step 5). Exact counts depend on how you parametrize; report the totals.
- Patterns: existing tests in each target file, cited above.
- Verification: targeted files pass, then full `pytest -q` green.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest tests/test_hardening_net.py tests/test_pipeline.py tests/test_prices.py tests/test_phase4.py -q` exits 0
- [ ] `pytest -q` exits 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -n "RATE_LIMIT" tests/test_hardening_net.py` shows the new env usage
- [ ] `grep -n "429\|502\|504" tests/test_hardening_net.py` shows the new cases
- [ ] `grep -n "prizes_changed" tests/test_phase4.py` shows the new tests
- [ ] No production files modified (`git status` — only the four test files)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any new test fails against current production code (a real bug) — do not fix production here; report the failing behavior as a new finding.
- The `notify_slack` signature differs from what test_phase4.py shows — read notifiers.py first and adapt the test to the real signature.
- Plan 029 (shared session) has already landed and changed the net.py Session mocking pattern — mirror the updated pattern instead.

## Maintenance notes

- The rate limiter tests pin the function-object state design; if a future refactor moves the limiter into a class, these tests should move with it.
- `_compute_unchanged` tests interact with plan 030 (state file per game) if that plan adds a `game` key to records — the dedup tests use explicit sorteo/fecha, so they stay valid.
- The Slack skip tests are the only guard against notification spam regressions; keep them whenever `notify_slack`'s decision handling changes.
