# Plan 021: Add hermetic CLI tests for the `run`, `publish`, and `kino` commands

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/__main__.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The three most important CLI commands — `run`, `publish`, `kino` — have zero
hermetic tests. The only invocations of `run` live in `tests/e2e/`
(subprocess calls that hit real network; see plan 022), and `publish`/`kino`
are invoked nowhere in tests. `__main__.py` is a top-7 churn file
(7 commits/60). The recent `site --previous-data` regression (fixed at
`5287c5e`/`f5baf2b`) shows option-plumbing bugs slip through. These tests
also make plan 022 (gating live-network e2e tests) safe, because coverage
of the CLI code paths must not drop below the 80% gate in `tests.yml`.

## Current state

`tests/e2e/test_verification_suite.py:9-15` is the only CLI runner pattern in
the repo that touches `run`/`publish`:

```python
def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-m", "polla_app"] + args,
        capture_output=True,
        text=True,
        check=False,
    )
```

The hermetic pattern already used elsewhere is Click's `CliRunner` with
monkeypatched internals — see `tests/test_site.py:14-24`:

```python
def _invoke_site(tmp_path, monkeypatch, args):
    from polla_app import __main__ as main_mod
    monkeypatch.setattr(main_mod, "write_site_stats", lambda *a, **k: None)
    result = CliRunner().invoke(cli, ["site", *args])
    assert result.exit_code == 0, result.output
    return (tmp_path / "data.json").read_text(encoding="utf-8")
```

And the fetch-stubbing pattern (used by `tests/test_e2e.py:39` and others)
is `monkeypatch.setitem(pipeline.SOURCE_LOADERS, "openloto", fake_fetcher)`.

Key CLI surface under test (`polla_app/__main__.py`):
- `run` command (`__main__.py:159-234`): validates `--retries >= 1`,
  `--timeout >= 1`, `--mismatch-threshold >= 0` (click.BadParameter);
  parses `ALT_SOURCE_URLS` env JSON (BadParameter on invalid JSON);
  parses `--source-url key=value` pairs (BadParameter on missing `=` or
  empty key/value); calls `run_pipeline(...)` then `_echo_json(summary)`.
- `publish` command (`__main__.py:275-310`): `--normalized` and
  `--comparison-report` are `required=True`; loads optional `--summary`
  JSON (FileNotFoundError → proceeds); calls `publish_to_google_sheets(...)`,
  then `_echo_json(result)`; prints `result["diff"]` when `--dry-run`.
- `kino` command (`__main__.py:72-82`): calls `get_pozo_kino(...)` inside a
  try/except that emits `{"error": ...}` JSON on failure.

`tests/test_contracts.py` and `tests/test_cli_hardening.py` are the places
where dry-run `publish` behavior is already asserted at the function level
(`publish_to_google_sheets` with dry_run=True) — do not duplicate that;
test the CLI layer's option plumbing and error shape instead.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (new file) | `pytest tests/test_cli_commands.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |
| Format | `black --check polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `tests/test_cli_commands.py` (create — new test file)

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/__main__.py`, `polla_app/pipeline.py`, `polla_app/publish.py` — no production changes
- `tests/e2e/test_verification_suite.py` — handled by plan 022
- `tests/test_cli_hardening.py`, `tests/test_publish.py` — existing function-level tests; do not edit

## Git workflow

- Branch: `advisor/021-cli-hermetic-tests`
- Commit message style: `test(cli): cubrir run/publish/kino con CliRunner hermético`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create `tests/test_cli_commands.py` — `run` command tests

Model imports on `tests/test_site.py` (`from click.testing import CliRunner`,
`from polla_app.__main__ import cli`). Write these tests:

1. `test_run_ok_with_stubbed_loaders` — stub the two Loto fetchers via
   `monkeypatch.setitem(pipeline_module.SOURCE_LOADERS, "openloto", fake)`
   and `... "polla", fake` where `fake` is a function returning a minimal
   payload dict `{"fuente": "https://x.test", "montos": {"Loto Clásico": 1_000_000_000}, "sorteo": 5000, "fecha": "2026-08-15", "sha256": "abc"}`.
   Invoke `cli` with `["run", "--sources", "pozos", "--raw-dir", str(tmp_path), "--normalized", str(tmp_path/"n.jsonl"), "--comparison-report", str(tmp_path/"c.json"), "--summary", str(tmp_path/"s.json"), "--state-file", str(tmp_path/"st.jsonl"), "--log-file", str(tmp_path/"l.jsonl"), "--retries", "1", "--timeout", "5"]`.
   Assert `result.exit_code == 0` and `"publish"` appears in `result.output` (the summary JSON echoes a `publish` bool). The pipeline will try to attach prices unless you also set `--no-...`? No — `include_prices=True` is hardcoded in `__main__.py:231`; so stub `polla_app.pipeline._attach_prices` (or `polla_app.sources.prices.get_loto_prices`) with a no-op via monkeypatch to avoid real fetches. Note: `pipeline._attach_prices` is imported into the `pipeline` module namespace — monkeypatch `"polla_app.pipeline._attach_prices"` with a lambda taking the same args that just logs.
