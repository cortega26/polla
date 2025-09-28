# Contributing

Thanks for your interest in contributing! This project focuses on a small, well‑tested pipeline. Please keep changes minimal and behavior‑preserving unless explicitly discussed.

## Development Setup

1. Create a virtual environment and install dependencies:

```bash
pip install -r requirements-dev.txt
```

2. Run the test suite:

```bash
pytest -q
```

3. Lint and format:

```bash
ruff check .
black .
```

## Project Conventions

- Python 3.10+ only.
- Keep functions small and single‑purpose; add docstrings for non‑obvious logic.
- Prefer `Mapping`/`Iterable` in function signatures for read‑only inputs.
- Do not log secrets. Prefer structured logs for errors via `ScriptError`.
- Preserve the public API (`run_pipeline`, `publish_to_google_sheets`).

## Running the CLI

```bash
python -m polla_app --help
python -m polla_app pozos
python -m polla_app run --sources pozos --normalized artifacts/normalized.jsonl --comparison-report artifacts/comparison_report.json --summary artifacts/run_summary.json
```

To publish (dry‑run):

```bash
python -m polla_app publish --normalized artifacts/normalized.jsonl --comparison-report artifacts/comparison_report.json --summary artifacts/run_summary.json --dry-run
```

## Benchmarks

Micro‑benchmarks for parser performance:

```bash
python scripts/benchmark_pozos_parsing.py
```

## Pull Requests

- Include tests for new behavior or bug fixes.
- Keep diffs focused. If refactoring, avoid changing functionality.
- Ensure `ruff`, `mypy`, and `pytest` pass locally before submitting.

