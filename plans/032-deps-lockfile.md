# Plan 032: Pin production dependencies and add a lockfile with a freshness check

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- requirements.txt requirements-dev.txt pyproject.toml .github/workflows/ docs/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED (first bump after locking is deliberate; installs must be re-verified)
- **Depends on**: plan 033 should follow this one (both touch manifests/workflows)
- **Category**: migration
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The nightly production ingest (`scrape.yml`), the dry-run (`update.yml`),
and the dashboard (`pages.yml`) all run `pip install -r requirements.txt`,
which contains five floor-only pins (`beautifulsoup4>=4.12.3`,
`click>=8.1.7`, `requests>=2.33.1`, `gspread>=6.1.0`,
`scrapling[fetchers]>=0.4.7`). Dependencies are re-resolved fresh every
night, so a transitive or direct dep bump changes ingest behavior with zero
review. This already happened: commit `4615c93` documents how an unpinned
`playwright` pulled chromium-1234 while scrapling expected 1228, breaking
the browser fallback. The jobs run with the Google service-account,
spreadsheet, and Slack secrets in env — reproducibility is a security
property here, not just hygiene. Scrapling itself (0.x line, API churned
within 0.4.x) belongs on an upper bound.

## Current state

`requirements.txt` (repo root, 6 lines):

```
beautifulsoup4>=4.12.3
click>=8.1.7
requests>=2.33.1
gspread>=6.1.0
scrapling[fetchers]>=0.4.7
playwright==1.61.0
```

`pyproject.toml:8-15` — the same five floor pins + `playwright>=1.61.0,<1.62`
(note the discrepancy with requirements.txt — plan 033 unifies it).

`requirements-dev.txt`:

```
-r requirements.txt
black==26.3.1
mypy==1.13.0
pytest==9.0.3
pytest-cov==5.0.0
ruff==0.7.3
types-click==7.1.8
```

Workflow installs: `scrape.yml:94`, `update.yml:37`, `pages.yml:36` run
`pip install -r requirements.txt`; `tests.yml`, `docs.yml`, `health.yml`
install `requirements-dev.txt` (and `pip install -e .`).

Known-good verified versions (from the local venv, 2026-08-15):
playwright 1.61.0, scrapling 0.4.14, click 8.4.2, requests 2.34.2,
gspread 6.2.1, beautifulsoup4 4.15.0.

No lockfile exists (`ls *.lock uv.lock poetry.lock Pipfile.lock` → nothing).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Check pip-tools availability | `python -m pip show pip-tools \|\| pip show pip-tools` | may be absent — then `pip install pip-tools` (allowed; installs into the venv are fine, nothing repo-mutating) |
| Compile lock | `pip-compile --output-file requirements.lock requirements.txt` | exit 0, writes `requirements.lock` |
| Verify lock matches manifest | `pip-compile --dry-run --output-file requirements.lock requirements.txt` | "Would make no changes" (pip-tools >= 7) or exit 0 with no diff |
| Install from lock | `pip install -r requirements.lock` | exit 0 |
| Tests | `pytest -q` | all pass |
| Import surface | `python -c "import polla_app; import polla_app.pipeline, polla_app.sources.browser, polla_app.publish, polla_app.site"` | exit 0 (no import errors with locked versions) |

## Scope

