# Plan 046: Remove dead root re-exports, enforce the parse-SLO benchmark, share test helpers

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/__init__.py .github/workflows/ Makefile README.md tests/ scripts/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Three small hygiene gaps:

1. **Dead root re-exports** — `polla_app/__init__.py:6-10` re-exports
   `ScriptError`, `run_pipeline`, `publish_to_google_sheets`,
   `get_pozo_openloto` and lists them in `__all__`. Every importer in the
   repo (production and tests) uses `from polla_app import <module>` or
   submodule paths — `grep -rn "from polla_app import "` shows zero uses of
   the root symbols. Dead public surface invites wrong imports and gives a
   false compatibility promise.
2. **Unenforced parse-SLO guard** — `README.md:126` claims
   `scripts/benchmark_pozos_parsing.py` "asegura" (guarantees) the <150ms
   median parsing SLO. No CI workflow or Makefile target runs it (verified:
   `grep -rn "benchmark" .github/workflows/ Makefile` → zero hits). The
   guard the README promises does not exist; the SLO can regress silently.
3. **Test helpers duplicated** — tiny JSONL-writer/fixture helpers are
   re-implemented per test file: `_write_ndjson` (tests/test_site.py:31-37),
   `_fail_once` (tests/test_hardening_net.py:12-24), `run_cli`/
   `clean_artifacts` (tests/e2e/test_verification_suite.py:9-33). There is no
   `tests/conftest.py`, so each new test file re-invents the wheel and the
   e2e `clean_artifacts` arg list drifts from the CLI's options.

## Current state

`polla_app/__init__.py` (entire file):

```python
"""Utilities for Chilean Loto próximo pozo aggregation."""

__version__ = "3.2.0"

from .exceptions import ScriptError
from .pipeline import run_pipeline
from .publish import publish_to_google_sheets
from .sources import get_pozo_openloto

__all__ = [
    "ScriptError",
    "run_pipeline",
    "publish_to_google_sheets",
    "get_pozo_openloto",
]
```

`README.md:124-126`:

```markdown
## Rendimiento y Confiabilidad

- **Parsing de Alto Rendimiento**: `scripts/benchmark_pozos_parsing.py` asegura que mantengamos un tiempo medio de scraping inferior a **150ms**.
```

`scripts/benchmark_pozos_parsing.py` — verified working (0.07 ms/parse);
it imports `polla_app.sources.pozos` and times `_extract_amounts` +
`_extract_proximo_info` over the bundled fixtures. Run it once before
editing to confirm it still works on current HEAD.

Test helper examples: `tests/test_site.py:31-37` `_write_ndjson(path, records)`
writes `"\n".join(json.dumps(...))`; `tests/e2e/test_verification_suite.py:9-33`
`run_cli(args)` shells out to `python3 -m polla_app` and `clean_artifacts`
fixture builds an arg-path dict.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Benchmark (manual) | `python scripts/benchmark_pozos_parsing.py` | prints JSON with `total_ms` (< 150) |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/__init__.py` — remove the 4 re-exports and `__all__` (keep `__version__` and the module docstring)
- `.github/workflows/tests.yml` (or `scrape.yml` — see Step 2 decision) — add a benchmark step with a fail threshold
- `tests/conftest.py` (create) — shared `write_ndjson` helper
- `tests/test_site.py` — use the shared helper (delete local `_write_ndjson`)
- `tests/test_hardening_net.py` — move `_fail_once` to conftest only if it can be shared without a signature change; otherwise leave it (report the decision)
- `README.md:126` — reword to say the SLO is enforced in CI (once the step exists)

**Out of scope** (do NOT touch, even though they look related):
- `scripts/benchmark_pozos_parsing.py` — no edits (it works; the gap is enforcement, not the script)
- The `__version__` constant (single source of truth per AGENTS.md)
- Plan 021's new `tests/test_cli_commands.py` — if it lands first, it may reuse the conftest helper; otherwise keep this plan self-contained

## Git workflow

- Branch: `advisor/046-hygiene-cleanup`
- Commit message style: `chore: quitar re-exports muertos, enforce del SLO de parseo y helpers de test compartidos`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Remove the dead re-exports

In `polla_app/__init__.py`, delete the four `from ... import ...` lines and
the `__all__` list. Keep `__version__` and the docstring.

**Verify**: `grep -rn "from polla_app import run_pipeline\|from polla_app import publish_to_google_sheets\|from polla_app import get_pozo_openloto\|from polla_app import ScriptError" . --include='*.py'` → no matches (excluding `.venv`); `python -c "import polla_app; print(polla_app.__version__)"` → `3.2.0`; `pytest -q` → all pass.

### Step 2: Enforce the benchmark SLO in CI

Decision: add to `.github/workflows/tests.yml` (it already runs the parse
tests) a step after the pytest step:

```yaml
      - name: Enforce parsing SLO (<150ms)
        run: |
          ms=$(python scripts/benchmark_pozos_parsing.py | python -c "import sys,json; print(json.load(sys.stdin)['total_ms'])")
          echo "median parse: ${ms} ms"
          python - <<PY
          import os, sys
          if float(os.environ.get('MS', '999')) >= 150:
              sys.exit(f"parsing SLO exceeded: {os.environ['MS']}ms >= 150ms")
          PY
          # or the simpler inline form below
