# Plan 018: Rebuild the local venv on Python 3.13 (interpreter parity with CI)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 9180c98..HEAD -- pyproject.toml .github/workflows/tests.yml`
> If the runtime requirements in scope changed since this plan was written,
> compare the "Current state" excerpts against the live repo before
> proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW-MED
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `9180c98`, 2026-08-15

## Why this matters

`pyproject.toml:7` declares `requires-python = ">=3.13"`, CI runs Python
3.13 (`actions/setup-python python-version: '3.13'` in every workflow), and
commit `f890ef5` migrated the codebase to 3.13 — but the local dev venv is
still Python 3.12.3 (`.venv/pyvenv.cfg` → `version = 3.12.3`). Local runs
therefore test a different interpreter than CI: code that only works on
3.13 (or breaks on it) passes locally. The venv's `bin/black`/`bin/mypy`
scripts are also broken: their shebangs point at
`/home/carlos/VS_Code_Projects/polla/.venv/bin/python` — a nonexistent path
(`black: no se ha encontrado el fichero requerido`). Rebuilding on 3.13
restores local == CI parity and working tooling.

## Current state

- `.venv/pyvenv.cfg`:

  ```ini
  home = /usr/bin
  include-system-site-packages = false
  version = 3.12.3
  executable = /usr/bin/python3.12
  ```

- `pyproject.toml:7`: `requires-python = ">=3.13"`
- CI: every workflow uses `actions/setup-python` with `python-version: '3.13'`.
- `.venv/bin/black` shebang: `#!/home/carlos/VS_Code_Projects/polla/.venv/bin/python` (wrong path → `no se ha encontrado el fichero requerido`).
- pyenv has `3.13.12` and `3.14.3` installed (`/home/carlos/.pyenv/versions/`).
- This is a **local environment** change: no source files are touched, so
  nothing to commit. It fixes the interpreter mismatch and the broken
  shebangs in one step.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Interpreter | `.venv/bin/python --version` | `Python 3.13.x` |
| Full test | `.venv/bin/python -m pytest -q` | all pass |
| Typecheck | `mypy polla_app`         | exit 0              |
| Lint      | `ruff check polla_app tests` | exit 0           |
| Format    | `black --check polla_app tests` | exit 0        |

## Scope

**In scope** (the only things you should modify):
- Recreate `.venv` using a Python 3.13 interpreter

**Out of scope** (do NOT touch, even though they look related):
- Source files, tests, workflows, `requirements*.txt`, `pyproject.toml`
- The pyenv global version or any other project's venv
- Committing anything: this plan produces no repo changes

## Steps

### Step 1: Recreate the venv with Python 3.13

From the repo root (do NOT use `make clean` — it deletes `logs/`,
`artifacts/`, `pipeline_state/` and `storage_state.json`):

```bash
python3.13 -m venv --clear .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e .
.venv/bin/python -m playwright install chromium
```

If `python3.13` is not on PATH, use the pyenv interpreter directly:
`.venv/bin/python` after
`pyenv local 3.13.12` or
`/home/carlos/.pyenv/versions/3.13.12/bin/python -m venv --clear .venv`.

**Verify**:

```bash
.venv/bin/python --version
```

Expected: `Python 3.13.12` (or another 3.13.x). Note: the `--clear` flag
erases the old venv first, which fixes the broken shebangs (`bin/black`,
`bin/mypy` will now point at the new `.venv`).

### Step 2: Verify the tooling

**Verify**:

```bash
.venv/bin/black --check polla_app tests
.venv/bin/mypy polla_app
.venv/bin/ruff check polla_app tests
```

Expected: exit 0 on each; mypy prints `Success: no issues found`. Also
confirm the shebang is fixed:

```bash
head -1 .venv/bin/black
```

Expected: `#!/home/carlos/VS_Code_Projects/pipelines/polla/.venv/bin/python` (repo's actual path).

### Step 3: Full suite on 3.13

**Verify**:

```bash
.venv/bin/python -m pytest -q
```

Expected: `226 passed, 1 skipped` (count may drift ±1 if other plans
landed). All green on 3.13 — matching CI.

## Test plan

No new tests — this is a local environment rebuild. The verification
commands above are the gate. Optional parity check with CI:

```bash
cd /tmp/opencode && /home/carlos/VS_Code_Projects/pipelines/polla/.venv/bin/python -c "import sys; print(sys.version_info[:2])"
```

Expected: `(3, 13)`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `.venv/bin/python --version` → `Python 3.13.x`
- [ ] `.venv/bin/black`, `.venv/bin/mypy`, `.venv/bin/ruff` all execute (no
      "no se ha encontrado el fichero requerido")
- [ ] `black --check polla_app tests`, `mypy polla_app`,
      `ruff check polla_app tests` all exit 0
- [ ] `.venv/bin/python -m pytest -q` exits 0
- [ ] `git status` shows no changes to tracked files
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The venv cannot be recreated (network-restricted pip, missing Python 3.13
  interpreter) — report which step failed.
- A verification command fails twice after a reasonable fix attempt (e.g. a
  dependency that doesn't support 3.13).
- You are not on the machine where `.venv` lives (this plan is
  machine-specific; if the executor runs in a different environment, report
  and stop).

## Maintenance notes

- The Makefile's `lint`/`type-check`/`test` targets use bare `black`,
  `mypy`, `ruff` — on this machine they resolve through pyenv shims to a
  Python 3.12 environment. If `make ready`'s pre-commit hooks run mypy/pytest
  outside the venv, prefer invoking `.venv/bin/...` explicitly until the
  shims are aligned.
- If the project bumps `requires-python` again, repeat this plan.
- A reviewer should confirm the venv was rebuilt (not just `--clear` skipped)
  by checking `.venv/pyvenv.cfg` → `version = 3.13.x`.
