# Observability (Tracing, Metrics, Logging)

This project emits structured JSON logs with correlation IDs, simple trace spans, and metric events. No external agents are required.

## Correlation IDs

- Every pipeline run generates a `run_id` which is set as `correlation_id` in all structured log entries from that run.
- Example log line (JSONL in `logs/run.jsonl`):

```json
{"event":"pipeline_start","run_id":"...","sources":["pozos"],"timestamp":"2025-01-01T00:00:00+00:00","correlation_id":"..."}
```

## Spans

- Minimal spans are emitted around major phases (e.g., `pozos_only`).
- Example:

```json
{"event":"span_start","name":"pozos_only","attrs":{"sources":["pozos"]},"timestamp":"...","correlation_id":"..."}
{"event":"span_end","name":"pozos_only","ms":1234,"timestamp":"...","correlation_id":"..."}
```

## Metrics

- Metric events are emitted via the same log stream, e.g. at the end of the pipeline:

```json
{"event":"metric","name":"pipeline_run","kind":"counter","value":1,"tags":{"decision":"publish","publish":true},"timestamp":"...","correlation_id":"..."}
```

## Redaction

- Sensitive fields are redacted automatically before writing logs (keys containing `password`, `secret`, `token`, `credential`, `apikey`, `api_key`, `key`, excluding URL-like `fuente`/`url`). Long opaque tokens are masked.

## Sample Dashboards

- Grafana + Loki (or any JSON log backend):
  - Panel 1: `count_over_time({event="pipeline_complete"}[24h])` grouped by `decision`.
  - Panel 2: `quantile_over_time(0.95, {event="span_end", name="pozos_only"} | unwrap ms [24h])`.
  - Panel 3: Error count: `{event="error"}` split by `error_code`.

- Example Loki LogQL (conceptual):
  - `sum by (decision) (count_over_time({event="pipeline_complete"}[1h]))`
  - `histogram_quantile(0.95, sum by (le) (rate({event="span_end", name="pozos_only"} | unwrap ms | __error__="" [5m])))`

## Alert Rules (examples)

- High error rate: `sum(rate({event="error"}[5m])) > 0.1`
- Pipeline failing: `sum(rate({event="pipeline_complete", decision!~"publish|publish_forced"}[10m])) > 0`
- Latency p95 exceeded: `quantile_over_time(0.95, {event="span_end", name="pozos_only"} | unwrap ms [15m]) > 15000`

## Verification Checklist

- [ ] Run `python -m polla_app run --log-file logs/run.jsonl` and confirm log lines contain `correlation_id`.
- [ ] Confirm span start/end appear with `name="pozos_only"` and `ms` value.
- [ ] Confirm a `metric` event `name="pipeline_run"` is present with decision tags.
- [ ] Verify redaction by logging a payload containing a key like `token`: it should be masked in the log output.
- [ ] CI doctests and unit tests pass.

