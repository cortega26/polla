# Plan 036: pages.yml reuses scrape.yml artifacts instead of re-ingesting

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- .github/workflows/scrape.yml .github/workflows/pages.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: MED (pages must still deploy when scrape.yml failed — the fallback path is load-bearing)
- **Depends on**: none (run after 030 if possible — both touch pages.yml; 030 edits the state-file flag, this plan rewrites the ingest steps)
- **Category**: perf
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

`pages.yml` (14:00 UTC) re-fetches every URL that `scrape.yml` (13:00 UTC)
already fetched an hour earlier: the Loto `run --sources pozos` and Kino
`run --sources kino` steps run identical ingests with identical defaults,
solely so the `site` step minutes later can read `artifacts/normalized.jsonl`
and `artifacts_kino/normalized.jsonl`. `scrape.yml` already uploads exactly
those files as the `alt-sources-artifacts` artifact. This doubles the daily
upstream network load and the browser-launch risk (polla.cl 403s trigger a
Chromium launch per workflow), and on a flaky day the duplicate run pays
the full retry/backoff cost. Loto/Kino data changes only at draw time
(2-3x/week), so the "1 hour fresher" argument is illusory.

## Current state

`.github/workflows/pages.yml` (excerpts):

```yaml
on:
  schedule:
    - cron: '0 14 * * *'  # daily 14:00 UTC (after the 13:00 ingest)
  workflow_dispatch:

jobs:
  deploy:
    ...
    steps:
      - uses: actions/checkout@v6
      - name: Set up Python ... (3.13, cache pip, requirements.txt)
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          python -m playwright install chromium --with-deps || python -m playwright install chromium
      - name: Restore last dashboard data  (site/data.json, site/stats.json cache)
      - name: Ingest Loto pozos (dry data for the dashboard)
        id: ingest-loto
        continue-on-error: true
        run: |
          mkdir -p artifacts site
          python -m polla_app run --sources pozos --retries 2 --timeout 30 --no-fail-fast --raw-dir artifacts/raw ...
      - name: Ingest Kino pozos
        id: ingest-kino
        continue-on-error: true
        run: | (same for --sources kino, artifacts_kino)
      - name: Build dashboard (polla site ...)
      - name: Deploy to GitHub Pages
```

`.github/workflows/scrape.yml` (ingest job, excerpts):

```yaml
      - name: Upload pipeline artifacts
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: alt-sources-artifacts
          path: |
            artifacts/
            artifacts_kino/
            logs/
          retention-days: 30
```

The `site` step in pages.yml passes `--previous-data site/data.json` (from
the cache restore) — that fallback stays and is what makes "scrape.yml
failed but we still deploy the last good data" work today.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| YAML sanity | `python -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/pages.yml').read_text())"` | prints dict (pyyaml may be absent — then skip) |
| Verify artifact download syntax | `grep -n "download-artifact\|workflow_run" .github/workflows/pages.yml` | new trigger + download step |
| Lint (repo) | `ruff check polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `.github/workflows/pages.yml`

**Out of scope** (do NOT touch, even though they look related):
- `.github/workflows/scrape.yml` — artifact name `alt-sources-artifacts` already exists; no change
- `polla_app/*` — no code changes
- Plan 030's state-file flag changes — coordinate: if 030 added `--state-file` to the `site` step, keep it here

## Git workflow

- Branch: `advisor/036-pages-reuse-artifacts`
- Commit message style: `ci(pages): reutilizar artefactos de scrape.yml en vez de re-ingestar`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add a `workflow_run` trigger and artifact download

In `pages.yml`:

1. Add to the `on:` block:
   ```yaml
   workflow_run:
     workflows: ["Ingest Alternative Sources"]
     types: [completed]
     branches: [main]
   ```
   (The `name` of scrape.yml is "Ingest Alternative Sources" — verify with
   `grep -n "^name:" .github/workflows/scrape.yml`.)
