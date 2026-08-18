# Plan 033: Unify the playwright pin and automate chromium parity + browser caching

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- requirements.txt pyproject.toml .github/workflows/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/032-deps-lockfile.md (both touch manifests/workflows; run 032 first)
- **Category**: migration
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

The chromium browser binary the scraper's fallback relies on is kept in
sync with scrapling's driver by a manual pin: commit `4615c93` pinned
`playwright==1.61.0` because `scrapling[fetchers]`'s unbounded
`patchright>=1.61.2`/`playwright>=1.61.0` extra pulled a newer chromium
revision than scrapling expected, so the browser was never found in CI.
Two manifest policies exist (`pyproject.toml:14` `>=1.61.0,<1.62` vs
`requirements.txt:6` `==1.61.0`) and the parity check is a memory item —
the next scrapling bump breaks the fallback again silently. Separately,
three nightly workflows re-download ~170MB of chromium on every run
(`scrape.yml:95`, `update.yml:38`, `pages.yml:37`), with no cache.

Verified parity today: playwright 1.61.0 and patchright 1.61.2 both expect
chromium revision 1228 (checked both `browsers.json` in the venv).

## Current state

- `pyproject.toml:14` — `"playwright>=1.61.0,<1.62"`
- `requirements.txt:6` — `playwright==1.61.0`
- `.github/workflows/scrape.yml:95`, `update.yml:38`, `pages.yml:37`:
  `python -m playwright install chromium --with-deps || python -m playwright install chromium`
- No `actions/cache` for `~/.cache/ms-playwright` in any workflow; the only
  cache configured is pip (`setup-python` `cache: 'pip'`).
- `polla_app/sources/browser.py` — the StealthyFetcher construction is the
  only place scrapling's driver is used (availability-gated).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Read chromium revisions | `python -c "import json,pathlib; d=pathlib.Path('venv/lib/python3.13/site-packages/scrapling/../patchright/browsers.json'); print(d)"` — find the real path first with `python -c "import patchright, os; print(os.path.dirname(patchright.__file__))"` | prints the path to `browsers.json` |
| Verify pin agreement | `grep -n "playwright" requirements.txt pyproject.toml` | identical strings |
| Tests | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `pyproject.toml` — unify the playwright pin with requirements.txt
- `.github/workflows/scrape.yml`, `update.yml`, `pages.yml` — chromium cache step + (for scrape.yml) a parity check step
- `docs/` — a one-line note in the doc that mentions the pin rationale (check `docs/SLOs.md` or README's stack section; add a sentence only if a natural spot exists)

**Out of scope** (do NOT touch, even though they look related):
- The scrapling upper bound and lockfile (plan 032)
- Removing the pin entirely — the pin is the parity guard; do not weaken it
- `requirements.lock` regeneration — if plan 032 has landed, the lock already contains `playwright==1.61.0`; re-run `pip-compile` only if the manifest edit changes the lock (it shouldn't)

## Git workflow

- Branch: `advisor/033-playwright-parity`
- Commit message style: `build(deps): pin unificado de playwright + chequeo de paridad chromium + caché`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Unify the manifest pin

Set `pyproject.toml:14` to `"playwright==1.61.0"` (same as requirements.txt).

**Verify**: `grep -n "playwright" requirements.txt pyproject.toml` → both
`playwright==1.61.0`.

### Step 2: Add the chromium cache to the three workflows

In `scrape.yml`, `update.yml`, and `pages.yml`, insert an
`actions/cache@v4`-style step before the `playwright install` line (use the
same cache action version the workflows already use — `actions/cache/restore@v5`
in pages.yml/scrape.yml; mirror the local style; `actions/cache@v4` is fine
for the combined restore/save in one step). Cache:

```yaml
      - name: Cache playwright chromium
        uses: actions/cache@v4
        with:
          path: ~/.cache/ms-playwright
          key: ms-playwright-${{ runner.os }}-1228
```

(The key encodes the chromium revision 1228 — bump it whenever the pin
moves. A miss just re-downloads; correctness is preserved by the parity
check in Step 3.)

**Verify**: `grep -n "ms-playwright" .github/workflows/scrape.yml .github/workflows/update.yml .github/workflows/pages.yml` → one cache step each, key contains `1228`.

### Step 3: Add the parity check to scrape.yml's ingest job

In `scrape.yml`, in the job that installs dependencies and runs the
pipeline (the `ingest` job), after the `playwright install` step, add a
check that the chromium revisions agree between the installed playwright
and scrapling's driver. Portable snippet:

```yaml
      - name: Verify chromium parity (playwright vs scrapling)
        run: |
          python - <<'PY'
          import json, pathlib, sys
          import playwright
          import patchright

          def revision(driver):
              p = pathlib.Path(driver.__file__).parent / "browsers.json"
              data = json.loads(p.read_text(encoding="utf-8"))
              for b in data.get("browsers", []):
                  if b.get("name") == "chromium":
                      return b["revision"]
              raise SystemExit("chromium not in browsers.json")

          rev_pw = revision(playwright)
          rev_pr = revision(patchright)
          print(f"playwright chromium={rev_pw} patchright chromium={rev_pr}")
          if rev_pw != rev_pr:
              raise SystemExit(f"CHROMIUM PARITY BROKEN: playwright {rev_pw} != patchright {rev_pr}")
          PY
```

(If `patchright` is not installed in the scrape env as a direct dep, use
scrapling's METADATA or install it via the fetchers extra — verify with
`pip show patchright` after the deps install step; the extra is declared by
`scrapling[fetchers]`.)

**Verify**: run the snippet locally in the venv → prints both revisions and exits 0 (both 1228 today).

## Test plan

- No unit tests; verification is the parity snippet (Step 3) and CI runs
  showing the cache hit.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "playwright" requirements.txt pyproject.toml` → identical `==1.61.0` pins
- [ ] `grep -n "ms-playwright" .github/workflows/*.yml` → cache steps in all three workflows with key `ms-playwright-...-1228`
- [ ] `grep -n "parity" .github/workflows/scrape.yml` → the check step exists
- [ ] The parity snippet exits 0 locally (both drivers at revision 1228)
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The two pins cannot be made identical because some install path (e.g. `pip install -e .` in docs.yml/health.yml) requires a range — report the conflict.
- `patchright` isn't reachable in the scrape job env — report; the parity check needs the fetchers extra installed (verify it is, per the note in Step 3).
- The local drivers disagree on revision (venv drift) — report the numbers; do not hand-edit the pin beyond unifying the two manifests.

## Maintenance notes

- On every scrapling or playwright bump: re-run the parity snippet, update the cache key revision, and re-pin. The check in scrape.yml makes a silent drift fail loudly.
- The cache key is revision-based on purpose: a stale cache (wrong revision) is worse than no cache, so the key must change with the pin.
- Plan 032's lockfile pins playwright==1.61.0 already; after this plan, `pip-compile` output should be unchanged — if not, regenerate and commit together.
