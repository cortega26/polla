# Plan 017: Remove the dead/conflicting mypy config from pyproject.toml

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 9180c98..HEAD -- pyproject.toml mypy.ini`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `9180c98`, 2026-08-15

## Why this matters

The repo has two mypy configs: `pyproject.toml` `[tool.mypy]` (with stale
`python_version = "3.10"`) and `mypy.ini` (active, `python_version = 3.13`).
mypy reads the first config file it finds (`mypy.ini` wins), so the
pyproject.toml block is dead config — and a trap: running
`mypy --config-file pyproject.toml polla_app` produces 7 errors including
`Module "datetime" has no attribute "UTC"` (3.10 vs 3.13). Anyone who
deletes `mypy.ini` "to simplify" would silently break the build with a
misleading 3.10 target. Mypy also warns on unused sections in `mypy.ini`
(`[mypy-googleapiclient.*]`, `[mypy-tenacity.*]` — dead deps removed in
`807d984`). This plan removes the dead config and the unused sections.

## Current state

- `pyproject.toml:38-67`:

  ```toml
  [tool.mypy]
  python_version = "3.10"
  warn_return_any = true
  warn_unused_configs = true
  warn_unused_ignores = false
  disallow_untyped_defs = true

  [[tool.mypy.overrides]]
  module = "gspread"
  ignore_missing_imports = true

  [[tool.mypy.overrides]]
  module = "requests"
  ignore_missing_imports = true

  [[tool.mypy.overrides]]
  module = "bs4"
  ignore_missing_imports = true

  [[tool.mypy.overrides]]
  module = "bs4.*"
  ignore_missing_imports = true

  [[tool.mypy.overrides]]
  module = "scrapling.*"
  ignore_missing_imports = true

  [[tool.mypy.overrides]]
  module = "scrapling"
  ignore_missing_imports = true

  [[tool.mypy.overrides]]
  module = "playwright.*"
  ignore_missing_imports = true
  ```

- `mypy.ini` (the ACTIVE config — mypy.ini precedes pyproject.toml in
  mypy's search order) — contains the same settings plus per-module
  `ignore_missing_imports`, including two now-unused sections:

  ```ini
  [mypy-google.*]
  ignore_missing_imports = True

  [mypy-googleapiclient.*]   # UNUSED: no googleapiclient imports remain
  ignore_missing_imports = True

  [mypy-tenacity.*]          # UNUSED: no tenacity imports remain
  ignore_missing_imports = True
  ```

  Mypy confirms: `mypy polla_app` prints
  `mypy.ini: note: unused section(s): [mypy-googleapiclient.*], [mypy-tenacity.*]`.

- Coverage of the `playwright`/`scrapling` overrides is preserved: the
  imports are all inside function bodies (see `polla_app/sources/browser.py:24`
  `from scrapling import StealthyFetcher`), and `mypy.ini` covers the only
  missing-stub imports in use (gspread, requests, bs4, google.*). After the
  removal, `mypy polla_app` must still pass cleanly — that is the gate.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Typecheck | `mypy polla_app`         | exit 0, no "unused section" note |
| Full type | `mypy polla_app tests`   | exit 0              |
| Lint      | `ruff check polla_app tests` | exit 0           |
| Full test | `python -m pytest -q`    | all pass            |

## Scope

**In scope** (the only files you should modify):
- `pyproject.toml` — delete the `[tool.mypy]` block (lines 38–67)
- `mypy.ini` — delete the unused `[mypy-googleapiclient.*]` and
  `[mypy-tenacity.*]` sections

**Out of scope** (do NOT touch, even though they look related):
- The `[tool.pytest.ini_options]`, `[tool.black]`, `[tool.coverage.*]`
  blocks in `pyproject.toml`.
- `polla_app/**` — no source changes.
- Anything in `mypy.ini` other than the two listed sections
  (`[mypy-google.*]` is still used — verify before assuming).

## Git workflow

- Branch: `advisor/017-mypy-config-cleanup`
- Commit style (repo convention): `build(config): eliminar [tool.mypy] muerto de pyproject y secciones sin uso de mypy.ini`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Remove the dead `[tool.mypy]` block from pyproject.toml

Delete everything from line 38 (`[tool.mypy]`) through line 67 (the last
`[[tool.mypy.overrides]]` block for `playwright.*`). Confirm the surrounding
blocks are untouched: `[tool.pytest.ini_options]` (line 30) and
`[tool.coverage.run]` (line 72) must remain.

**Verify**:

```bash
grep -n "tool.mypy" pyproject.toml
```

Expected: no matches. And:

```bash
mypy polla_app
```

Expected: exit 0, **no** `unused section(s)` note (the note disappears only
after step 2; if it still prints, proceed — the check completes in step 2).

### Step 2: Prune unused sections from mypy.ini

Delete the two sections:

```ini
[mypy-googleapiclient.*]
ignore_missing_imports = True

[mypy-tenacity.*]
ignore_missing_imports = True
```

Keep `[mypy-google.*]` and everything below (gspread/requests/bs4) intact.

**Verify**:

```bash
mypy polla_app
```

Expected: exit 0, `Success: no issues found in 18 source files`, and **no**
`unused section(s)` note.

### Step 3: Full verification

**Verify** (all must pass):

```bash
mypy polla_app tests
ruff check polla_app tests
black --check polla_app tests
python -m pytest -q
```

Expected: exit 0 on each; pytest `226 passed, 1 skipped` (count may drift by
±1 if other plans landed).

## Test plan

No new tests — this is build config. The gates are the commands above.
Optional sanity check that the effective config is unchanged:

```bash
mypy --config-file mypy.ini polla_app
```

Expected: same `Success` result as the default invocation (proves the active
config was mypy.ini all along).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -c "\[tool.mypy\]" pyproject.toml` → 0
- [ ] `grep -c "googleapiclient\|tenacity" mypy.ini` → 0
- [ ] `mypy polla_app` exits 0 with no `unused section(s)` note
- [ ] `mypy polla_app tests`, `ruff check .`, `black --check .`, `python -m pytest -q` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `mypy polla_app` fails after the removal (e.g. a section that *was* in use
  gets deleted by accident, or an import that relied on a pyproject override
  surfaces) — restore the removed block and report, do not edit mypy.ini
  settings to paper over it.
- `pyproject.toml` or `mypy.ini` don't match the excerpts above.
- A verification command fails twice after a reasonable fix attempt.

## Maintenance notes

- `mypy.ini` is now the single source of truth for mypy. Any future
  `ignore_missing_imports` entry belongs there, not in pyproject.toml.
- If `googleapiclient` or `tenacity` are ever re-added, re-add their
  sections to `mypy.ini`.
- A reviewer should confirm only the two files changed and that the
  `[mypy-google.*]` section survived (it covers `google.oauth2` used by
  `publish.py`).
