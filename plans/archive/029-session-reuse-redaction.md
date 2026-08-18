# Plan 029: Reuse one HTTP session per run and redact URL userinfo in logs

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/net.py polla_app/obs.py polla_app/sources/browser.py tests/test_hardening_net.py tests/test_phase3_hardening.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (connection-lifecycle + log-text changes; response handling preserved)
- **Depends on**: none
- **Category**: perf (session) + security (redaction)
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Two independent problems in the HTTP layer:

1. `fetch_html` creates a fresh `requests.Session()` per call (net.py:113)
   and never closes it; on `raise_for_status()` failure the response is
   abandoned without `close()`. A run makes 4-6 plain fetches, each paying a
   new TCP+TLS handshake, and failed/retried requests leak connections —
   contradicting AGENTS.md's "Reuse `requests.Session()` where possible".
2. `obs._redact_url_query` (obs.py:58-82) rebuilds URLs keeping
   `parts.netloc` unchanged, so `https://user:pass@host/...` userinfo
   credentials pass through logs unredacted. `net.py` logs the raw `url` at
   INFO on every retry/backoff (net.py:182-206) and `browser.py:53-58` logs
   raw URLs on browser fallback — an operator configuring keyed URLs via
   `ALT_SOURCE_URLS`/`--source-url` (a documented feature) would leak the
   key into CI logs and consoles.

## Current state

`polla_app/net.py:113`:

```python
    session = requests.Session()
```

…and `_request()` (net.py:153-159) returns `response`; the retry loop at
net.py:166-181 does `raise_for_status()`-driven retries and `finally`
branches; `session` and the final `response` are never closed anywhere in
the function.

`polla_app/obs.py:58-82` — `_redact_url_query` masks sensitive *query
params* but reconstructs with the untouched `parts.netloc`.

`polla_app/sources/browser.py:53-58` — logs `url` on fallback (verify exact
lines before editing).

The existing redaction tests that must keep passing:
`tests/test_phase3_hardening.py:25-40` (query-param redaction) and the
`sanitize` URL tests — they assert `url`/`fuente` values are preserved for
plain URLs; extending userinfo masking does not change those.

The session-stub pattern in `tests/test_hardening_net.py` (lines 21-33)
monkeypatches `polla_app.net.requests.Session` with a fake class returning
a `get` — **if the session becomes module-level, this pattern changes**:
the fake must be installed before the first use, or the module-level
session must be reset in tests. See Step 1 note.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (net) | `pytest tests/test_hardening_net.py -q` | all pass |
| Tests (obs) | `pytest tests/test_phase3_hardening.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/net.py` — shared session + close handling; route retry/backoff URL logging through redaction
- `polla_app/obs.py` — userinfo masking in `_redact_url_query`
- `polla_app/sources/browser.py` — redact logged URL on fallback
- `tests/test_hardening_net.py`, `tests/test_phase3_hardening.py` — adjust/extend tests

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/__main__.py` — no CLI changes
- The rate limiter's function-object state (plan 026 tests it; don't refactor it here)
- The browser fallback bypassing the rate limiter (politeness; separate concern, noted in the index)

## Git workflow

- Branch: `advisor/029-session-reuse-redaction`
- Commit message style: `perf(net): sesión HTTP compartida; security(obs): redactar userinfo de URLs`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Shared session in `net.py`

Add a module-level session:

```python
# One session per process: reuses connection pools across fetches within a run.
_SESSION = requests.Session()
```

In `fetch_html`, replace `session = requests.Session()` with use of
`_SESSION`. Close semantics: add a `try/finally` so that on the failure
paths the last `response` is closed before the next retry attempt; on
success return the response to the caller (callers currently don't close
it — add a `response.close()` in the `finally` only for the non-returned
paths; for the returned response, add a `response.close()` in the pipeline
consumers is out of scope — instead, ensure the retry loop closes
intermediate responses and leave the final response to be garbage
collected like today, OR return and document. Choose the minimal safe
option: close intermediate retry responses; keep the final response
lifecycle unchanged (it is consumed synchronously by callers and goes out
of scope).

**Test impact**: `tests/test_hardening_net.py` monkeypatches
`polla_app.net.requests.Session` — with a module-level `_SESSION` created at
import time, that patch no longer intercepts. Fix: in the test file, patch
`polla_app.net._SESSION` with a fake session object exposing `.get`
(adjust the existing `_fail_once`-based tests minimally), or expose a
small helper `fetch_html(..., _session=...)` — **prefer patching
`polla_app.net._SESSION` in a fixture** so the existing test bodies stay
readable. Add a module-level `autouse` fixture in the test file that
restores `_SESSION` after each test.

**Verify**: `pytest tests/test_hardening_net.py -q` → all pass (existing
retry tests unchanged in behavior).

### Step 2: Close intermediate responses in the retry loop

Locate the retry loop (net.py:166-181). On each failed attempt, before the
next `_request()`, call `response.close()` on the failed response. Read the
current loop first; the exact placement depends on how the loop is
structured (it currently catches `requests.HTTPError`/`RequestException`).
Keep the successful response returned to the caller.

**Verify**: `pytest tests/test_hardening_net.py -q` → all pass.

### Step 3: Mask userinfo in `_redact_url_query` (obs.py)

In `obs.py`, before `urlunsplit`, mask credentials:

```python
        if parts.username or parts.password:
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            netloc = f"{host}"
        else:
            netloc = parts.netloc
