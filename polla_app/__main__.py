"""CLI entry point for the Polla scraper."""

import asyncio
import logging
import sys
from pathlib import Path

import click

from .browser import PlaywrightManager
from .config import AppConfig
from .exceptions import ScriptError
from .scraper import PollaScraper
from .sheets import CredentialManager, GoogleSheetsManager


# Configure logging
def setup_logging(log_level: str) -> logging.Logger:
    """Set up logging configuration."""
    logger = logging.getLogger("polla_app")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(console_handler)

    # File handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    from datetime import datetime

    log_file = log_dir / f"polla_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    return logger


async def run_scraper(config: AppConfig, logger: logging.Logger) -> int:
    """Run the main scraping process."""
    try:
        logger.info("Starting Polla.cl scraper v2.0.0")

        async with PlaywrightManager(config, logger) as browser_manager:
            page = await browser_manager.get_page()

            scraper = PollaScraper(config, page, logger)
            prize_data = await scraper.scrape_prize_data()

            logger.info("Successfully scraped prize data: %s", prize_data)

            # Update Google Sheets
            credential_manager = CredentialManager(config, logger)
            sheets_manager = GoogleSheetsManager(config, credential_manager, logger)
            await sheets_manager.update_sheet(prize_data)

            logger.info("Successfully updated Google Sheet")
            return 0

    except ScriptError as e:
        e.log_error(logger)
        if e.error_code == "ACCESS_DENIED":
            return 2
        return 1
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 3


async def run_multi_agents(config: AppConfig, logger: logging.Logger, agents: int) -> int:
    """Run multiple scraper agents concurrently."""

    async def _agent_task(agent_id: int) -> int:
        agent_logger = logger.getChild(f"agent-{agent_id}")
        return await run_scraper(config, agent_logger)

    results = await asyncio.gather(*[_agent_task(i) for i in range(agents)])
    # Return the highest exit code so any failure bubbles up
    return max(results)


@click.group()
def cli() -> None:
    """Command-line interface for polla_app."""


@cli.command()
@click.option("--show", is_flag=True, help="Run browser in headed mode")
@click.option("--timeout", default=30, help="Page timeout in seconds")
@click.option(
    "--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"])
)
@click.option("--agents", default=1, help="Number of parallel scraper agents")
def scrape(show: bool, timeout: int, log_level: str, agents: int) -> None:
    """Scrape Polla.cl prize data and update Google Sheets."""
    logger = setup_logging(log_level)

    config = AppConfig.create_default()
    config.browser.headless = not show
    config.scraper.timeout = timeout

    if agents == 1:
        exit_code = asyncio.run(run_scraper(config, logger))
    else:
        exit_code = asyncio.run(run_multi_agents(config, logger, agents))
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
