# Plan 025: Reconcile environment-variable and README contract with the code

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- README.md CONTRIBUTING.md polla_app/net.py .github/workflows/scrape.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW (docs/config; no code behavior change unless Step 2 option is chosen)
- **Depends on**: none
- **Category**: dx
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The documented operator contract is wrong in four ways: (1)
`POLLA_BACKOFF_FACTOR` is documented with default `0.3` but the code uses
`30.0` (net.py:162) — a 100x difference in retry latency, and the backoff
formula `factor * 2^(attempt-1)` (net.py:74-82) means operators setting
0.3 get 0.3s/0.6s/1.2s sleeps while the default runs are 30s/60s/120s;
(2) `POLLA_429_BACKOFF_SECONDS` is documented as "fixed delay after 429"
but is a legacy alias consulted only when `POLLA_BACKOFF_FACTOR` is unset;
(3) the README `publish --dry-run` example is non-runnable because
`--normalized` and `--comparison-report` are `required=True`
(`__main__.py:238-239`); (4) the README badge claims "Python 3.11+" while
`pyproject.toml:7` requires `>=3.13`. Also: `GOOGLE_SHEETS_SPREADSHEET_ID`
is read by code (publish.py:321,363) but documented nowhere, and
`scrape.yml:101` passes a dead `ALT_SOURCES_API_KEYS` secret that no code
reads. There is no `.env.example`.

## Current state

- `README.md:9` — badge: `https://img.shields.io/badge/python-3.11%2B-...`
- `README.md:104` — `POLLA_BACKOFF_FACTOR` | float | `0.3` | No | ...
- `README.md:105` — `POLLA_429_BACKOFF_SECONDS` | entero | — | No | "Retraso fijo tras recibir un código de estado 429 (fallback)."
- `README.md:89` — `python -m polla_app publish --dry-run`
- `CONTRIBUTING.md:28` — "Python 3.11+ only"
- `polla_app/net.py:161-165`:
  ```python
  max_retries = retries if retries is not None else int(os.getenv("POLLA_MAX_RETRIES", "3"))
  backoff_factor = float(os.getenv("POLLA_BACKOFF_FACTOR", "30.0"))
  # Fallback to legacy env if set for backward compatibility
  if "POLLA_429_BACKOFF_SECONDS" in os.environ and "POLLA_BACKOFF_FACTOR" not in os.environ:
  ```
  (next line assigns `POLLA_429_BACKOFF_SECONDS` to the backoff factor)
- `polla_app/__main__.py:238-239` — `--normalized` and `--comparison-report` are `required=True` on `publish`
- `polla_app/publish.py:321,363` — reads `GOOGLE_SHEETS_SPREADSHEET_ID` (with fallback to `GOOGLE_SPREADSHEET_ID`)
- `.github/workflows/scrape.yml:101` — `ALT_SOURCES_API_KEYS: ${{ secrets.ALT_SOURCES_API_KEYS }}` (no code reads it)
- No `.env.example` in the repo root.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Doctests | `pytest --doctest-glob='*.md' README.md docs -q` | 0 failed |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |
| Verify example | `python -m polla_app publish --help` | shows both required options |

## Scope

**In scope** (the only files you should modify):
- `README.md` — badge, env table rows, publish example
- `CONTRIBUTING.md` — Python version line
- `.env.example` (create — template of documented env vars)
- `.github/workflows/scrape.yml` — remove the dead `ALT_SOURCES_API_KEYS` passthrough

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/net.py` — do NOT change the `30.0` default or the legacy env alias in this plan (behavior change requires its own decision; see STOP conditions). This plan only fixes the *documentation* to match reality.
- `publish.py` — no code change; the required-flag contract is deliberate (workflows pass both flags explicitly).
- The `GOOGLE_SHEETS_SPREADSHEET_ID` alias — document it; removing the alias is a separate decision.

## Git workflow

- Branch: `advisor/025-env-docs-reconcile`
- Commit message style: `docs(env): alinear README y .env.example con el contrato real`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Fix the README env table rows

Update `README.md:104-105` to match `net.py`:

- `POLLA_BACKOFF_FACTOR` | float | `30.0` | No | "Multiplicador base del retroceso exponencial (`factor * 2^(intento-1)` segundos; cubre 429/500/502/503/504)."
- `POLLA_429_BACKOFF_SECONDS` | float | — | No | "Alias legacy: se usa como factor de retroceso solo si `POLLA_BACKOFF_FACTOR` no está definido."

Add a row for the undocumented alias:
- `GOOGLE_SHEETS_SPREADSHEET_ID` | string | — | Condicional | "Alias legacy de `GOOGLE_SPREADSHEET_ID` (misma hoja)."

**Verify**: `grep -n "POLLA_BACKOFF_FACTOR\|POLLA_429_BACKOFF_SECONDS\|GOOGLE_SHEETS_SPREADSHEET_ID" README.md` → rows match the new text.

### Step 2: Fix the publish example and the badge

Replace `README.md:89` with a runnable example:

```bash
python -m polla_app publish --dry-run \
  --normalized artifacts/normalized.jsonl \
  --comparison-report artifacts/comparison_report.json