```

…and pass `netloc` to `urlunsplit` instead of `parts.netloc`. (Simplest
safe form: rebuild netloc as `hostname[:port]`, dropping userinfo entirely
— never include any part of it.)

**Verify**: `pytest tests/test_phase3_hardening.py -q` → all pass; add to
the same file (or the obs test):

```python
def test_sanitize_redacts_url_userinfo() -> None:
    payload = {"url": "https://user:supersecret@api.example.test/feed?token=abc&x=1"}
    cleaned = sanitize(payload)
    assert "supersecret" not in cleaned["url"]
    assert "user" not in cleaned["url"]
    assert "api.example.test/feed?token=<redacted>&x=1" in cleaned["url"]
```

### Step 4: Redact logged URLs in net.py and browser.py

- In `net.py` retry/backoff logging (lines ~182-206), pass the URL through
  the redaction: import `sanitize` from `.obs` (check for circular imports:
  obs.py imports `redact` from exceptions.py; net.py importing obs.py is
  fine — obs has no net dependency) and log
  `sanitize({"url": url})["url"]` — or simpler, log the redacted string via
  a tiny local helper `_redact_url = lambda u: sanitize({"url": u})["url"]`
  — pick the clearer option.
- In `browser.py:53-58`, do the same for the fallback-warning log line.

**Verify**: `grep -n "url" polla_app/net.py | head` shows logging lines
using the redacted value; run a manual check:
`python -c "from polla_app.obs import sanitize; print(sanitize({'url':'https://u:p@h.test/?token=t'})['url'])"` → no `p`, no `t` after `token=`.

## Test plan

- Extend `tests/test_phase3_hardening.py` with the userinfo test (Step 3).
- Adapt `tests/test_hardening_net.py` session patching (Step 1) — the
  existing retry/backoff tests must pass with the module-level session.
- Optionally add `test_fetch_html_closes_response_on_retry` asserting the
  failed response's `close()` is called (add `close` to the fake response
  recording calls) — do this only if the current fake makes it trivial.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest -q` exits 0 (incl. adapted net tests and new userinfo test)
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -n "requests.Session()" polla_app/net.py` → no matches (module-level `_SESSION` instead)
- [ ] `python -c "from polla_app.obs import sanitize; print(sanitize({'url':'https://user:pass@h.test/?token=abc'})['url'])"` → output contains no `user`, `pass`, or `abc`
- [ ] `pytest tests/test_hardening_net.py -q` passes with the adapted patching
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `obs.py` cannot be imported from `net.py` without a circular import (check import graph first; report if it loops).
- The module-level session breaks a test in a way that requires changing test *assertions* (not just patching) — report instead.
- `browser.py` logging lines differ from the excerpt (lines 53-58) — adapt to the actual lines and note it.

## Maintenance notes

- The module-level `_SESSION` lives for the process lifetime (CLI runs are short-lived); `health --online` benefits directly.
- When plan 026 lands its rate-limiter tests, they will interact with the session patch in `test_hardening_net.py` — keep the autouse-restore fixture.
- If a future refactor moves the limiter or session into a shared `net` object, both this plan's session and plan 026's tests move with it.
