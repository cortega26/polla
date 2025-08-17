"""Browser management using Playwright."""

import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from .config import AppConfig
from .exceptions import ScriptError


class PlaywrightManager:
    """Manage Playwright browser lifecycle and configuration."""

    def __init__(self, config: AppConfig, logger: logging.Logger):
        """Initialize the browser manager."""
        self.config = config
        self.logger = logger
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "PlaywrightManager":
        """Async context manager entry."""
        await self._initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def _initialize(self) -> None:
        """Initialize Playwright and browser."""
        try:
            self._playwright = await async_playwright().start()

            # Launch browser
            launch_args = self.config.browser.to_launch_args()
            self.logger.info("Launching browser with args: %s", launch_args)
            self._browser = await self._playwright.chromium.launch(**launch_args)

            # Create context with storage state if exists
            context_args = self.config.browser.to_context_args()
            storage_state_path = Path(self.config.scraper.storage_state_file)

            if storage_state_path.exists():
                try:
                    context_args["storage_state"] = str(storage_state_path)
                    self.logger.info("Loading storage state from %s", storage_state_path)
                except Exception as e:
                    self.logger.warning("Failed to load storage state: %s", e)

            self._context = await self._browser.new_context(**context_args)

            # Set default timeouts
            self._context.set_default_navigation_timeout(self.config.browser.navigation_timeout)
            self._context.set_default_timeout(self.config.browser.timeout)

            # Create page
            self._page = await self._context.new_page()

            # Set up request/response logging for debugging
            self._page.on("response", self._log_response)

            self.logger.info("Browser initialized successfully")

        except Exception as e:
            raise ScriptError("Failed to initialize browser", e, "BROWSER_INIT_ERROR") from e

    def _log_response(self, response) -> None:
        """Log interesting responses for debugging."""
        if response.status >= 400:
            self.logger.warning("HTTP %d response from %s", response.status, response.url[:100])

    async def get_page(self) -> Page:
        """Get the browser page instance."""
        if not self._page:
            raise ScriptError("Browser not initialized", error_code="BROWSER_NOT_INITIALIZED")
        return self._page

    async def save_storage_state(self) -> None:
        """Save browser storage state for session persistence."""
        if not self._context:
            return

        try:
            storage_path = Path(self.config.scraper.storage_state_file)
            await self._context.storage_state(path=str(storage_path))
            self.logger.info("Saved storage state to %s", storage_path)
        except Exception as e:
            self.logger.warning("Failed to save storage state: %s", e)

    async def save_screenshot(self, prefix: str = "screenshot") -> str:
        """Save a screenshot for debugging."""
        if not self._page:
            return ""

        debug_dir = Path("debug")
        debug_dir.mkdir(exist_ok=True)

        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = debug_dir / f"{prefix}_{timestamp}.png"

        try:
            await self._page.screenshot(path=str(filename), full_page=True)
            self.logger.info("Screenshot saved to %s", filename)
            return str(filename)
        except Exception as e:
            self.logger.error("Failed to save screenshot: %s", e)
            return ""

    async def close(self) -> None:
        """Close all browser resources."""
        try:
            # Save storage state before closing
            await self.save_storage_state()

            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

            self.logger.info("Browser closed successfully")
        except Exception as e:
            self.logger.warning("Error closing browser: %s", e)
