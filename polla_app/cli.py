"""Command line interface for the alternative ingestion pipeline."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import click

from .config import AppConfig
from .exceptions import ScriptError
from .ingest import collect_report
from .sheets import CredentialManager, GoogleSheetsManager

LOGGER = logging.getLogger("polla_app")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
    )


@click.group()
def cli() -> None:
    """CLI principal."""


@cli.command()
@click.option("--config-t13", multiple=True, help="URLs de T13 a procesar (puede repetirse)")
@click.option("--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
@click.option("--skip-sheets", is_flag=True, help="No actualizar Google Sheets, solo imprimir JSON")
def ingest(config_t13: tuple[str, ...], log_level: str, skip_sheets: bool) -> None:
    """Ingerir información desde las fuentes alternativas y actualizar planilla."""

    setup_logging(log_level)
    logger = LOGGER

    config = AppConfig.create_default()
    if config_t13:
        config.sources.t13_urls = list(config_t13)

    try:
        report = collect_report(config, logger=logger)
    except ScriptError as exc:
        logger.error("Error durante la recopilación: %s", exc)
        raise SystemExit(1) from exc

    logger.info("Sorteo identificado: %s", report.sorteo)

    if skip_sheets:
        import json

        click.echo(json.dumps(report.to_sheet_values(), ensure_ascii=False, indent=2))
        raise SystemExit(0)

    credential_manager = CredentialManager(config, logger)
    sheets_manager = GoogleSheetsManager(config, credential_manager, logger)
    try:
        asyncio.run(sheets_manager.update_sheet(report))
    except ScriptError as exc:
        logger.error("Error al actualizar Google Sheets: %s", exc)
        raise SystemExit(2) from exc

    logger.info("Proceso completado correctamente")


@cli.command()
@click.argument("url")
def t13(url: str) -> None:
    """Imprimir el resultado crudo de una nota de T13."""

    from .sources import parse_t13_draw
    import json

    config = AppConfig.create_default()
    data = parse_t13_draw(url, ua=config.network.user_agent, timeout=config.network.timeout)
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


@cli.command()
@click.argument("url")
def h24(url: str) -> None:
    """Imprimir resultado crudo de 24Horas."""

    from .sources import parse_24h_draw
    import json

    config = AppConfig.create_default()
    data = parse_24h_draw(url, ua=config.network.user_agent, timeout=config.network.timeout)
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()

