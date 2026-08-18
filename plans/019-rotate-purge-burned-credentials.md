# Plan 019: Rotate burned credentials and purge them from git history

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- .gitignore .github/workflows requirements.txt`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.
>
> **CRITICAL — read "Why this matters" before doing anything.**

## Status

- **Priority**: P1
- **Effort**: M (of which ~half is human-run steps you cannot do alone)
- **Risk**: MED — history rewrite requires force-push; rotation is mandatory before any rewrite
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Three burned-credential exposures are reachable from `main` history today:

1. A Google service-account JSON (`polla-chilena-371715-7e3e108472d0.json`,
   containing the account's `private_key`) was added at commit `ce1e38b`
   and is still extractable via `git show ce1e38b:<file>` even though it was
   later deleted from the tree. This key grants write access to the published
   spreadsheet (the exact credential type `publish.py:31-53` consumes).
2. `.github/workflows/check_credentials.yml` (commit `73654c0`, deleted at
   `ededa7c`) ran on a daily schedule and printed the full `CREDENTIALS`
   environment variable (the service-account JSON) to Actions logs.
3. A committed `.env` (added `9670b79`, removed `2457e07`) contained a
   Webshare.io proxy API token (`PROXY_API_URL`/`PROXY_API_TOKEN`).

The key is burned regardless of deletion — rotation is the only remedy, and
it must happen **before** any history rewrite (a rewritten history with a
live key is still a leak). This plan makes the repo changes that prevent
recurrence, then hands the rotation + purge steps to the operator.

Rule for this plan: **never write a secret value anywhere** — no excerpts of
the key, no `.env` contents, no tokens. Reference filenames/commits only.

## Current state

- `.gitignore` (repo root) contains `.env` but **no** rule for service-account
  files — the only `*.json` credential that slipped in had no guard:
  ```
  .env
  ```
  (this is why `polla-chilena-371715-7e3e108472d0.json` was committed)
- `polla_app/publish.py:31-53` — `_load_credentials()` reads
  `Path.cwd() / "service_account.json"`, then falls back to
  `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_CREDENTIALS` / `CREDENTIALS` env vars.
- `.github/workflows/verify-secret.yml` exists and prints only lengths/booleans
  (never values) — this is the pattern to keep.
- `.github/workflows/scrape.yml:101` still passes `ALT_SOURCES_API_KEYS` env
  (`${{ secrets.ALT_SOURCES_API_KEYS }}`) — a secret no code reads (grep
  `ALT_SOURCES_API_KEYS` across `polla_app/`: zero hits).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| List tracked files that match credential patterns | `git ls-files \| grep -iE 'service_account\|(^\.env$)'` | exit 1 (no matches) after the fix |
| Find candidate files in history (names only, never contents) | `git log --all --diff-filter=A --name-only --format='%H' \| grep -iE '\.env$|service_account|credentials.*\.json'` | lists known files incl. `polla-chilena-371715-7e3e108472d0.json` and `.env` |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |
| Tests | `pytest -q` | all pass |

## Scope

**In scope** (the only files you should modify):
- `.gitignore` — add service-account credential patterns
- `.github/workflows/tests.yml` — add a tracked-file credential scan step
- `.github/workflows/scrape.yml` — remove the dead `ALT_SOURCES_API_KEYS` env passthrough (one line, `env:` block of the `pipeline` step)
- `plans/README.md` — status row

**Out of scope** (do NOT touch, even though they look related):
- The git history rewrite (`git filter-repo` + force-push) — operator-run, Step 5 below, with explicit human approval.
- The GCP service-account key rotation — operator-run, Step 4 below.
- The Webshare token rotation — operator-run, Step 4 below.
- `polla_app/publish.py` — no code change needed.

## Git workflow

- Branch: `advisor/019-rotate-purge-credentials` (match repo convention; see merged `advisor/*` branches)
- Commit per step; message style: conventional commits in Spanish, e.g. `ci(security): escanear archivos con credenciales en tests.yml` (see `git log --oneline -10`)
- Do NOT push or open a PR unless the operator instructed it. Do NOT force-push anything.

## Steps

### Step 1: Add credential-file rules to `.gitignore`

Append to `.gitignore` (after the existing `.env` line):

```
# Google service-account credentials (rotate, never commit)
service_account*.json
*service_account*.json
*credentials*.json
```

**Verify**: `git check-ignore -v service_account.json` → prints the rule (e.g. `.gitignore:N:service_account.json`), and `git check-ignore -v polla-chilena-371715-7e3e108472d0.json` → prints the rule.

### Step 2: Add a tracked-file credential scan to `tests.yml`

In `.github/workflows/tests.yml`, add a step right after the "Check formatting & linting" step (which currently runs `black --check polla_app tests` + `ruff check polla_app tests`):

```yaml
      - name: Scan tracked files for credentials
        run: |
          matches=$(git ls-files | grep -iE 'service_account|(^\.env$)|credentials.*\.json' || true)
          if [ -n "$matches" ]; then
            echo "::error::Credential-shaped files are tracked:"; echo "$matches"
            exit 1
          fi
```

Do NOT include any filename that still exists in the tree at runtime — after Step 1 and the fact that the tree is already clean, this must pass. (The known files exist only in history, which `git ls-files` does not see.)

**Verify**: `bash -n .github/workflows/tests.yml` (YAML sanity is caught by CI) and locally: `git ls-files | grep -iE 'service_account|(^\.env$)|credentials.*\.json' || true` → empty output.

### Step 3: Remove the dead `ALT_SOURCES_API_KEYS` passthrough

In `.github/workflows/scrape.yml`, in the `pipeline` step's `env:` block (currently includes `ALT_SOURCE_URLS` and `GOOGLE_SERVICE_ACCOUNT_JSON`/`GOOGLE_SPREADSHEET_ID`), delete the line:

```yaml
          ALT_SOURCES_API_KEYS: ${{ secrets.ALT_SOURCES_API_KEYS }}
```

**Verify**: `grep -n ALT_SOURCES_API_KEYS .github/workflows/scrape.yml` → no matches (and repo-wide: `grep -rn ALT_SOURCES_API_KEYS --include='*.py' --include='*.yml' --include='*.yaml' . | grep -v plans/` → no matches).

### Step 4: Operator-only — rotate the credentials (STOP until confirmed)

This step must be done by a human with console access. Prepare a checklist you deliver to the operator (do not perform it yourself):

1. Google Cloud console → IAM & Admin → Service Accounts → `polla-chilena-371715-7e3e108472d0` → Keys → **delete every key**, then create a new key and store it as `GOOGLE_SHEETS_CREDENTIALS` / `GOOGLE_SERVICE_ACCOUNT_JSON` secret in GitHub (and locally in `service_account.json`, which is gitignored after Step 1).
2. Webshare.io dashboard → regenerate the proxy API token; update any environment that used `PROXY_API_TOKEN`.
3. Confirm the repo's GitHub settings have push protection / secret scanning enabled (Settings → Code security); if not, enable them.

**Verify**: operator confirms the old key no longer exists in GCP and the new key works for `publish --dry-run` (credentials env set locally). **STOP if the operator has not confirmed rotation before you attempt Step 5.**

### Step 5: Operator-only — purge the files from history

Deliver this checklist to the operator; do not run it yourself:

1. Backup: `git clone --mirror <repo-url> /tmp/polla-backup-<date>` and confirm `git -C /tmp/polla-backup-<date> rev-parse HEAD` works.
2. Install `git-filter-repo` (e.g. `pip install git-filter-repo`).
3. `git filter-repo --invert-paths --path polla-chilena-371715-7e3e108472d0.json --path .env --path .github/workflows/check_credentials.yml`
4. Add remote again (filter-repo removes it), `git push --force --all` and `git push --force --tags`.
5. Warn collaborators to re-clone (old clones keep the history).

**Verify**: `git log --all --oneline --diff-filter=A --name-only --format='%H' | grep -cE 'polla-chilena|^\.env$'` → `0`, and `git fsck --no-reflogs --unreachable` shows no remaining dangling blobs for those paths (may require `git reflog expire --expire=now --all && git gc --prune=now`; if unreachable objects remain, note it in the report — GitHub keeps unreachable objects for 90 days).

## Test plan

No new unit tests for this plan (no application code changes). CI is the verification: the new scan step in `tests.yml` must pass on the next run of the workflow. If you want to verify the scan locally before pushing, run the `git ls-files` command from Step 2.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `git ls-files | grep -iE 'service_account|(^\.env$)|credentials.*\.json'` exits 1 (no matches)
- [ ] `git check-ignore -v service_account.json` prints a rule
- [ ] `grep -rn ALT_SOURCES_API_KEYS .github/workflows/` returns no matches
- [ ] `ruff check polla_app tests` and `mypy polla_app tests` exit 0; `pytest -q` all pass
- [ ] No files outside the in-scope list are modified (`git status` clean except the intended files)
- [ ] Operator has confirmed Step 4 rotation; Step 5 purge done or explicitly deferred with reason
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- You find a **live** credential-shaped file in the working tree (never print its contents; report the path).
- You find additional secret-bearing files in history beyond the three known paths (report paths only).
- The operator is unavailable to confirm rotation — do NOT rewrite history on your own.
- The code at the locations in "Current state" doesn't match the excerpts.

## Maintenance notes

- The scan step in `tests.yml` is the permanent guard: any future commit adding a credential-shaped file fails CI immediately.
- When the service-account key is rotated, update the GitHub secrets used by `scrape.yml`/`update.yml`/`pages.yml` (`GOOGLE_SHEETS_CREDENTIALS`) and the local `service_account.json`.
- GitHub retains unreachable objects ~90 days after purge; the burn window for the rotated key is the rotation date, not the purge date — document the rotation date in the PR description.
- If the repo is ever made public, assume the entire history before the purge was compromised and re-rotate everything once more.
