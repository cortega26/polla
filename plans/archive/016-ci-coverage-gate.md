# Plan 016: Enforce the 80% coverage gate in CI workflows

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 9180c98..HEAD -- .github/workflows/tests.yml .github/workflows/scrape.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `9180c98`, 2026-08-15

## Why this matters

README (line 23) and AGENTS.md promise "cumplimiento automático de cobertura
(umbral del 80%)" — but CI never enforces it. `tests.yml:36` and
`scrape.yml:57` run `pytest --cov=polla_app --cov-report=xml` with no
`--cov-fail-under`, and the codecov upload uses `fail_ci_if_error: false`
(the `target: 80%` in `.codecov.yml` is advisory only). The documented
guarantee is fiction; coverage could silently erode below 80% on the money
path without any red build. Current coverage is 86%, so the gate passes
today with headroom.

## Current state

- `.github/workflows/tests.yml:36`:

  ```yaml
      - name: Pytest
        run: pytest tests -v --cov=polla_app --cov-report=xml
  ```

- `.github/workflows/scrape.yml:57`:

  ```yaml
      - name: Run tests
        run: pytest tests -v --cov=polla_app --cov-report=xml
  ```

- `pyproject.toml:72-78` already declares the policy:
  `[tool.coverage.report] fail_under = 80` — but pytest-cov does not fail the
  build on it unless `--cov-fail-under` is passed (or a coverage report is
  generated in a failing mode).

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Coverage  | `pytest --cov=polla_app --cov-fail-under=80 -q` | exit 0, "Required test coverage of 80% reached" |
| Full test | `python -m pytest -q`    | all pass            |
| YAML sanity | `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/tests.yml')); yaml.safe_load(open('.github/workflows/scrape.yml'))"` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `.github/workflows/tests.yml` — add the flag to the Pytest step
- `.github/workflows/scrape.yml` — add the flag to the Run tests step

**Out of scope** (do NOT touch, even though they look related):
- `.codecov.yml` — codecov badge/threshold config; not a build gate.
- `pyproject.toml` — `fail_under` already exists; no change needed.
- `update.yml`, `pages.yml`, `docs.yml`, `health.yml` — no pytest coverage runs there.

## Git workflow

- Branch: `advisor/016-ci-coverage-gate`
- Commit style (repo convention): `ci(workflows): enforce 80% coverage gate with --cov-fail-under`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Update `tests.yml`

In `.github/workflows/tests.yml:36`, change:

```yaml
        run: pytest tests -v --cov=polla_app --cov-report=xml
```

to:

```yaml
        run: pytest tests -v --cov=polla_app --cov-report=xml --cov-fail-under=80
```

**Verify**: `python -m pytest --cov=polla_app --cov-report=xml --cov-fail-under=80 -q` → exit 0 with a line like `Required test coverage of 80% reached. Total coverage: 86%` (local coverage may differ slightly; must be ≥80).

### Step 2: Update `scrape.yml`

In `.github/workflows/scrape.yml:57`, apply the same change.

**Verify**: grep confirms both workflows contain `--cov-fail-under=80`:

```bash
grep -n "cov-fail-under" .github/workflows/tests.yml .github/workflows/scrape.yml
```

Expected: one match per file, inside the `run:` line.

### Step 3: Validate YAML and suite

**Verify**:

```bash
python -c "import yaml; [yaml.safe_load(open(f'.github/workflows/{n}')) for n in ('tests.yml','scrape.yml')]; print('yaml ok')"
python -m pytest -q
```

Expected: `yaml ok`, then the full suite passes.

## Test plan

No code tests — this is CI config. The verification commands above are the
gate. (Optional, if the repo uses actionlint: `actionlint .github/workflows/tests.yml .github/workflows/scrape.yml` if installed; otherwise skip.)

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -c "cov-fail-under=80" .github/workflows/tests.yml .github/workflows/scrape.yml` → 1 each
- [ ] Local `pytest --cov-fail-under=80 -q` exits 0
- [ ] YAML parses cleanly (step 3 command)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Local coverage is below 80% — do NOT raise the bar in the workflows; report
  the coverage drop instead (some other plan may have introduced the gap).
- The workflow files' pytest lines differ from the excerpts above.
- A verification command fails twice after a reasonable fix attempt.

## Maintenance notes

- If coverage later drops below 80% for a legitimate reason (e.g. a new
  optional path), the bar lives in three places: `pyproject.toml`
  (`fail_under`), `.codecov.yml` (`target`), and now both workflows
  (`--cov-fail-under`). Keep them in sync.
- A reviewer should confirm the flag was added to both files — missing one
  recreates the advisory-only situation for that pipeline.
