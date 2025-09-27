"""Custom exceptions for the Polla scraper."""

import logging
import traceback
from datetime import datetime


class ScriptError(Exception):
    """Custom exception for script errors with detailed context."""

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
        error_code: str | None = None,
    ):
        """Initialize the ScriptError."""
        self.message = message
        self.original_error = original_error
        self.error_code = error_code
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc() if original_error else None
        super().__init__(self.get_error_message())

    def get_error_message(self) -> str:
        """Get formatted error message."""
        base_msg = f"[{self.error_code}] {self.message}" if self.error_code else self.message
        if self.original_error:
            return f"{base_msg} Original error: {str(self.original_error)}"
        return base_msg

    def log_error(self, logger: logging.Logger) -> None:
        """Log error details."""
        logger.error("Error occurred at %s", self.timestamp.isoformat())
        logger.error("Message: %s", self.message)
        if self.error_code:
            logger.error("Error code: %s", self.error_code)
        if self.original_error:
            logger.error("Original error: %s", str(self.original_error))
        if self.traceback:
            logger.debug("Traceback:\n%s", self.traceback)
