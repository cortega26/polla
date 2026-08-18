# Plan 015: CLI-level tests for the `site` command (previous-data + stats failure)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 9180c98..HEAD -- tests/test_site.py polla_app/__main__.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/014-fix-site-previous-data-wiring.md
- **Category**: tests
- **Planned at**: commit `9180c98`, 2026-08-15

## Why this matters

`polla_app/__main__.py` has the lowest coverage in the repo (64%), and the
`site` command body (lines 355–385) is entirely uncovered by CLI-level tests.
Plan 014 found a real bug there: `--previous-data` was parsed but never
forwarded to `write_site_data` — invisible because only `build_site_payload`
was tested, never the command wiring. These tests lock the fixed behavior
and cover the stats-failure path so the CLI layer can't regress silently
again.

## Current state

- `tests/test_site.py` — tests only `build_site_payload`/`write_site_data`
  directly; no CliRunner tests exist. Ends at line 152.
- The CliRunner pattern to copy lives in `tests/test_health.py:5-14`:

  ```python
  from click.testing import CliRunner
  from polla_app.__main__ import cli

  def _invoke(args: list[str]) -> tuple[int, dict[str, Any]]:
      runner = CliRunner()
      result = runner.invoke(cli, args)
      assert result.exit_code == 0, result.output
      return result.exit_code, json.loads(result.output)
  ```

- The `site` command signature (after plan 014): `site --normalized <path>
  [--normalized-kino <path>] [--summary <path>] [--stats-url <url>]
  [--previous-data <path>] [--output <path>]`. It writes `data.json` at
  `--output` and tries to write `stats.json` next to it via
  `write_site_stats` (network CSV fetch) — which must be monkeypatched off in
  tests (repo rule: no network calls in tests).
- The `site` command calls `write_site_stats` and
  `write_site_data` — both are imported names in `polla_app/__main__.py`
  (`from .site import build_site_payload, write_site_data`; `from .stats
  import resolve_stats_url, write_site_stats`), so `monkeypatch.setattr` on
  the module works.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Test      | `python -m pytest tests/test_site.py -q` | all pass    |
| Full test | `python -m pytest -q`    | all pass            |
| Lint      | `ruff check polla_app tests`   | exit 0              |
| Format    | `black --check polla_app tests` | exit 0            |
| Typecheck | `mypy polla_app tests`   | exit 0, no issues   |

## Scope

**In scope** (the only files you should modify):
- `tests/test_site.py` — add CLI-level tests

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/__main__.py` — plan 014 owns the fix; if the fix is not yet
  merged into your base, apply plan 014 first (this plan DEPENDS on it).
- `polla_app/site.py`, `polla_app/stats.py` — no changes.
- Existing function-level tests in `tests/test_site.py` — leave them as-is.

## Git workflow

- Branch: `advisor/015-site-cli-tests`
- Commit style (repo convention): `test(site): cubrir el comando site con
  CliRunner (previous-data y fallo de stats)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add the helper and imports

At the top of `tests/test_site.py`, add:

```python
import pytest
from click.testing import CliRunner

from polla_app.__main__ import cli
```

Add a module-level helper (mirroring `tests/test_health.py`):

```python
def _invoke_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
) -> str:
    """Run `polla site` with a no-op stats writer and return data.json text."""
    from polla_app import __main__ as main_mod

    monkeypatch.setattr(main_mod, "write_site_stats", lambda *a, **k: None)
    result = CliRunner().invoke(cli, ["site", *args])
    assert result.exit_code == 0, result.output
    return (tmp_path / "data.json").read_text(encoding="utf-8")
```

The monkeypatch makes the stats CSV fetch a no-op (no network) while still
exercising the real command path.

**Verify**: `python -m pytest tests/test_site.py -q` → still passes (helper
not yet used; count unchanged).

### Step 2: Add the previous-data reuse test

Add a test that the CLI-level `--previous-data` flow reuses the previous
Kino section when the Kino input is missing (regression for plan 014):

```python
def test_site_cli_reuses_previous_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loto = tmp_path / "loto.jsonl"
    loto.write_text(
        json.dumps({"sorteo": 5465, "fecha": "2026-08-16", "confidence": "full",
                    "fuente": "openloto", "pozos_proximo": {"Loto Clásico": 620_000_000}}),
        encoding="utf-8",
    )
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps({
            "loto": {"sorteo": 5465, "pozos_clp": {"Loto Clásico": 620_000_000}},
            "kino": {"sorteo": 3266, "pozos_clp": {"Kino": 8_370_000_000}},
        }),
        encoding="utf-8",
    )

    raw = _invoke_site(tmp_path, monkeypatch, [
        "--normalized", str(loto),
        "--normalized-kino", str(tmp_path / "missing_kino.jsonl"),
        "--previous-data", str(previous),
        "--output", str(tmp_path / "data.json"),
    ])
    data = json.loads(raw)
    assert data["kino"]["sorteo"] == 3266
```