2. Keep the existing schedule + `workflow_dispatch` triggers.
3. Add, after the "Install dependencies" step (and before "Restore last
   dashboard data"), a step:
   ```yaml
      - name: Download latest ingest artifacts
        id: download-artifacts
        if: github.event_name == 'workflow_run'
        uses: actions/download-artifact@v7
        with:
          name: alt-sources-artifacts
          path: .
          github-token: ${{ secrets.GITHUB_TOKEN }}
          run-id: ${{ github.event.workflow_run.id }}
   ```
   (`download-artifact@v7` supports `run-id`; if the version pin differs in
   the repo — scrape.yml uses `actions/upload-artifact@v7` — mirror that
   major version.)

**Verify**: `grep -n "workflow_run\|download-artifact" .github/workflows/pages.yml` → both present.

### Step 2: Make the ingest steps conditional fallbacks

Change the two ingest steps to run **only when the artifact download did
not happen or the artifacts are missing**:

- Add `if: ${{ steps.download-artifacts.outcome == 'skipped' || !steps.download-artifacts.outcome }}`-style condition, or the cleaner
  artifact-presence check: keep `continue-on-error: true` and prepend a
  guard in the `run:` script:
  ```yaml
        run: |
          if [ -f artifacts/normalized.jsonl ] && [ -f artifacts_kino/normalized.jsonl ]; then
            echo "Artifacts present from scrape.yml; skipping re-ingest"
            exit 0
          fi
          mkdir -p artifacts site
          python -m polla_app run --sources pozos ... (unchanged)
  ```
  Do the same for the Kino step (check `artifacts_kino/normalized.jsonl`).
  Use the file-guard approach — it is robust to both schedule-triggered
  (no artifact) and workflow_run-triggered (artifact present) runs, and to
  a failed scrape (no artifact → re-ingest happens as today).

**Verify**: read the modified YAML — both ingest `run:` blocks start with
the guard; `grep -c "if \[ -f artifacts" .github/workflows/pages.yml` → 2.

### Step 3: Keep the fallback path intact

Confirm the `site` step still uses `--previous-data site/data.json` and the
cache restore step still runs before it (so a failed ingest + failed
artifact still deploys last-good data).

**Verify**: `grep -n "previous-data\|site/data.json" .github/workflows/pages.yml` → both present.

## Test plan

- No unit tests. Verification is CI behavior after merge: a `workflow_run`
  pages run shows "Artifacts present ... skipping re-ingest" in logs and
  deploys; a manual `workflow_dispatch` of pages.yml (no artifact) re-ingests
  as before. The executor should run the YAML through `yaml.safe_load` and
  note any syntax errors.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "workflow_run" .github/workflows/pages.yml` → trigger present with the correct workflow name (verified against scrape.yml's `name:`)
- [ ] `grep -n "download-artifact" .github/workflows/pages.yml` → step present, gated on `workflow_run`
- [ ] `grep -c "if \[ -f artifacts" .github/workflows/pages.yml` → 2 guards
- [ ] `grep -n "previous-data" .github/workflows/pages.yml` → unchanged fallback
- [ ] YAML parses (`yaml.safe_load`)
- [ ] `ruff check polla_app tests` and `mypy polla_app tests` exit 0 (no app changes)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The scrape.yml workflow `name:` differs from "Ingest Alternative Sources" — use the actual name in the trigger.
- `actions/download-artifact` at the repo's pinned major doesn't support `run-id` — report and use the workflow-run-aware alternative the version supports.
- pages.yml's structure differs from the excerpt (e.g. ingest steps have different ids) — adapt the guard placement to the live ids and note it.

## Maintenance notes

- The daily double-ingest stops on merge; upstream load halves. If draw data ever needs to be fresher than the last ingest, re-enable the 14:00 ingest selectively (e.g. only when `--previous-data` differs) — not now.
- Plan 030 (state per game) may add `--state-file` to the site step; keep that flag regardless of this plan.
- When scrape.yml's artifact retention changes, revisit the download step's expectations.
