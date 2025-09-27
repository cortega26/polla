"""CLI entry point for the alternative-source ingestion workflow."""

from __future__ import annotations

import json
import logging

import click

from .ingest import ingest_draw, list_24h_result_urls
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


def _echo_json(payload: dict, *, indent: int | None = 2) -> None:
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


if __name__ == "__main__":
    cli()