2. `test_run_rejects_bad_retries` — `["run", "--sources", "pozos", "--retries", "0", ...]` → `result.exit_code != 0` and "must be >= 1" in `result.output`.
3. `test_run_rejects_invalid_source_url_format` — `["run", "--source-url", "novalid", ...]` → exit code != 0, "must be in the format" in output.
4. `test_run_rejects_invalid_alt_source_urls_env` — `monkeypatch.setenv("ALT_SOURCE_URLS", "{not json")`, invoke `run` with minimal args → exit code != 0, "valid JSON" in output.
5. `test_run_mixed_games_rejected` — `["run", "--sources", "pozos,kino", ...]` → exit code != 0 and "separate invocation" in output (surface for plan 020's guard).

**Verify**: `pytest tests/test_cli_commands.py -q` → 5 pass. No network is ever touched (no `requests.get` reachable — fetchers are stubbed).

### Step 2: Add `publish` command tests (dry-run path)

Stub `polla_app.__main__.publish_to_google_sheets` with a function that returns
`{"ok": True, "publish": False, "dry_run": True, "diff": "- old\n+ new"}` and
asserts it was called once (record the kwargs). Tests:

1. `test_publish_requires_flags` — `["publish"]` alone → exit code != 0, "Missing option" in output (both `--normalized` and `--comparison-report` are `required=True`).
2. `test_publish_dry_run_prints_diff` — invoke with `["publish", "--dry-run", "--normalized", str(tmp_path/"n.jsonl"), "--comparison-report", str(tmp_path/"c.json")]` (files may not exist — the stub replaces the loader) → exit code 0, `"- old"` and `"+ new"` in output, and the stub's kwargs show `dry_run=True`.
3. `test_publish_missing_summary_is_ok` — same as 2 but add `--summary str(tmp_path/"missing.json")` → exit code 0 (the FileNotFoundError branch proceeds without summary).

**Verify**: `pytest tests/test_cli_commands.py -q` → 8 pass.

### Step 3: Add `kino` command test

Stub `polla_app.__main__.get_pozo_kino` (imported into `__main__` module namespace — verify the import name with `grep -n "get_pozo_kino" polla_app/__main__.py` before writing) to return a minimal payload, invoke `["kino"]`, assert exit code 0 and the payload's `montos` echo. Add a second test where the stub raises `ParseError("boom")` → exit code 0 (the command catches and emits `{"error": ...}` JSON — assert `"error"` in output and `"boom"` not being a traceback, i.e. `"Traceback" not in result.output`).

**Verify**: `pytest tests/test_cli_commands.py -q` → 10 pass; `pytest -q` full suite green.

## Test plan

- New file `tests/test_cli_commands.py` with the 10 tests above.
- Structural patterns: `tests/test_site.py` (CliRunner + monkeypatch of `__main__` names) and `tests/test_e2e.py:39` (SOURCE_LOADERS stubbing).
- Verification: `pytest tests/test_cli_commands.py -q` → 10 passed; full `pytest -q` green; coverage of `__main__.py` goes up (check with `pytest --cov=polla_app.__main__ tests/test_cli_commands.py` — no threshold, just observe it's nonzero).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `tests/test_cli_commands.py` exists and `pytest tests/test_cli_commands.py -q` reports 10 passed
- [ ] `pytest -q` exits 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -c "def test_" tests/test_cli_commands.py` == 10
- [ ] The tests contain no network calls: `grep -nE "requests|urlopen|http" tests/test_cli_commands.py` → no matches except docstrings
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The import path of `get_pozo_kino` in `__main__.py` differs from expectation (check with grep first; adjust the monkeypatch target, not the production code).
- Stubbing `_attach_prices` doesn't prevent network calls — then stub the source fetch functions (`polla_app.sources.prices.get_loto_prices`, `get_kino_prices`) instead, but do not let a test hit the network.
- Any test requires editing production code to pass — report instead; the production code is out of scope.

## Maintenance notes

- When plan 022 removes the live-network e2e tests, these tests carry the coverage of `run`/`publish`/`kino` code paths — keep them in sync with any CLI option changes.
- The `kino` command's JSON-error shape (`{"error": ...}`) is asserted here; if a future plan unifies CLI error handling (see DEBT-05 in the index), update these assertions deliberately.
