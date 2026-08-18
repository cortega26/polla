# Plan 034: Make `make ready` work on fresh machines and stop staging everything

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- Makefile requirements-dev.txt CONTRIBUTING.md README.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

README's quick-start step 1 is `make ready`, but `ready` runs
`pre-commit run --all-files` (Makefile:50-53) and `pre-commit` is in no
requirements file and mentioned in no doc — a fresh dev machine fails at
step 1 with `pre-commit: command not found`. Worse, the target runs
`git add .` **before** the checks, so every unrelated WIP file gets staged,
and the config's own `block-unstaged-changes` hook (`.pre-commit-config.yaml:5-11`)
is defeated (there are never unstaged changes to block once everything is
added). If a hook fails, the tree is left partially staged. The fix: make
pre-commit a documented dev dependency, and run checks against the real
worktree, staging only after they pass.

## Current state

`Makefile:50-53`:

```makefile
ready:
	git add .
	pre-commit run --all-files
	git add .
```

`requirements-dev.txt` (6 lines): black, mypy, pytest, pytest-cov, ruff,
types-click — **no pre-commit**.

`CONTRIBUTING.md:7-11` — install steps (`pip install -r requirements-dev.txt`);
no mention of pre-commit or `pre-commit install`.

`.pre-commit-config.yaml:5-11` — the local `check-unstaged` hook:

```yaml
      - id: check-unstaged
        name: block-unstaged-changes
        entry: git diff --exit-code
        ...
        description: Blocks commit if there are unstaged changes to prevent pre-commit stash conflicts.
```

`README.md:59-63` — quick start step 1 is `make ready`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Verify pre-commit installed after fix | `pre-commit --version` | version prints |
| Validate hook config | `pre-commit validate-config` | exit 0 |
| Dry-run the ready flow (no staging) | `pre-commit run --all-files` | all hooks pass (may need `pre-commit install` first) |
| Lint (repo) | `ruff check polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `requirements-dev.txt` — add `pre-commit`
- `CONTRIBUTING.md` — document `pre-commit install`
- `Makefile` — reorder `ready`: hooks first, stage after
- `README.md` — one sentence in the quick start about pre-commit (only if a natural spot exists)

**Out of scope** (do NOT touch, even though they look related):
- The `.pre-commit-config.yaml` hook list — no changes
- The dual-formatter setup (black + ruff-format) — plan 035
- `git add .` in CI or elsewhere

## Git workflow

- Branch: `advisor/034-make-ready-fix`
- Commit message style: `build(dx): make ready sin git add previo; pre-commit en requirements-dev`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add pre-commit to dev requirements

Append to `requirements-dev.txt`:

```
pre-commit==4.2.0
```

(Check the currently installed version with `pre-commit --version` if
available — pin to the installed major; if none is installed, use a recent
stable, e.g. `pre-commit>=4,<5`.)

**Verify**: `grep -n pre-commit requirements-dev.txt` → the line exists.

### Step 2: Reorder the `ready` target

Replace the Makefile target:

```makefile
ready:
	git add .
	pre-commit run --all-files
	git add .
```

with:

```makefile
ready:
	pre-commit run --all-files
	git add .
```

**Verify**: `sed -n '48,53p' Makefile` → `pre-commit run --all-files` comes
first, a single `git add .` after it.

### Step 3: Document pre-commit in CONTRIBUTING

In CONTRIBUTING.md, after the install-deps instructions, add one line:

```
- Instala los hooks locales (una vez): `pre-commit install`
```

Keep the surrounding text unchanged.

**Verify**: `grep -n "pre-commit" CONTRIBUTING.md` → the line exists.

## Test plan

- No unit tests. Manual verification: on a machine with pre-commit
  installed, `make ready` runs hooks on the real worktree and stages only
  after they pass; a machine without pre-commit now installs it via
  `requirements-dev.txt`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n pre-commit requirements-dev.txt` → pinned line
- [ ] `grep -n -A3 "^ready:" Makefile` → hooks first, then one `git add .`
- [ ] `grep -n "pre-commit install" CONTRIBUTING.md` → documented
- [ ] `pre-commit validate-config` exits 0
- [ ] `ruff check polla_app tests` and `mypy polla_app tests` exit 0 (unchanged code)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `pre-commit` is already a dev dependency somewhere else (double pin) — merge, don't duplicate.
- The `ready` target text differs from the excerpt — adapt the edit to the live text.
- Running `pre-commit run --all-files` fails on an existing file (formatting drift) — report; do not auto-fix files outside this plan's scope.

## Maintenance notes

- After this plan, `make ready`'s guarantee is: nothing staged until all
  hooks pass — the `block-unstaged-changes` hook regains its purpose.
- Plan 035 aligns the mypy/format invocations that these hooks run — run
  both plans in sequence.
- AGENTS.md's "run `make ready` before committing" instruction now works on
  a fresh clone.
