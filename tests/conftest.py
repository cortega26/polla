"""Pytest configuration and fixtures."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from polla_app.config import AppConfig


@pytest.fixture
def app_config():
    """Provide test configuration."""
    return AppConfig.create_default()


@pytest.fixture
def mock_logger():
    """Provide mock logger."""
    return MagicMock()


@pytest.fixture
def mock_page():
    """Provide mock Playwright page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.content = AsyncMock(return_value="<html>test content loto</html>")
    page.locator = MagicMock()
    page.screenshot = AsyncMock()
    page.evaluate = AsyncMock(return_value="{}")
    return page


@pytest.fixture
def sample_html():
    """Load sample HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "polla_mock.html"
    return fixture_path.read_text()
