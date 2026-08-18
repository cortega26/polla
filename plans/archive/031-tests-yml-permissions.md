# Plan 031: Drop write permissions from `tests.yml` and align AGENTS.md with reality

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- .github/workflows/tests.yml AGENTS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: MED (behavior change only for PR-triggered runs; no functional test loss)
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

`tests.yml` declares `permissions: contents: write` (plus `id-token: write`)
at the workflow level and triggers on `pull_request` — i.e., **fork PRs**.
The checkout step uses `ref: ${{ github.head_ref }}` (tests.yml:16), so
PR-controlled code runs with a write-scoped `GITHUB_TOKEN` injected. A
malicious fork PR could read the token from its own job environment and
push commits to the repo. The workflow never actually writes anything — the
write permission exists only to satisfy AGENTS.md's claim that tests.yml
"automatically fixes and commits minor formatting issues" (AGENTS.md:173),
which the workflow does not implement (it only runs `black --check` and
`ruff check`). This plan drops the permission to `contents: read` and
rewrites the AGENTS.md claim to match reality.

## Current state

`.github/workflows/tests.yml:1-9`:

```yaml
name: tests

on:
  push:
  pull_request:

permissions:
  contents: write
  id-token: write
```

`.github/workflows/tests.yml:14-17`:

```yaml
      - name: Checkout
        uses: actions/checkout@v6
        with:
          ref: ${{ github.head_ref }}
```

The only write-ish step downstream is the codecov upload
(`codecov-action@v6` with `use_oidc: true`, `fail_ci_if_error: false`) —
codecov uses OIDC via `id-token`, not the repo token; the `contents` write
is unused.

`AGENTS.md` ("Guardrails & Quality Policies (MANDATORY)"):

```
- **CI Enforcement**:
  - `tests.yml`: Automatically fixes and commits minor formatting issues to keep the history clean.
  - `scrape.yml` (Production): Performs strict checks (`--check`) without auto-fixing ...
```

The `scrape.yml` description is accurate; the `tests.yml` one is not.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| YAML sanity | `python -c "import yaml, pathlib; print(yaml.safe_load(pathlib.Path('.github/workflows/tests.yml').read_text()))"` | prints the parsed dict (pyyaml may be absent — then skip; CI validates YAML) |
| Verify permissions | `grep -n -A4 "^permissions:" .github/workflows/tests.yml` | shows `contents: read` |
| Verify token usage | `grep -rn "GITHUB_TOKEN\|contents: write" .github/workflows/tests.yml` | no matches after the change |
| Lint (repo untouched) | `ruff check polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `.github/workflows/tests.yml` — permissions block
- `AGENTS.md` — the CI-enforcement bullet about tests.yml

**Out of scope** (do NOT touch, even though they look related):
- Adding the auto-fix+commit step that AGENTS.md currently promises — a deliberate alternative, but it would require the write token; the safer direction chosen here is to remove the promise. If the operator wants auto-fix, that's a separate plan.
- The `id-token: write` — keep it (codecov OIDC needs it).
- Other workflows' permissions.

## Git workflow

- Branch: `advisor/031-tests-yml-permissions`
- Commit message style: `ci(security): tests.yml con solo contents: read; AGENTS.md refleja la realidad`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Narrow the permissions

In `.github/workflows/tests.yml`, change:

```yaml
permissions:
  contents: write
  id-token: write
```

to:

```yaml
permissions:
  contents: read
  id-token: write
```

**Verify**: `grep -n -A4 "^permissions:" .github/workflows/tests.yml` →
`contents: read`.

### Step 2: Rewrite the AGENTS.md claim

Replace the bullet:

```
  - `tests.yml`: Automatically fixes and commits minor formatting issues to keep the history clean.
```

with:

```
  - `tests.yml`: Enforces formatting with strict `--check` (black + ruff) and fails the build on any drift; no auto-commit.
```

Keep the surrounding text (the scrape.yml bullet and the Fail-Fast note) unchanged.

**Verify**: `grep -n "tests.yml" AGENTS.md` → the bullet shows the new text.

## Test plan

- No unit tests. Verification: the workflow YAML parses (CI will run it on
  push), and the repo's checks stay green.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n -A4 "^permissions:" .github/workflows/tests.yml` shows `contents: read`
- [ ] `grep -n "Automatically fixes" AGENTS.md` → no matches
- [ ] `ruff check polla_app tests` and `mypy polla_app tests` exit 0 (repo unchanged otherwise)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The workflow contains any step that genuinely needs `contents: write` (e.g. an auto-commit step added since the audit) — report; the plan's premise fails and the operator must choose between keeping the write token (with the fork-PR risk) or removing the step.
- `AGENTS.md` phrasing differs from the excerpt — adapt the edit to the live text and note it.

## Maintenance notes

- If an auto-fix+commit step is ever added to tests.yml, it MUST be gated to same-repo `push` events only (never fork PRs) and use a scoped PAT, not the default token.
- The `ref: head_ref` checkout on PRs remains — that's fine now that the token is read-only; the residual risk (fork PR code running in CI) is the standard GitHub Actions model.
- Plan 019's credential-scan step (if landed) coexists with this one — both harden tests.yml without conflict.
