# Plan 014: `polla site` forwards `--previous-data` to the written payload

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 9180c98..HEAD -- polla_app/__main__.py polla_app/site.py docs/API.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `9180c98`, 2026-08-15

## Why this matters

Commit `9180c98` ("fix(site): conservar la sección del juego fallido en
data.json") added `--previous-data` support to `build_site_payload` so the
dashboard keeps the last good section of a game whose ingest failed. But the
CLI never forwards `previous_payload` to `write_site_data`, which rebuilds the
payload from scratch — the written `data.json` still blanks the failed game.
Verified by execution: with `--previous-data` pointing at a payload containing
a Kino section and a missing Kino input file, the generated `data.json` came
out with `"kino": null`. The whole purpose of the fix is dead code at the CLI
level, and `.github/workflows/pages.yml` now passes the flag expecting it to
work.

## Current state

- `polla_app/__main__.py` — the `site` click command (lines 345–385). It
  parses `--previous-data` into `previous_payload`, builds `payload` WITH it
  (used only for stats prizes/prices), then calls `write_site_data` WITHOUT it:

  ```python
  # polla_app/__main__.py:355-384 (abridged)
  previous_payload: dict[str, Any] | None = None
  if previous_data:
      try:
          previous_payload = json.loads(Path(previous_data).read_text(encoding="utf-8"))
      except FileNotFoundError:
          previous_payload = None
  payload = build_site_payload(
      loto_path=Path(normalized),
      kino_path=Path(normalized_kino) if normalized_kino else None,
      summary_path=Path(summary) if summary else None,
      previous_payload=previous_payload,
  )

  stats_path = Path(output).parent / "stats.json"
  try:
      write_site_stats(
          stats_url or resolve_stats_url(),
          stats_path,
          prizes=payload.get("current_prizes_clp") or {},
          prices=payload.get("current_prices") or {},
      )
  except Exception as exc:  # noqa: BLE001 - stats are auxiliary; dashboard still works
      LOGGER.warning("Could not sync game statistics: %s", exc)

  write_site_data(
      loto_path=Path(normalized),
      output=Path(output),
      kino_path=Path(normalized_kino) if normalized_kino else None,
      summary_path=Path(summary) if summary else None,
  )  # <-- previous_payload NOT forwarded: data.json loses the fallback
  ```

- `polla_app/site.py:126-146` — `write_site_data` already accepts
  `previous_payload: Mapping[str, Any] | None = None` and forwards it to
  `build_site_payload`. No change needed there.

- `docs/API.md:118` — stale signature:
  `polla_app.site.write_site_data(loto_path, output, kino_path=None, summary_path=None)`
  (missing the new `previous_payload` kwarg).

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Test      | `python -m pytest tests/test_site.py -q` | all pass            |
| Lint      | `ruff check polla_app tests`   | exit 0              |
| Format    | `black --check polla_app tests` | exit 0            |
| Typecheck | `mypy polla_app`            | exit 0, no issues   |

## Scope

**In scope** (the only files you should modify):
- `polla_app/__main__.py` — forward the kwarg in the `site` command
- `docs/API.md` — refresh the `write_site_data` signature line

**Out of scope** (do NOT touch, even though they look related):
- `polla_app/site.py` — `write_site_data`/`build_site_payload` already
  support the kwarg; changing them is unnecessary.
- `tests/test_site.py` — new CLI-level tests land in plan 015; if you write
  tests here, restrict yourself to the existing function-level style.
- `.github/workflows/pages.yml` — already passes `--previous-data`.

## Git workflow

- Branch: `advisor/014-site-previous-data`
- Commit style (repo convention, from `git log --oneline`):
  `fix(site): reenviar previous_payload a write_site_data en el comando site`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Forward `previous_payload` to `write_site_data`

In `polla_app/__main__.py`, inside the `site` command, add the kwarg to the
final `write_site_data(...)` call:

```python
write_site_data(
    loto_path=Path(normalized),
    output=Path(output),
    kino_path=Path(normalized_kino) if normalized_kino else None,
    summary_path=Path(summary) if summary else None,
    previous_payload=previous_payload,
)
```

Leave the `build_site_payload` call above untouched (it feeds the stats
merges). Do not refactor the double payload build — that is out of scope.

**Verify**: `python -m pytest tests/test_site.py -q` → all pass, then run the
manual reproduction below. In a scratch dir (e.g. `/tmp/opencode/sitebug`):

```bash
printf '{"sorteo":5465,"fecha":"2026-08-16","confidence":"full","fuente":"openloto","pozos_proximo":{"Loto Clásico":620000000}}\n' > loto.jsonl
printf '{"decision":{"status":"publish"},"publish_reason":"x"}\n' > summary.json
echo '{"loto":{"sorteo":5465,"pozos_clp":{"Loto Clásico":620000000}},"kino":{"sorteo":3266,"pozos_clp":{"Kino":8370000000}}}' > previous.json
POLLA_STATS_URL="file:///nonexistent.csv" python -m polla_app site \
  --normalized loto.jsonl \
  --normalized-kino /tmp/opencode/sitebug/nonexistent_kino.jsonl \
  --summary summary.json \
  --previous-data previous.json \
  --output data.json
python -c "import json;d=json.load(open('data.json'));assert d['kino'] is not None;print('OK kino section:', d['kino']['sorteo'])"
```

Expected final output: `OK kino section: 3266` (before the fix it was
`None`). Note: `POLLA_STATS_URL=file:///...` is intentionally invalid so the
stats sync fails harmlessly and the command still exits 0 — the stats failure
path also works as a side-check.

### Step 2: Refresh the docs signature

In `docs/API.md:118`, update the line to:

```
`polla_app.site.write_site_data(loto_path, output, kino_path=None, summary_path=None, previous_payload=None)`
```

**Verify**: `grep -n "previous_payload" docs/API.md` → shows the updated line.

## Test plan

No new tests in this plan (plan 015 adds the CLI-level regression tests).
Existing suites must stay green:

- `python -m pytest -q` → 226 passed, 1 skipped (count may shift by ±1 if
  other plans landed).

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python -m pytest -q` exits 0
- [ ] The manual reproduction prints `OK kino section: 3266`
- [ ] `ruff check polla_app tests` exits 0
- [ ] `black --check polla_app tests` exits 0
- [ ] `mypy polla_app` exits 0
- [ ] `grep -n "previous_payload" polla_app/__main__.py` shows the kwarg in
      the `write_site_data(...)` call
- [ ] `docs/API.md:118` lists `previous_payload=None`
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- The `site` command in `polla_app/__main__.py` does not match the excerpts
  above (codebase drifted since this plan was written).
- The manual reproduction still prints `None` after the fix — the payload
  reuse may be broken elsewhere; report instead of hacking around it.
- A verification command fails twice after a reasonable fix attempt.
- The fix appears to require touching a file outside the in-scope list.

## Maintenance notes

- The `site` command builds the payload twice per run (once for stats, once
  inside `write_site_data`) — wasteful but harmless; a future refactor could
  write the already-built payload directly.
- If `build_site_payload` gains more fallback knobs, `write_site_data` must
  stay in lockstep — it is the only path that reaches disk.
- A reviewer should confirm the stats `payload` (with previous data) and the
  written `data.json` (now with previous data) are consistent for the
  same-game-failure scenario.