**In scope** (the only files you should modify):
- `requirements.txt` — tighten `scrapling` to `>=0.4.14,<0.5` (bound to the verified-working line; the `>=0.4.7` floor is stale)
- `pyproject.toml` — same scrapling bound (keep the two manifests in sync)
- `requirements.lock` (create) — compiled lockfile
- `.github/workflows/scrape.yml`, `update.yml`, `pages.yml` — install from `requirements.lock`
- `.github/workflows/tests.yml` — add a lock-staleness check step
- `docs/` — one line in the relevant doc if it documents install commands (check `docs/API.md`/`docs/SLOs.md`; README's "Calidad y Pruebas" section mentions pip install only via requirements — update if it names `requirements.txt`)

**Out of scope** (do NOT touch, even though they look related):
- `requirements-dev.txt` — dev pins are already exact; leave them
- The playwright pin strategy (plan 033)
- Adding dependabot config (note it as a follow-up in Maintenance notes; the repo uses GitHub's built-in dependabot via settings)
- `pip-audit` CI step (separate follow-up; do not add in this plan)

## Git workflow

- Branch: `advisor/032-deps-lockfile`
- Commit message style: `build(deps): lockfile + cota superior de scrapling; CI instala desde el lock`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Tighten the scrapling bound in both manifests

- `requirements.txt`: `scrapling[fetchers]>=0.4.7` → `scrapling[fetchers]>=0.4.14,<0.5`
- `pyproject.toml` `dependencies`: same change.

**Verify**: `grep -n "scrapling" requirements.txt pyproject.toml` → both show `>=0.4.14,<0.5`.

### Step 2: Compile the lockfile

`pip-compile --output-file requirements.lock requirements.txt` (use
`python -m piptools compile` if the `pip-compile` entry point is missing).

**Verify**: `requirements.lock` exists and its first lines pin
`beautifulsoup4==…`, `scrapling[fetchers]==0.4.14` (or higher within <0.5),
`playwright==1.61.0`; commit it.

### Step 3: Install from the lock in production workflows

In `scrape.yml`, `update.yml`, and `pages.yml`, replace
`pip install -r requirements.txt` with `pip install -r requirements.lock`
(three sites; keep the surrounding steps unchanged). Note: `pages.yml` and
`scrape.yml` `setup-python` steps use `cache: 'pip'` with
`cache-dependency-path: 'requirements.txt'` — update those paths to
`requirements.lock` so the pip cache invalidates with the lock.

**Verify**: `grep -rn "requirements" .github/workflows/scrape.yml .github/workflows/update.yml .github/workflows/pages.yml` → installs reference `requirements.lock`; cache paths reference it too.

### Step 4: Lock-staleness check in tests.yml

Add a step in `tests.yml` (after the pip install, before or after lint —
place it near "Check formatting & linting"):

```yaml
      - name: Check lockfile freshness
        run: |
          pip-compile --dry-run --output-file requirements.lock requirements.txt \
            || { echo "::error::requirements.lock is stale; run pip-compile and commit"; exit 1; }
```

If `--dry-run` is unsupported by the installed pip-tools version, use the
portable alternative: compile to a temp file and diff:

```bash
pip-compile --output-file /tmp/req.lock requirements.txt && diff -u requirements.lock /tmp/req.lock
```

**Verify**: locally run the exact check command → exit 0.

### Step 5: Re-verify the install + suite

`pip install -r requirements.lock` then `pytest -q` and the import-surface
command → all green.

**Verify**: full suite passes with locked versions.

## Test plan

- No new unit tests; the CI freshness step is the gate. Existing suites
  (`pytest -q`) must pass with the locked resolution.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `requirements.lock` exists, is tracked, and pins `scrapling[fetchers]==0.4.*` (>=0.4.14, <0.5)
- [ ] `grep -n "scrapling" requirements.txt pyproject.toml` shows `>=0.4.14,<0.5`
- [ ] `grep -rn "requirements.lock" .github/workflows/scrape.yml .github/workflows/update.yml .github/workflows/pages.yml .github/workflows/tests.yml` shows installs, cache paths, and the freshness check
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `pip install -r requirements.lock` exits 0 in the local venv
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- `pip-compile` resolves a version that breaks the suite or the import surface — report the versions; do not hand-edit the lock.
- pip-tools cannot be installed (no network to PyPI) — report; the plan needs an operator-side compile.
- A workflow references `requirements.txt` somewhere beyond the three install sites (e.g. a verify-secret step) — report the extra site; extend the scope only with the reviewer's OK.

## Maintenance notes

- Bump discipline: edit `requirements.txt`, run `pip-compile`, commit both, let the freshness check enforce it. GitHub's dependabot (settings-enabled) will open PRs touching `requirements.txt`; merge them together with the regenerated lock.
- Plan 033 unifies the playwright pin and adds the chromium-parity check — run it after this plan.
- Follow-ups (not in this plan): a weekly `pip-audit` job with fail-on-high; dependabot for the lockfile. The scrape secrets env is the reason these matter.
