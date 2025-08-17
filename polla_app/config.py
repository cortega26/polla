"""Configuration classes for the Polla scraper."""

from dataclasses import dataclass, field
from typing import Dict, Any


@dataclass
class BrowserConfig:
    """Browser configuration settings."""
    
    headless: bool = True
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "es-CL"
    timezone: str = "America/Santiago"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    navigation_timeout: int = 45000  # 45 seconds in ms
    timeout: int = 15000  # 15 seconds in ms for actions
    
    def to_launch_args(self) -> Dict[str, Any]:
        """Convert to Playwright launch arguments."""
        return {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
    
    def to_context_args(self) -> Dict[str, Any]:
        """Convert to Playwright context arguments."""
        return {
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "locale": self.locale,
            "timezone_id": self.timezone,
            "user_agent": self.user_agent,
        }


@dataclass
class ScraperConfig:
    """Scraper configuration settings."""
    
    base_url: str = "https://www.polla.cl/es"
    timeout: int = 30  # seconds
    retry_attempts: int = 3
    retry_multiplier: float = 1.5
    min_retry_wait: int = 5
    element_timeout: int = 10000  # 10 seconds in ms
    storage_state_file: str = "storage_state.json"


@dataclass
class GoogleConfig:
    """Google Sheets configuration settings."""
    
    spreadsheet_id: str = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    range_name: str = "Sheet1!A1:A7"
    scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/spreadsheets",)
    retry_attempts: int = 3
    retry_delay: int = 5


@dataclass
class AppConfig:
    """Main application configuration."""
    
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    
    @classmethod
    def create_default(cls) -> "AppConfig":
        """Create default configuration."""
        return cls()
