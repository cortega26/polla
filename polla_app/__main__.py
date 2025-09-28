"""CLI entry point for the alternative-source ingestion workflow."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import click

from .ingest import ingest_draw, list_24h_result_urls
from .pipeline import run_pipeline
from .publish import publish_to_google_sheets
from .sources import get_pozo_openloto, get_pozo_resultadosloto

LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()), format=LOG_FORMAT, datefmt=LOG_DATEFMT
    )


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Set the logging verbosity.",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str) -> None:
    """Command-line interface for polla_app."""

    _configure_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level


def _echo_json(payload: dict[str, Any], *, indent: int | None = 2) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=indent))


@cli.command()
@click.argument("url")
@click.option(
    "--source",
    default="t13",
    type=click.Choice(["t13", "24h"]),
    help="Source parser to use.",
)
@click.option("--no-pozos", is_flag=True, help="Skip próximo pozo enrichment.")
@click.option("--compact", is_flag=True, help="Emit JSON in a single line.")
def ingest(url: str, source: str, no_pozos: bool, compact: bool) -> None:
    """Parse a draw URL and print the normalized record."""

    record = ingest_draw(url, source=source, include_pozos=not no_pozos)
    _echo_json(record, indent=None if compact else 2)


@cli.command("list-24h")
@click.option(
    "--index-url",
    default="https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html",
    show_default=True,
    help="24Horas tag index to scan.",
)
@click.option("--limit", default=10, show_default=True, help="Maximum number of URLs to return.")
def list_24h(index_url: str, limit: int) -> None:
    """List recent 24Horas result URLs."""

    urls = list_24h_result_urls(index_url=index_url, limit=limit)
    for item in urls:
        click.echo(item)


@cli.command()
def pozos() -> None:
    """Print próximo pozo estimates from known aggregators."""

    results = {
        "openloto": get_pozo_openloto(),
        "resultadoslotochile": get_pozo_resultadosloto(),
    }
    _echo_json(results)


@cli.command()
@click.option(
    "--sources",
    default="openloto",
    show_default=True,
    help="Comma-separated list of sources to use (or 'all').",
)
@click.option(
    "--source-url",
    multiple=True,
    help="Override a source URL in the form source=url. Can be provided multiple times.",
)
@click.option("--retries", default=3, show_default=True, help="Number of retries per source.")
@click.option("--timeout", default=30, show_default=True, help="HTTP timeout in seconds.")
@click.option(
    "--fail-fast/--no-fail-fast",
    default=False,
    show_default=True,
    help="Abort on the first source failure instead of continuing.",
)
@click.option(
    "--raw-dir",
    default="artifacts/raw",
    show_default=True,
    help="Directory where per-source raw outputs will be written.",
)
@click.option(
    "--normalized",
    default="artifacts/normalized.jsonl",
    show_default=True,
    help="Path to the normalized NDJSON output file.",
)
@click.option(
    "--comparison-report",
    default="artifacts/comparison_report.json",
    show_default=True,
    help="Path to the comparison report JSON file.",
)
@click.option(
    "--summary",
    default="artifacts/run_summary.json",
    show_default=True,
    help="Path to the machine-readable run summary.",
)
@click.option(
    "--state-file",
    default="pipeline_state/last_run.jsonl",
    show_default=True,
    help="File used to persist the last successful normalized record.",
)
@click.option(
    "--log-file",
    default="logs/run.jsonl",
    show_default=True,
    help="Structured log file emitted by the pipeline.",
)
@click.option(
    "--mismatch-threshold",
    default=0.25,
    show_default=True,
    help="Maximum ratio of category mismatches tolerated before quarantining output.",
)
@click.option(
    "--include-pozos/--no-include-pozos",
    default=True,
    show_default=True,
    help="Include próximo pozo enrichment in the normalized record.",
)
def run(
    sources: str,
    source_url: tuple[str, ...],
    retries: int,
    timeout: int,
    fail_fast: bool,
    raw_dir: str,
    normalized: str,
    comparison_report: str,
    summary: str,
    state_file: str,
    log_file: str,
    mismatch_threshold: float,
    include_pozos: bool,
) -> None:
    """Execute the multi-source ingestion pipeline."""

    if retries < 1:
        raise click.BadParameter("--retries must be >= 1")
    if timeout < 1:
        raise click.BadParameter("--timeout must be >= 1")
    if mismatch_threshold < 0:
        raise click.BadParameter("--mismatch-threshold must be >= 0")

    requested_sources = [item.strip() for item in sources.split(",") if item.strip()]
    if not requested_sources:
        requested_sources = ["all"]

    overrides: dict[str, str] = {}
    env_overrides = os.getenv("ALT_SOURCE_URLS")
    if env_overrides:
        try:
            data = json.loads(env_overrides)
        except json.JSONDecodeError as exc:
            raise click.BadParameter("ALT_SOURCE_URLS must contain valid JSON") from exc
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(key, str) and isinstance(value, str):
                    overrides.setdefault(key.lower(), value)
    for item in source_url:
        if "=" not in item:
            raise click.BadParameter("--source-url must be in the format source=url")
        key, value = item.split("=", 1)
        key = key.strip().lower()
        if not key or not value:
            raise click.BadParameter("--source-url must include a non-empty source and url")
        overrides[key] = value.strip()

    summary_payload = run_pipeline(
        sources=requested_sources,
        source_overrides=overrides,
        raw_dir=Path(raw_dir),
        normalized_path=Path(normalized),
        comparison_report_path=Path(comparison_report),
        summary_path=Path(summary),
        state_path=Path(state_file),
        log_path=Path(log_file),
        retries=retries,
        timeout=timeout,
        fail_fast=fail_fast,
        mismatch_threshold=mismatch_threshold,
        include_pozos=include_pozos,
    )

    _echo_json(summary_payload)


@cli.command()
@click.option("--normalized", required=True, help="Path to the normalized NDJSON file.")
@click.option("--comparison-report", required=True, help="Path to the comparison report JSON file.")
@click.option(
    "--summary",
    default=None,
    help="Optional run summary JSON file to honour publish/quarantine decisions.",
)
@click.option(
    "--worksheet",
    default="Normalized",
    show_default=True,
    help="Worksheet name to update with canonical data.",
)
@click.option(
    "--discrepancy-tab",
    default="Discrepancies",
    show_default=True,
    help="Worksheet name used to store comparison mismatches.",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    show_default=True,
    help="Skip calls to the Google Sheets API and only print the intended actions.",
)
@click.option(
    "--force-publish/--no-force-publish",
    default=False,
    show_default=True,
    help="Publish even if the run summary requested quarantine.",
)
@click.option(
    "--allow-quarantine/--no-allow-quarantine",
    default=False,
    show_default=True,
    help="When set, discrepancies are still written even if the canonical update is skipped.",
)
def publish(
    normalized: str,
    comparison_report: str,
    summary: str | None,
    worksheet: str,
    discrepancy_tab: str,
    dry_run: bool,
    force_publish: bool,
    allow_quarantine: bool,
) -> None:
    """Publish validated data to Google Sheets."""

    summary_payload: dict[str, object] | None = None
    if summary:
        try:
            summary_payload = json.loads(Path(summary).read_text(encoding="utf-8"))
        except FileNotFoundError:
            # Proceed without run summary if not present; rely on comparison report
            summary_payload = None

    result = publish_to_google_sheets(
        normalized_path=Path(normalized),
        comparison_report_path=Path(comparison_report),
        summary=summary_payload,
        worksheet_name=worksheet,
        discrepancy_tab=discrepancy_tab,
        dry_run=dry_run,
        force_publish=force_publish,
        allow_quarantine=allow_quarantine,
    )

    _echo_json(result)


if __name__ == "__main__":
    cli()
