# Plan 037: Reconcile stale docs — API.md, CHANGELOG, docs/implementation/, observability.md

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- docs/ CHANGELOG.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: LOW (docs only; no code changes)
- **Depends on**: none
- **Category**: docs
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Three doc families are actively wrong, and one de-facto API is undocumented:

1. `docs/API.md:32` says `run_pipeline` returns "status (publish/skip/quarantine), publish_reason, and max_deviation" — the real summary (pipeline.py:493-504) has `publish` (bool), `decision` (with `status`/`confidence`/`reason`), `publish_reason`, `prizes_changed`, and paths; `max_deviation` lives in the comparison report, and `include_prices` (pipeline.py:742) is undocumented.
2. `CHANGELOG.md:35` claims "`--sources all` ahora incluye Loto y Kino" — `pipeline.py:43-48` raises `ValueError` for `"all"` (and plan 020 extends the rejection).
3. `docs/implementation/IMPLEMENTATION_BACKLOG.md` is headed "polla v3.1.0" (line 3), describes removed components (`get_pozo_resultadosloto` at line 377, workflow `sync-main-to-master.yml` at line 719), and lists FEAT-03/FEAT-05 as `todo` — the only place a reader finds "what's next" describes a repo state that no longer exists. `docs/observability.md:16,20-21,40,45,51,56` document the span `pozos_only`; the only production span is `ingestion_orchestration` (pipeline.py:558; obs.py:121's `pozos_only` is a docstring-only example).
4. The artifact schemas that scrape.yml/publish.py/site.py consume (normalized.jsonl, comparison_report.json, run_summary.json) have no field-level reference anywhere.

## Current state

- `polla_app/pipeline.py:493-504` — `_build_summary_payload` (verify the exact keys; the audit shows `publish`, `decision{status,confidence,total_categories,mismatched_categories,reason}`, `publish_reason`, `prizes_changed`, plus artifact paths).
- `polla_app/pipeline.py:742` — `include_prices: bool = False` parameter.
- `polla_app/pipeline.py:43-48` — `"all"` rejected with `ValueError`.
- `polla_app/pipeline.py:558` — `with span("ingestion_orchestration", log_event, attrs={"sources": requested_sources})`.
- `tests/test_contracts.py:14-128` — the artifact field lists asserted by tests; use it as the source of truth for the schema doc.
- `docs/implementation/` — a directory with IMPLEMENTATION_BACKLOG.md (and possibly other files — list them before editing).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Doctests | `pytest --doctest-glob='*.md' README.md docs -q` | 0 failed (exit 0 or 5 for no tests collected) |
| Verify summary keys | `grep -n "publish\|prizes_changed\|publish_reason" polla_app/pipeline.py \| head -20` | matches the doc you write |
| Lint | `ruff check polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `docs/API.md` — fix the `run_pipeline` return description; add `include_prices`
- `CHANGELOG.md` — correct or remove the `--sources all` entry
- `docs/implementation/IMPLEMENTATION_BACKLOG.md` — stamp as historical (or move guidance to plans/README.md reference)
- `docs/observability.md` — fix the span name
- `docs/API.md` — add a short artifact-schema section (field lists from `tests/test_contracts.py`)

**Out of scope** (do NOT touch, even though they look related):
- Deleting `docs/implementation/` — preserve history; only re-label
- Any code change to emit a `pozos_only` alias span
- README/CONTRIBUTING (plan 025 covers those)
- plans/README.md — read it to reference it, do not restructure

## Git workflow

- Branch: `advisor/037-docs-reconcile`
- Commit message style: `docs: alinear API.md, CHANGELOG, observability.md y marcar docs/implementation como histórico`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Fix `docs/API.md` run_pipeline description

Read the current section around API.md:25-40. Rewrite the return-shape
description to match `_build_summary_payload`'s actual keys (read
pipeline.py:481-504 first and transcribe the real keys). Add a sentence on
the `include_prices` parameter (pipeline.py:742): "Cuando
`include_prices=True`, se obtienen los precios vivos del juego y se adjuntan
al registro normalizado."

**Verify**: `grep -n "max_deviation\|status" docs/API.md` → the wrong claims
gone; `grep -n "include_prices" docs/API.md` → present.

### Step 2: Correct the CHANGELOG entry

Read CHANGELOG.md around line 35. Replace the "`--sources all` ahora incluye
Loto y Kino" claim with an accurate entry, e.g.: "`--sources all` rechazado:
cada juego (Loto/Kino) se ingesta en una invocación separada." Keep the
CHANGELOG style (check nearby entries for date/format conventions).

**Verify**: `grep -n '"all"' CHANGELOG.md` → no stale claim (or the corrected
wording).

### Step 3: Stamp docs/implementation/ as historical

Add a prominent header at the top of `docs/implementation/IMPLEMENTATION_BACKLOG.md`
(after the title):

```
> **Estado: HISTÓRICO.** Este backlog describe el repositorio en su estado
> v3.1.0 y NO refleja el código actual. Para el backlog vivo, ver
> `plans/README.md` (y `CHANGELOG.md` para la historia de cambios).
```

Do not edit the body (preserve the historical record).

**Verify**: `head -8 docs/implementation/IMPLEMENTATION_BACKLOG.md` → shows the banner.

### Step 4: Fix observability.md span name

Replace every `pozos_only` occurrence in `docs/observability.md` with
`ingestion_orchestration` (verify there is no other real span name in
production: `grep -rn 'span("' polla_app/` → only pipeline.py:558).

**Verify**: `grep -n "pozos_only" docs/observability.md` → no matches;
`grep -n "ingestion_orchestration" docs/observability.md` → present.

### Step 5: Add the artifact-schema section to API.md

Append a section "Esquemas de artefactos" to `docs/API.md` documenting the
three files as a field list derived from `tests/test_contracts.py:14-128`
(read it and transcribe the asserted keys; do not invent fields). For each
file list the top-level keys, e.g.:

```
artifacts/normalized.jsonl (una línea por juego, ver plan 024):
  sorteo, fecha, fuente, confidence, premios, pozos_proximo, provenance,
  precios (cuando include_prices=True), game (tras plan 030)

artifacts/comparison_report.json: run{id,generated_at,sources,...},
  last_draw{sorteo,fecha}, decision{status,confidence,...}, mismatches[]

artifacts/run_summary.json: publish (bool), decision{...},
  publish_reason, prizes_changed, paths
```

(Transcribe exact keys from the code/tests; mark additive fields that
depend on unlanded plans as "si aplica".)

**Verify**: `grep -n "Esquemas de artefactos" docs/API.md` → present.

## Test plan

- No unit tests. Verification: doctest suite passes; grep checks per step.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -n "max_deviation" docs/API.md` → only where it truthfully describes the comparison report
- [ ] `grep -n "include_prices" docs/API.md` → present
- [ ] `grep -n "pozos_only" docs/observability.md` → no matches
- [ ] `grep -n "HISTÓRICO" docs/implementation/IMPLEMENTATION_BACKLOG.md` → banner present
- [ ] `grep -n "Esquemas de artefactos" docs/API.md` → section present with keys matching `tests/test_contracts.py`
- [ ] `pytest --doctest-glob='*.md' README.md docs -q` → 0 failed
- [ ] `ruff check polla_app tests` exits 0 (no code changes)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The `run_pipeline` summary keys differ from the excerpt (read pipeline.py:481-504 and transcribe the real ones — if they differ substantially, report rather than guessing).
- `docs/implementation/` contains files besides IMPLEMENTATION_BACKLOG.md that also claim to be current — list them; add the banner to each only with the reviewer's OK.
- A doctest in the docs you edit fails — fix only the doc text, never add code exceptions.

## Maintenance notes

- The artifact-schema section is the reference for scrape.yml's parse steps and plans 024/030's record changes; keep it in sync when those land.
- When plans/README.md changes (status flips), the "backlog vivo" pointer stays correct automatically.
- Future contract changes: update docs/API.md schema section in the same change (per AGENTS.md's Contracts section).