```

Simpler, robust form (prefer this — one shell, no nested python):

```yaml
      - name: Enforce parsing SLO (<150ms)
        run: |
          ms=$(python scripts/benchmark_pozos_parsing.py | sed -n 's/.*"total_ms": \([0-9.]*\).*/\1/p')
          echo "median parse: ${ms} ms"
          awk -v ms="$ms" 'BEGIN { if (ms >= 150) { print "::error::parsing SLO exceeded: " ms "ms"; exit 1 } }'
```

Check the benchmark script's exact JSON output shape first (run it) so the
`sed` extraction matches; if the output differs, adapt the extraction to the
real output. If `total_ms` is per-parse (it printed "Total por parse (4
combinaciones): 0.07 ms" plus a `total_ms` key), use the per-parse value —
read the script to pick the right key.

**Verify**: run the exact step command locally against the venv python →
prints the ms and exits 0.

### Step 3: Shared test helper

Create `tests/conftest.py`:

```python
"""Shared test helpers (autouse-safe, importable by any test module)."""

import json
from pathlib import Path
from typing import Any


def write_ndjson(path: Path, records: list[dict[str, Any]]) -> Path:
    """Write records as JSONL (one object per line)."""
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )
    return path
```

Then in `tests/test_site.py`, replace the local `_write_ndjson` definition
with `from conftest import write_ndjson` and update its 2-3 call sites
(`_write_ndjson(x, y)` → `write_ndjson(x, y)`).

**Verify**: `pytest tests/test_site.py -q` → all pass; `grep -n "def _write_ndjson" tests/test_site.py` → no match.

### Step 4: Move `_fail_once` if it ports cleanly

`tests/test_hardening_net.py:12-24` `_fail_once(failures, exc)` is a
generic "raise once then succeed" helper. Move it to `tests/conftest.py` as
`fail_once` and update the ~5 usages in that file. If any usage depends on
its closure shape in a way that makes the move awkward, leave it local and
report the decision (the value of sharing is marginal here).

**Verify**: `pytest tests/test_hardening_net.py -q` → all pass.

### Step 5: Reword the README SLO claim

Once the CI step exists, update `README.md:126`:

```markdown
- **Parsing de Alto Rendimiento**: `scripts/benchmark_pozos_parsing.py` (media < **150ms**, enforced en CI `tests.yml`).
```

**Verify**: `grep -n "benchmark_pozos_parsing" README.md` → shows the CI-enforcement wording.

## Test plan

- No new behavior tests; the CI step is the guard. The full suite must stay
  green after the helper moves (the two test files are the regression net).
- The benchmark step's own command is verified locally in Step 2.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `pytest -q` exits 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] `grep -c "from \." polla_app/__init__.py` → 0 (no imports remain); `python -c "import polla_app"` → exit 0
- [ ] `grep -n "Enforce parsing SLO\|benchmark_pozos_parsing" .github/workflows/tests.yml` → step present
- [ ] `grep -n "def write_ndjson\|def fail_once" tests/conftest.py` → present; `grep -rn "def _write_ndjson" tests/` → no match
- [ ] `grep -n "enforced en CI" README.md` → present
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Removing the root re-exports breaks an import somewhere you didn't expect (the grep is conclusive, but a downstream tool like an external script could import `polla_app.run_pipeline` — if you find one, report it; restore only that symbol).
- The benchmark output shape doesn't match the extraction in Step 2 — adapt to the real output, don't weaken the 150ms threshold.
- `tests/conftest.py` conflicts with plan 021's conftest plans — coordinate by adding to the same file (it's in scope; a duplicate `write_ndjson` definition would be a merge problem, report if 021 added one).

## Maintenance notes

- The CI SLO step makes README's claim true; when the benchmark or SLO changes, keep README and the step in sync.
- `__init__.py` now contains only `__version__` — the version single-source rule (AGENTS.md) is unaffected.
- Future test files should import `write_ndjson`/`fail_once` from `conftest` instead of re-implementing.