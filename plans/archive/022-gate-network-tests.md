# Plan 022: Gate live-network tests out of the default `pytest` suite

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- pyproject.toml tests/e2e tests/test_health.py .github/workflows/tests.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/021-cli-hermetic-tests.md (coverage replacement)
- **Category**: tests
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The default test suite performs live scraping of third-party sites:
`tests/e2e/test_verification_suite.py:47-83` runs
`python3 -m polla_app run --sources openloto` (real fetch of openloto.cl with
retries and 30s backoff), `:98-142` fetches a fake domain plus real polla.cl,
and `tests/test_health.py:44-57` makes a real fetch of the Kino pendón whose
result is never even asserted. AGENTS.md is explicit: "Never add network
calls to tests" and "Tests must be deterministic". Consequences: CI and local
runs are nondeterministic, can hang for minutes on upstream slowness, and can
get the repo's CI IPs rate-limited/banned by the very sources the project
scrapes. This plan gates them behind an opt-in marker.

**Coverage dependency**: `tests.yml` runs `pytest tests -v --cov=polla_app --cov-report=xml --cov-fail-under=80`. Excluding the e2e tests removes live code paths from the coverage measurement — plan 021's hermetic CLI tests (which cover the same `run`/`publish`/`kino` code) must land first, or the gate may fail.

## Current state

- `pyproject.toml:30-32`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  addopts = "-q"
  ```
  No `markers` section, no `-m` filter.
- `tests/e2e/test_verification_suite.py` — 6 tests: `test_cli_help`,
  `test_source_isolation` (live openloto fetch), `test_redaction_correctness`
  (pure, no network), `test_degraded_mode` (fake domain + live polla),
  plus ~2 more below line 100 that shell out with real fetches. The
  subprocess helper is `run_cli` (lines 9-15). Only the live-fetch tests
  need the marker.
- `tests/test_health.py:44-57` — `test_health_online_degraded` stubs
  openloto/polla but leaves `get_pozo_kino` live.
- `.github/workflows/tests.yml` runs `pytest tests -v --cov=polla_app --cov-report=xml --cov-fail-under=80` — with `addopts = "-q"` already, the CI command will inherit the new marker exclusion automatically (pytest merges addopts).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Default suite (excludes network) | `pytest -q` | all pass, 0 skipped-network tests run |
| Opt-in network suite | `pytest -q -m network` | the marked tests run (may fail if sites are down — that is expected) |
| Lint | `ruff check polla_app tests` | exit 0 |
| Coverage check | `pytest --cov=polla_app --cov-fail-under=80 tests -q` | coverage >= 80% (must hold after plan 021) |

## Scope

**In scope** (the only files you should modify):
- `pyproject.toml` — add `markers` and `addopts = "-q -m \"not network\""`
- `tests/e2e/test_verification_suite.py` — add `@pytest.mark.network` to the live-fetch tests
- `tests/test_health.py` — add `@pytest.mark.network` to `test_health_online_degraded` (and fix the unasserted live fetch only if a stub already exists — otherwise just mark it)

**Out of scope** (do NOT touch, even though they look related):
- Deleting or rewriting the e2e tests (plan 021 provides the hermetic replacements; keep the network suite as an opt-in smoke test)
- `.github/workflows/*.yml` — the CI command inherits the exclusion; no workflow edit needed. (Adding a scheduled network job is a follow-up, not part of this plan.)
- `tests/e2e/__init__.py` creation — check whether `tests/e2e/` has one; if not, leave as is.

## Git workflow

- Branch: `advisor/022-gate-network-tests`
- Commit message style: `test(ci): excluir pruebas de red por defecto (marcador network)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Register the marker and exclude by default

In `pyproject.toml`, under `[tool.pytest.ini_options]`:

```toml
addopts = "-q -m \"not network\""
markers = [
    "network: tests that hit live third-party sites (opt-in with -m network)",
]
```

**Verify**: `pytest --markers | grep -A1 "network"` → shows the marker
description; `pytest -q` → no `PytestUnknownMarkWarning` in output.

### Step 2: Mark the live-fetch e2e tests

In `tests/e2e/test_verification_suite.py`, add `@pytest.mark.network` above
every test that performs a real fetch: `test_source_isolation` (line 47,
`run --sources openloto`), `test_degraded_mode` (line 98), and any other
subprocess tests below that invoke `run` without a stubbed URL
(check lines 100-180 for further `run_cli` calls with real sources — mark
any whose args include `--sources openloto`, `--sources polla`, or
`--source-url` pointing at a live domain; leave `test_cli_help` and
`test_redaction_correctness` unmarked since they are hermetic).

**Verify**: `pytest tests/e2e -q` → the unmarked tests run (2 pass), the
marked ones are deselected (shown as deselected with `-q` silent — run
`pytest tests/e2e -q -rs` and confirm "deselected" count == number of marked).

### Step 3: Mark the health online test

In `tests/test_health.py`, add `@pytest.mark.network` to
`test_health_online_degraded` (the one that leaves `get_pozo_kino` live).

**Verify**: `pytest tests/test_health.py -q` → passes with the live test
deselected.

### Step 4: Verify the coverage gate still holds

**Verify**: `pytest --cov=polla_app --cov-fail-under=80 tests -q` → exits 0.
If it fails, the replacement coverage from plan 021 is missing — report back
(do not lower the threshold; it is a deliberate CI gate).

## Test plan

- No new tests in this plan; it reclassifies existing ones.
- Verification is the suite behavior change: default run green without
  network, `-m network` opt-in runs them.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest -q` exits 0 and completes without any network access (`grep` the test file to confirm the marked set; optionally run with `-m network` separately)
- [ ] `pytest --cov=polla_app --cov-fail-under=80 tests -q` exits 0
- [ ] `pytest -q -m network tests/e2e tests/test_health.py` executes the marked tests (they may fail on a bad network day — that is expected and documented)
- [ ] `ruff check polla_app tests` and `mypy polla_app tests` exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Plan 021 has not landed and the coverage gate fails — do not weaken the gate.
- A test you marked turns out to be hermetic (network-free) — unmark it and note it.
- The full suite still makes network calls after this plan (check for other `requests.get`/`urlopen`/subprocess calls in tests) — report the locations.

## Maintenance notes

- The `-m network` suite is the manual smoke test for source drift; consider a scheduled CI job running it later (follow-up, out of scope).
- When new tests are written, the repo rule is: hermetic by default, `@pytest.mark.network` only for explicit opt-in smoke tests.
- If `tests.yml` ever needs the network suite, run `pytest tests -m network` explicitly in a separate job with `continue-on-error: true`.
