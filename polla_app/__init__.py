"""Polla.cl Prize Scraper - Async Playwright Implementation."""

__version__ = "2.0.0"

from .exceptions import ScriptError
from .models import PrizeData

__all__ = ["ScriptError", "PrizeData"]
