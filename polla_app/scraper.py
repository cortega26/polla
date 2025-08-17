"""Main scraper logic using Playwright."""

import asyncio
import logging
import random
import re

import tenacity
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .config import AppConfig
from .exceptions import ScriptError
from .models import PrizeData


class PollaScraper:
    """Scraper for Polla.cl prize data."""

    def __init__(self, config: AppConfig, page: Page, logger: logging.Logger):
        """Initialize the scraper."""
        self.config = config
        self.page = page
        self.logger = logger
        # Order matters here - more specific indicators should come first so that
        # the resulting error message contains the most helpful hint. For example,
        # if "Imperva" is present alongside the generic "Access Denied" message we
        # want the former to surface in the exception so downstream checks can
        # assert on it.
        self._access_denied_indicators = [
            "Imperva",
            "Access Denied",
            "Error 16",
            "Request blocked",
            "Security check",
            "Please wait while we verify",
            "Your request has been blocked",
            "DDoS protection",
            "Bot Detection",
            "Captcha",
        ]

    async def _check_access_denied(self) -> None:
        """Check if access is denied and abort if detected."""
        content = await self.page.content()

        for indicator in self._access_denied_indicators:
            if indicator in content:
                self.logger.error("Access denied detected: %s", indicator)

                # Save screenshot for debugging

                await self._save_screenshot("access_denied")

                raise ScriptError(
                    f"Access denied by WAF/Security: {indicator}", error_code="ACCESS_DENIED"
                )

    async def _save_screenshot(self, prefix: str) -> str:
        """Save a screenshot."""
        from datetime import datetime
        from pathlib import Path

        debug_dir = Path("debug")
        debug_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = debug_dir / f"{prefix}_{timestamp}.png"

        try:
            await self.page.screenshot(path=str(filename), full_page=True)
            self.logger.info("Screenshot saved to %s", filename)
            return str(filename)
        except Exception as e:
            self.logger.error("Failed to save screenshot: %s", e)
            return ""

    async def _human_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Add human-like delay between actions."""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)

    async def _close_popups(self) -> None:
        """Close any popup banners that might appear."""
        popup_selectors = [
            'span.close[data-bind="click: hideBanner"]',
            ".banner-close",
            ".modal-close",
            ".popup-close",
            "button.close",
            '[aria-label="Close"]',
            '[aria-label="Cerrar"]',
        ]

        for selector in popup_selectors:
            try:
                close_button = self.page.locator(selector).first
                if await close_button.is_visible():
                    await close_button.click()
                    self.logger.info("Closed popup with selector: %s", selector)
                    await self._human_delay(0.5, 1.5)
                    return
            except Exception:
                continue

    def _parse_prize(self, text: str) -> int:
        """Parse prize text to integer value."""
        try:
            if not text or not text.strip():
                raise ValueError("Empty prize value")

            cleaned = text.strip().replace("$", "").replace(" ", "")

            multiplier = 1
            if "MM" in cleaned.upper():
                cleaned = re.sub(r"(?i)MM", "", cleaned)
                multiplier = 1_000_000

            # Normalise decimal/thousand separators. If both comma and dot are
            # present we assume a thousands/decimal pair like "1.234,5".
            if "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                if "," in cleaned:
                    cleaned = cleaned.replace(",", ".")
                if cleaned.count(".") > 1:
                    cleaned = cleaned.replace(".", "")

            value = float(cleaned)

            if multiplier == 1 and 0 < value < 1000:
                multiplier = 1_000_000

            return int(value * multiplier)

        except (ValueError, AttributeError) as e:
            self.logger.error("Failed to parse prize value: '%s'", text)
            raise ScriptError(
                f"Parsing error for prize value: '{text}'", e, "PRIZE_PARSING_ERROR"
            ) from e

    def _validate_prizes(self, prizes: list[int]) -> None:
        """Validate that we have valid prize data."""
        if not prizes:
            raise ScriptError("No prizes found", error_code="NO_PRIZES_ERROR")

        if len(prizes) < 7:
            raise ScriptError(
                f"Invalid prize data: expected 7+ prizes, got {len(prizes)}",
                error_code="INSUFFICIENT_PRIZES_ERROR",
            )

        if all(prize == 0 for prize in prizes):
            raise ScriptError(
                "All prizes are zero - possible scraping error", error_code="ZERO_PRIZES_ERROR"
            )

    async def _extract_prizes_from_game(self, game_name: str) -> int | None:
        """Extract prize value for a specific game."""
        prize_selectors = [
            f'[data-game="{game_name}"] .prize-amount',
            f'[data-game="{game_name}"] .prize-value',
            f".game-{game_name.lower()} .prize-amount",
            f".{game_name.lower()}-prize",
            ".prize-amount",
            ".jackpot-amount",
            ".prize-value",
            '[data-bind*="prize"]',
        ]

        for selector in prize_selectors:
            try:
                elements = self.page.locator(selector)
                count = await elements.count()

                for i in range(count):
                    element = elements.nth(i)
                    if await element.is_visible():
                        text = await element.text_content()
                        if text and any(c.isdigit() for c in text):
                            prize = self._parse_prize(text)
                            self.logger.info(
                                "Extracted %s prize: %s (parsed to %d)", game_name, text, prize
                            )
                            return prize
            except Exception as e:
                self.logger.debug("Failed with selector %s: %s", selector, e)
                continue

        return None

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(ScriptError),
        wait=tenacity.wait_exponential(multiplier=1.5, min=5),
        stop=tenacity.stop_after_attempt(3),
        before_sleep=lambda retry_state: logging.getLogger("polla_app.scraper").info(
            "Retrying scrape in %.1f seconds (attempt %d)...",
            retry_state.next_action.sleep if retry_state.next_action else 0,
            retry_state.attempt_number,
        ),
    )
    async def scrape_prize_data(self) -> PrizeData:
        """Main scraping method to extract all prize data."""
        try:
            self.logger.info("Starting prize data scraping...")

            # Navigate to the main page
            self.logger.info("Navigating to %s", self.config.scraper.base_url)
            await self.page.goto(self.config.scraper.base_url, wait_until="networkidle")

            # Check for access denied
            await self._check_access_denied()

            # Wait for content to load
            await self._human_delay(2, 4)

            # Close any popups
            await self._close_popups()

            # Verify we have the right content
            content = await self.page.content()
            if "loto" not in content.lower():
                self.logger.warning("Expected content not found, might be blocked")
                await self._save_screenshot("no_content")
                raise ScriptError(
                    "Expected lottery content not found", error_code="CONTENT_NOT_FOUND"
                )

            # Extract prizes for each game
            games = [
                ("Loto", "loto"),
                ("Recargado", "recargado"),
                ("Revancha", "revancha"),
                ("Desquite", "desquite"),
                ("Jubilazo", "jubilazo"),
                ("Multiplicar", "multiplicar"),
                ("Jubilazo 50", "jubilazo_50"),
            ]

            prizes = []

            for display_name, field_name in games:
                self.logger.info("Processing game: %s", display_name)

                # Try to expand the game section if needed
                expand_selectors = [
                    f'[data-game="{display_name}"] .expand-icon',
                    f'[data-game="{display_name}"] .expanse-controller',
                    f".game-{field_name} .expand-button",
                    ".expanse-controller img",
                ]

                for selector in expand_selectors:
                    try:
                        expand_btn = self.page.locator(selector).first
                        if await expand_btn.is_visible():
                            await expand_btn.click()
                            self.logger.info("Clicked expand for %s", display_name)
                            await self._human_delay(1, 2)
                            break
                    except Exception:
                        continue

                # Extract the prize value
                prize_value = await self._extract_prizes_from_game(display_name)

                if prize_value is None:
                    self.logger.warning("Could not extract prize for %s, using 0", display_name)
                    prize_value = 0

                prizes.append(prize_value)

                # Add delay between games
                await self._human_delay(0.5, 1.5)

            # Validate prizes
            self._validate_prizes(prizes)

            # Save final screenshot
            await self._save_screenshot("final_state")

            # Create and return PrizeData
            return PrizeData(
                loto=prizes[0],
                recargado=prizes[1],
                revancha=prizes[2],
                desquite=prizes[3],
                jubilazo=prizes[4],
                multiplicar=prizes[5],
                jubilazo_50=prizes[6],
            )

        except PlaywrightTimeout as e:
            self.logger.error("Page timeout: %s", e)
            await self._save_screenshot("timeout_error")
            raise ScriptError("Page load timeout", e, "TIMEOUT_ERROR") from e
        except ScriptError:
            raise
        except Exception as e:
            self.logger.exception("Unexpected error during scraping")
            await self._save_screenshot("error_state")
            raise ScriptError("Failed to scrape prize data", e, "SCRAPE_ERROR") from e
