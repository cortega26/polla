# SLOs, Error Budgets, and Alerts

This project is a CLI/pipeline. SLOs apply to runs of `polla_app` commands and their artifacts.

## Service Level Objectives (SLOs)

- Availability (monthly): ≥ 99.0% of scheduled health checks report `status=pass`.
- Error rate (per week): < 1% of pipeline runs exit non‑zero due to non‑config errors.
- Latency (per run):
  - `pozos` mode: p95 ≤ 15s (online), p99 ≤ 30s.
  - `publish` dry‑run: p95 ≤ 2s.

Notes:
- Runs failing due to missing credentials or robots disallowance are counted as user/config errors and excluded from error rate.

## Error Budgets

With 99% availability SLO on a 30‑day month:
- Budget = 1% of 30 days ≈ 7h 12m of failed health checks.

Burn policies:
- Warning: > 50% budget burned over trailing 7 days.
- Page: > 100% budget burned over trailing 3 days.

## Alerts

- Health checks failing across both sources (`status=fail`) for ≥ 3 consecutive runs: page.
- Fast burn: ≥ 20% budget in ≤ 2 hours: page.
- Degraded (`status=degraded`) for ≥ 6 consecutive runs: ticket.

Alerts should include context: source availability, response codes, and last change in `ALT_SOURCE_URLS`.

## Health Checks

- `python -m polla_app health` prints JSON with `status: pass|degraded|fail` and per‑source timings.
- CI runs offline doctests; scheduled checks can run `health --online` from a networked runner.

Example:

```bash
python -m polla_app health --online --timeout 5 | jq .
```

## Load, Soak, and Chaos Tests

- Load: parser micro‑benchmarks (`scripts/benchmark_pozos_parsing.py`).
- Soak: run pipeline in a loop with stable inputs; ensure idempotent outcomes and no errors.
- Chaos: simulate one source failing; pipeline should remain `publish` or `degraded` depending on mode (covered in tests).

## Observability

- Structured logs: pipeline emits JSON lines to `logs/run.jsonl` with `event` and decision fields.
- Error taxonomy: use `ScriptError`/`ConfigError`/`RobotsDisallowedError` to classify issues.