**Verify**: `python -m pytest tests/test_site.py -q` → new test passes.
Confirm it fails (kino `None`) if you revert the plan-014 one-line fix —
that is the regression proof. Run:

```bash
git stash push polla_app/__main__.py && python -m pytest tests/test_site.py -q -k previous_section; git stash pop
```

Expected: the new test FAILS on the reverted code, then passes again after
`git stash pop`.

### Step 3: Add the without-previous test

```python
def test_site_cli_without_previous_keeps_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loto = tmp_path / "loto.jsonl"
    loto.write_text(
        json.dumps({"sorteo": 5465, "fecha": "2026-08-16", "confidence": "full",
                    "fuente": "openloto", "pozos_proximo": {"Loto Clásico": 620_000_000}}),
        encoding="utf-8",
    )
    raw = _invoke_site(tmp_path, monkeypatch, [
        "--normalized", str(loto),
        "--normalized-kino", str(tmp_path / "missing_kino.jsonl"),
        "--output", str(tmp_path / "data.json"),
    ])
    data = json.loads(raw)
    assert data["kino"] is None
    assert data["loto"]["sorteo"] == 5465
```

**Verify**: `python -m pytest tests/test_site.py -q` → passes.

### Step 4: Add the stats-failure test

```python
def test_site_cli_stats_failure_still_writes_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app import __main__ as main_mod

    loto = tmp_path / "loto.jsonl"
    loto.write_text(
        json.dumps({"sorteo": 5465, "fecha": "2026-08-16", "confidence": "full",
                    "fuente": "openloto", "pozos_proximo": {"Loto Clásico": 620_000_000}}),
        encoding="utf-8",
    )

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("csv fetch failed")

    monkeypatch.setattr(main_mod, "write_site_stats", boom)
    result = CliRunner().invoke(cli, [
        "site",
        "--normalized", str(loto),
        "--output", str(tmp_path / "data.json"),
    ])
    assert result.exit_code == 0, result.output
    data = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    assert data["loto"]["sorteo"] == 5465
```

**Verify**: `python -m pytest tests/test_site.py -q` → all 4 new tests +
existing ones pass.

## Test plan

New tests (all in `tests/test_site.py`), modeled on the CliRunner pattern in
`tests/test_health.py`:

1. `test_site_cli_reuses_previous_section` — regression: previous-data path
   through the CLI.
2. `test_site_cli_without_previous_keeps_none` — baseline behavior.
3. `test_site_cli_stats_failure_still_writes_data` — stats failure path.
4. (Optional) `test_site_cli_summary_decision` — `--summary` wiring, if you
   want extra coverage of the decision block.

Verification: `python -m pytest tests/test_site.py -q` → all pass;
`python -m pytest -q` → full suite green.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `tests/test_site.py` contains the 3 required new tests, all passing
- [ ] Step 2's stash experiment demonstrated the test fails without the
      plan-014 fix (record the output in your final report)
- [ ] `python -m pytest -q` exits 0
- [ ] `ruff check polla_app tests` exits 0
- [ ] `black --check polla_app tests` exits 0
- [ ] `mypy polla_app tests` exits 0
- [ ] No network calls in the new tests (grep for `http`/`fetch` in the
      added lines returns nothing)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `tests/test_site.py` or `polla_app/__main__.py` differ from the excerpts
  above in a way that invalidates the approach.
- The plan-014 fix is not present in your base (the regression test would
  fail for the wrong reason) — report that 015 needs 014 first.
- A verification command fails twice after a reasonable fix attempt.
- The tests require touching an out-of-scope file.

## Maintenance notes

- These tests are the first to exercise the `site` command end-to-end;
  future CLI options for `site` should add a CliRunner case here, not only a
  function-level test.
- The stats no-op monkeypatch means a broken `write_site_stats` contract
  (e.g. new required kwargs) could pass silently — if stats wiring changes,
  revisit the helper.
- A reviewer should check the stash experiment was actually run and
  documented, not asserted from memory.
