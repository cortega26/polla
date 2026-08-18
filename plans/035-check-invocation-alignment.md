# Plan 035: Align mypy and format invocations across Makefile, README, and CI

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- Makefile README.md .github/workflows/`
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

The same checks run with different scopes in different places: Makefile and
README and `scrape.yml` run `mypy polla_app` (package only), while
`tests.yml` and the pre-commit hook run `mypy polla_app tests` (package +
tests). A type error in `tests/` passes `make type-check` and the
production workflow but fails `tests.yml` — the local gate and the prod
gate disagree, and README's claim that "CI refleja estos comandos" is
false. Separately, the ruff-format gate exists **only** in the pre-commit
hook (`.pre-commit-config.yaml:22-27`); contributors without hooks installed
ship formatting drift that no CI catches.

## Current state

- `Makefile:27-28`:
  ```makefile
  type-check:
  	mypy polla_app
  ```
- `README.md:118`: "`mypy polla_app` – verifica el tipado estricto ..."
- `.github/workflows/scrape.yml` (test job): `run: mypy polla_app`
- `.github/workflows/tests.yml` (Mypy step): `run: mypy polla_app tests`
- `.pre-commit-config.yaml:37-40`: `args: ["polla_app", "tests"]`
- `Makefile:21-22` `format`: runs `black` only; pre-commit runs both
  `ruff-format` and `black`; no CI check for `ruff format`.
- `README.md:119` mentions `black --check`; `README.md:122` claims
  "CI refleja estos comandos a través de tests.yml".

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Typecheck (aligned) | `mypy polla_app tests` | exit 0 |
| Format check (new gate) | `ruff format --check polla_app tests` | exit 0 |
| Lint | `ruff check polla_app tests` | exit 0 |
| Black check | `black --check polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `Makefile` — `type-check` target; `format` target unchanged or extended with a note (see Step 2)
- `README.md` — the mypy line
- `.github/workflows/scrape.yml` — mypy line in the test job
- `.github/workflows/tests.yml` — add `ruff format --check` next to `black --check`

**Out of scope** (do NOT touch, even though they look related):
- `.pre-commit-config.yaml` — already aligned; leave it
- Adding `ruff format --check` to scrape.yml (it runs the full tests.yml-equivalent checks in its `test` job — check: scrape.yml has its own lint step; if it also runs black/ruff, add the format check there too only if it's the production strict gate — see Step 3)
- Any change to the formatters' configuration

## Git workflow

- Branch: `advisor/035-check-invocation-alignment`
- Commit message style: `build(dx): mypy polla_app tests y ruff format --check en todos los gates`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Align the mypy invocation in Makefile, README, and scrape.yml

- `Makefile:28`: `mypy polla_app` → `mypy polla_app tests`
- `README.md:118`: `mypy polla_app` → `mypy polla_app tests`
- `.github/workflows/scrape.yml` (the "Run type checking" step in the test job): `mypy polla_app` → `mypy polla_app tests`

**Verify**: `grep -rn "mypy polla_app$" Makefile README.md .github/workflows/` → no
matches that are missing `tests` (the pre-commit config uses `args: ["polla_app", "tests"]` — different syntax, fine).

### Step 2: Add the ruff-format gate to tests.yml

In `.github/workflows/tests.yml`, in the "Check formatting & linting" step,
add the format check:

```yaml
        run: |
          black --check polla_app tests
          ruff check polla_app tests
          ruff format --check polla_app tests
```

**Verify**: `grep -n "ruff format" .github/workflows/tests.yml` → the line
exists; locally `ruff format --check polla_app tests` exits 0.

### Step 3: Mirror the format gate in scrape.yml's test job (strict gate)

Check whether scrape.yml's test job runs `black --check` + `ruff check`
(same step as tests.yml): if yes, append `ruff format --check polla_app tests`
there too — scrape.yml is the production strict gate and should fail on
format drift identically.

**Verify**: `grep -n "ruff format" .github/workflows/scrape.yml` → the line
exists (if the lint step exists there).

## Test plan

- No unit tests. Verification: all four commands in the Commands table exit 0.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -rn "mypy polla_app" Makefile README.md .github/workflows/scrape.yml` → every occurrence includes `tests`
- [ ] `grep -rn "ruff format --check" .github/workflows/tests.yml .github/workflows/scrape.yml` → present in the workflow(s) that run black
- [ ] `mypy polla_app tests`, `ruff format --check polla_app tests`, `ruff check polla_app tests`, `black --check polla_app tests` all exit 0
- [ ] `pytest -q` exits 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `mypy polla_app tests` fails (it passes in the current venv — if not, report; do not add type ignores to make it pass).
- `ruff format --check` fails (formatting drift) — report the files; do not auto-format them (out of scope).
- scrape.yml's test job doesn't run black/ruff at all (structure differs) — skip the mirror there and note it.

## Maintenance notes

- README's "CI refleja estos comandos" claim becomes true again for typecheck; keep the claim true when adding new checks by updating all four places (Makefile, README, tests.yml, pre-commit).
- Plan 034 (make ready) uses these hooks; running 034 and 035 in sequence gives a fully aligned local/CI gate.