```

Change the badge on `README.md:9` from `python-3.11%2B` to `python-3.13%2B`
(keep the rest of the URL identical).

**Verify**: `python -m polla_app publish --dry-run --normalized /tmp/x.jsonl --comparison-report /tmp/y.json` fails with a *different* error than "Missing option" (it will fail on credentials/config instead — proving the flags parse). `grep -n "3.13%2B" README.md` → 1 match.

### Step 3: Fix CONTRIBUTING and create `.env.example`

`CONTRIBUTING.md:28` → "Python 3.13+ only".

Create `.env.example` (repo root) with every env var from the README table
(rows at README.md:94-109 after Step 1), commented, no real values:

```
# Google Sheets publishing (required for `publish`, not for --dry-run)
GOOGLE_SPREADSHEET_ID=
# GOOGLE_SERVICE_ACCOUNT_JSON=       # inline JSON; or use service_account.json
# GOOGLE_CREDENTIALS=                # legacy alias
# GOOGLE_SHEETS_SPREADSHEET_ID=      # legacy alias of GOOGLE_SPREADSHEET_ID
# ALT_SOURCE_URLS={"openloto": "https://..."}   # JSON mapping of source overrides
# POLLA_USER_AGENT=
# POLLA_RATE_LIMIT_RPS=
# POLLA_MAX_RETRIES=3
# POLLA_BACKOFF_FACTOR=30.0
# POLLA_429_BACKOFF_SECONDS=         # legacy alias, only used if POLLA_BACKOFF_FACTOR unset
# SLACK_WEBHOOK_URL=
# POLLA_PUBLISH_LOCK_PATH=pipeline_state/publish.lock
# POLLA_PUBLISH_LOCK_TIMEOUT=300
# POLLA_STATS_URL=
```

**Verify**: `git check-ignore .env.example` → exits 1 (it must be tracked, not ignored — `.gitignore` only ignores `.env`).

### Step 4: Remove the dead CI secret passthrough

In `.github/workflows/scrape.yml:101`, delete the `ALT_SOURCES_API_KEYS` line from the `pipeline` step's `env:` block.

**Verify**: `grep -rn ALT_SOURCES_API_KEYS --include='*.yml' --include='*.yaml' --include='*.py' . | grep -v plans/` → no matches.

## Test plan

- No unit tests; verification is the doctest suite and grep checks above.
- `pytest --doctest-glob='*.md' README.md docs -q` must not fail (existing doctests unaffected — the README publish example is a bash block, not a doctest).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "POLLA_BACKOFF_FACTOR" README.md` shows default `30.0`
- [ ] `grep -n "python-3.13" README.md` shows the updated badge
- [ ] `README.md` publish example includes both required flags
- [ ] `.env.example` exists and is not gitignored (`git check-ignore .env.example` exits 1)
- [ ] `grep -rn ALT_SOURCES_API_KEYS .github/ polla_app/` returns no matches
- [ ] `ruff check polla_app tests`, `mypy polla_app tests` exit 0; `pytest -q` all pass
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The operator signals the `30.0` default is actually wrong and should be 0.3 — that is a behavior change; propose a separate plan rather than editing net.py here.
- You find additional env vars read by code that are undocumented — list them in the report and add them to `.env.example` (that is in scope; keep going).
- The `publish --help` output shows the required flags have changed — update the example accordingly and note it.

## Maintenance notes

- Any future env-var change should update README + `.env.example` + (if relevant) this plan's rows — the three must stay in lockstep.
- `GOOGLE_SHEETS_SPREADSHEET_ID` remains a supported alias; a future cleanup plan may deprecate it (needs a migration note per AGENTS.md).
- The dead `ALT_SOURCES_API_KEYS` secret can be deleted from the repo's GitHub Settings → Secrets once this plan lands.
