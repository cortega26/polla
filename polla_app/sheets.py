"""Google Sheets integration tailored to the new draw report format."""

from __future__ import annotations

import asyncio
import json
import logging
from os import environ
from typing import Any, Iterable

import tenacity
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from .config import AppConfig
from .exceptions import ScriptError
from .models import DrawReport


class CredentialManager:
    """Load and validate Google credentials."""

    def __init__(self, config: AppConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    @staticmethod
    def _validate_credentials_dict(creds_dict: dict[str, Any]) -> None:
        required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
        missing = [key for key in required_fields if key not in creds_dict]
        if missing:
            raise ScriptError(
                f"Credenciales incompletas: faltan {', '.join(missing)}",
                error_code="INVALID_CREDENTIALS",
            )

    def get_credentials(self) -> Credentials:
        credentials_json = environ.get("CREDENTIALS")
        if not credentials_json:
            raise ScriptError("CREDENTIALS no está definido", error_code="MISSING_CREDENTIALS")
        try:
            credentials_dict = json.loads(credentials_json)
        except json.JSONDecodeError as exc:
            raise ScriptError("CREDENTIALS no es JSON válido", exc, "INVALID_JSON") from exc
        self._validate_credentials_dict(credentials_dict)
        self.logger.info("Credenciales de Google cargadas correctamente")
        return service_account.Credentials.from_service_account_info(
            credentials_dict, scopes=self.config.google.scopes
        )


class GoogleSheetsManager:
    """Push draw reports to Google Sheets."""

    def __init__(self, config: AppConfig, credential_manager: CredentialManager, logger: logging.Logger):
        self.config = config
        self.credential_manager = credential_manager
        self.logger = logger
        self._service: Resource | None = None

    def _ensure_service(self) -> None:
        if self._service is None:
            creds = self.credential_manager.get_credentials()
            self._service = build("sheets", "v4", credentials=creds)

    def _get_service(self) -> Resource:
        self._ensure_service()
        if self._service is None:  # pragma: no cover - defensive
            raise ScriptError("Servicio de Google Sheets no inicializado", error_code="SERVICE_NOT_INITIALIZED")
        return self._service

    def fetch_last_recorded_sorteo(self) -> int | None:
        """Read the sheet to determine the last recorded draw number."""

        service = self._get_service()
        try:
            response = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=self.config.google.spreadsheet_id, range=self.config.google.read_range)
                .execute()
            )
        except HttpError as exc:
            raise ScriptError("No se pudo leer el Google Sheet", exc, "SHEETS_READ_ERROR") from exc
        values = response.get("values", [])
        for row in values:
            if row and row[0] == "Sorteo" and len(row) > 1:
                try:
                    return int(row[1])
                except (TypeError, ValueError):
                    return None
        return None

    @tenacity.retry(
        wait=tenacity.wait_exponential(multiplier=1, min=5),
        stop=tenacity.stop_after_attempt(3),
        retry=tenacity.retry_if_exception_type((HttpError, ScriptError)),
    )
    async def update_sheet(self, report: DrawReport) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._update_sheet_sync, report)

    def _update_sheet_sync(self, report: DrawReport) -> None:
        service = self._get_service()
        try:
            last_sorteo = self.fetch_last_recorded_sorteo()
        except ScriptError as exc:
            self.logger.warning("No fue posible leer el sorteo anterior: %s", exc)
            last_sorteo = None
        report.last_recorded_sorteo = last_sorteo
        values = report.to_sheet_values()
        body = {"values": values}
        try:
            response = (
                service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.config.google.spreadsheet_id,
                    range=self.config.google.range_name,
                    valueInputOption="RAW",
                    body=body,
                )
                .execute()
            )
        except HttpError as exc:
            raise ScriptError("Error al actualizar Google Sheets", exc, "SHEETS_WRITE_ERROR") from exc
        updated = response.get("updatedCells", 0)
        self.logger.info("Actualización completada: %s celdas", updated)

