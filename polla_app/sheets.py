"""Google Sheets integration."""

import asyncio
import json
import logging
from os import environ
from typing import Any, cast

import tenacity
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from .config import AppConfig
from .exceptions import ScriptError
from .models import PrizeData


class CredentialManager:
    """Manage Google service account credentials."""

    def __init__(self, config: AppConfig, logger: logging.Logger):
        """Initialize credential manager."""
        self.config = config
        self.logger = logger

    @staticmethod
    def _validate_credentials_dict(creds_dict: dict[str, Any]) -> None:
        """Validate that credentials have required fields."""
        required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
        missing_fields = [field for field in required_fields if field not in creds_dict]
        if missing_fields:
            raise ScriptError(
                f"Missing required credential fields: {', '.join(missing_fields)}",
                error_code="INVALID_CREDENTIALS",
            )

    def get_credentials(self) -> Credentials:
        """Get Google credentials from environment."""
        try:
            credentials_json = environ.get("CREDENTIALS")
            if not credentials_json:
                raise ScriptError(
                    "CREDENTIALS environment variable is not set",
                    error_code="MISSING_CREDENTIALS",
                )

            credentials_dict = json.loads(credentials_json)
            self._validate_credentials_dict(credentials_dict)

            self.logger.info("Google credentials successfully loaded")
            return cast(
                Credentials,
                service_account.Credentials.from_service_account_info(
                    credentials_dict, scopes=self.config.google.scopes
                ),
            )

        except json.JSONDecodeError as e:
            raise ScriptError(
                "Invalid JSON in CREDENTIALS environment variable", e, "INVALID_JSON"
            ) from e
        except Exception as e:
            if isinstance(e, ScriptError):
                raise
            raise ScriptError("Error retrieving credentials", e, "CREDENTIAL_ERROR") from e


class GoogleSheetsManager:
    """Manage Google Sheets updates."""

    def __init__(
        self, config: AppConfig, credential_manager: CredentialManager, logger: logging.Logger
    ):
        """Initialize sheets manager."""
        self.config = config
        self.credential_manager = credential_manager
        self.logger = logger
        self._service: Resource | None = None

    def _initialize_service(self) -> None:
        """Initialize Google Sheets service."""
        if not self._service:
            creds = self.credential_manager.get_credentials()
            self._service = build("sheets", "v4", credentials=creds)

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=5),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type((HttpError, ScriptError)),
    )
    async def update_sheet(self, prize_data: PrizeData) -> None:
        """Update Google Sheet with prize data."""
        try:
            # Run synchronous Google API in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._update_sheet_sync, prize_data)

        except Exception as e:
            raise ScriptError("Error updating Google Sheet", e, "UPDATE_ERROR") from e

    def _update_sheet_sync(self, prize_data: PrizeData) -> None:
        """Synchronous sheet update (for thread pool execution)."""
        self._initialize_service()

        if not self._service:
            raise ScriptError(
                "Google Sheets service not initialized",
                error_code="SERVICE_NOT_INITIALIZED",
            )

        values = prize_data.to_sheet_values()
        body = {"values": values}

        self.logger.info("Updating Google Sheet with prize data...")

        try:
            response = (
                self._service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.config.google.spreadsheet_id,
                    range=self.config.google.range_name,
                    valueInputOption="RAW",
                    body=body,
                )
                .execute()
            )

            updated = response.get("updatedCells", 0)
            self.logger.info(
                "Update successful - %d cells updated. Total prizes: %d",
                updated,
                prize_data.total_prize_money,
            )

        except HttpError as error:
            status = getattr(error.resp, "status", None)
            if status == 403:
                raise ScriptError(
                    "Permission denied - check service account permissions",
                    error,
                    "PERMISSION_DENIED",
                ) from error
            elif status == 404:
                raise ScriptError(
                    "Spreadsheet not found - check spreadsheet ID",
                    error,
                    "SPREADSHEET_NOT_FOUND",
                ) from error
            else:
                raise ScriptError(
                    f"Google Sheets API error: {status}", error, "SHEETS_API_ERROR"
                ) from error
