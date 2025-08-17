"""Test scraper functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from polla_app.exceptions import ScriptError
from polla_app.models import PrizeData
from polla_app.scraper import PollaScraper


class TestScraperAccessDenied:
    """Test access denied detection."""

    @pytest.fixture
    def scraper(self, app_config, mock_page, mock_logger):
        """Create scraper instance."""
        return PollaScraper(app_config, mock_page, mock_logger)

    @pytest.mark.asyncio
    async def test_detect_access_denied(self, scraper, mock_page):
        """Test that access denied is detected."""
        mock_page.content = AsyncMock(
            return_value="<html>Access Denied - Imperva Protection</html>"
        )

        with pytest.raises(ScriptError) as exc_info:
            await scraper._check_access_denied()

        assert exc_info.value.error_code == "ACCESS_DENIED"
        assert "Imperva" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_access_denied(self, scraper, mock_page):
        """Test normal content passes check."""
        mock_page.content = AsyncMock(return_value="<html>Normal lottery content</html>")

        # Should not raise
        await scraper._check_access_denied()


class TestScraperIntegration:
    """Test full scraping flow."""

    @pytest.fixture
    def scraper(self, app_config, mock_logger):
        """Create scraper with mock page."""
        mock_page = MagicMock()

        # Mock navigation
        mock_page.goto = AsyncMock()

        # Mock content checks
        mock_page.content = AsyncMock(return_value="<html>Loto prize content</html>")

        # Mock element interactions
        mock_locator = MagicMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.first = MagicMock()
        mock_locator.first.is_visible = AsyncMock(return_value=True)
        mock_locator.first.click = AsyncMock()
        mock_locator.first.text_content = AsyncMock(return_value="$1.200.000")
        mock_locator.nth = MagicMock(return_value=mock_locator.first)

        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_page.screenshot = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value="{}")

        return PollaScraper(app_config, mock_page, mock_logger)

    @pytest.mark.asyncio
    async def test_successful_scrape(self, scraper):
        """Test successful scraping returns PrizeData."""
        result = await scraper.scrape_prize_data()

        assert isinstance(result, PrizeData)
        assert result.loto == 1200000
        assert result.total_prize_money > 0
