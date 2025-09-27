"""Alternative data ingestion utilities for Chilean Loto transparency."""

__version__ = "3.0.0"

from .exceptions import ScriptError
from .models import DrawReport

__all__ = ["ScriptError", "DrawReport"]
