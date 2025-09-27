"""High level orchestration for collecting and validating draw data."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Sequence

from .analyzer import compare_records, determine_last_draw
from .config import AppConfig
from .exceptions import ScriptError
from .models import ComparisonResult, DrawReport, DrawSourceRecord, JackpotRecord, PrizeBreakdown
from .sources import (
    get_pozo_openloto,
    get_pozo_resultadosloto,
    list_24h_result_urls,
    parse_24h_draw,
    parse_t13_draw,
)

_logger = logging.getLogger("polla_app.ingest")


def _to_record(data: dict[str, object]) -> DrawSourceRecord:
    # Convert nested dict to dataclasses
    prizes = [PrizeBreakdown.from_dict(p) for p in data.get("premios", [])]  # type: ignore[arg-type]
    sorteo_value = data.get("sorteo")
    if isinstance(sorteo_value, str) and sorteo_value.isdigit():
        sorteo_value = int(sorteo_value)
    fecha_value = data.get("fecha")
    if fecha_value is not None:
        fecha_value = str(fecha_value)
    fuente_value = str(data.get("fuente", ""))
    sha_value = data.get("sha256")
    titulo_value = data.get("titulo")
    return DrawSourceRecord(
        sorteo=sorteo_value,
        fecha=fecha_value,
        fuente=fuente_value,
        premios=prizes,
        html_sha256=str(sha_value) if sha_value else None,
        titulo=str(titulo_value) if titulo_value else None,
    )


def _fetch_t13_records(urls: Sequence[str], config: AppConfig) -> list[DrawSourceRecord]:
    records: list[DrawSourceRecord] = []
    for url in urls:
        try:
            data = parse_t13_draw(url, ua=config.network.user_agent, timeout=config.network.timeout)
            records.append(_to_record(data))
        except ScriptError as exc:
            _logger.warning("Fallo al parsear T13 %s: %s", url, exc)
    return records


def _fetch_24h_record_for_sorteo(config: AppConfig, sorteo: int | None) -> list[DrawSourceRecord]:
    if not sorteo:
        return []
    try:
        index_entries = list_24h_result_urls(
            config.sources.h24_tag_url,
            ua=config.network.user_agent,
            timeout=config.network.timeout,
            limit=10,
        )
    except ScriptError as exc:
        _logger.warning("No se pudo listar artículos 24Horas: %s", exc)
        return []

    records: list[DrawSourceRecord] = []
    for entry in index_entries:
        if entry.get("sorteo") != sorteo:
            continue
        url = entry["url"]
        try:
            data = parse_24h_draw(url, ua=config.network.user_agent, timeout=config.network.timeout)
            record = _to_record(data)
            record.titulo = entry.get("titulo") or record.titulo
            records.append(record)
        except ScriptError as exc:
            _logger.warning("No se pudo parsear nota de 24Horas %s: %s", url, exc)
    return records


def _fetch_jackpots(config: AppConfig) -> list[JackpotRecord]:
    jackpots: list[JackpotRecord] = []
    for label, func, url in (
        ("OpenLoto", get_pozo_openloto, config.sources.openloto_url),
        ("ResultadosLotoChile", get_pozo_resultadosloto, config.sources.resultadosloto_url),
    ):
        try:
            pozos = func(url=url, ua=config.network.user_agent)
            jackpots.append(JackpotRecord(fuente=f"{label} ({url})", pozos=pozos, fetched_at=datetime.now(timezone.utc)))
        except ScriptError as exc:
            _logger.warning("No se pudo obtener pozos desde %s: %s", label, exc)
    return jackpots


def collect_report(config: AppConfig, logger: logging.Logger | None = None) -> DrawReport:
    """Collect data from configured sources and build a draw report."""

    logger = logger or _logger
    t13_urls = config.sources.iter_t13_urls()
    if not t13_urls:
        raise ScriptError("No hay URLs de T13 configuradas", error_code="SIN_T13")

    t13_records = _fetch_t13_records(t13_urls, config)
    if not t13_records:
        raise ScriptError("No fue posible obtener datos de T13", error_code="SIN_DATOS_T13")

    primary = determine_last_draw(t13_records)
    logger.info("Último sorteo identificado: %s (fecha %s)", primary.sorteo, primary.fecha)

    secondary_sources = _fetch_24h_record_for_sorteo(config, primary.sorteo)
    comparisons: list[ComparisonResult] = []
    for secondary in secondary_sources:
        comparison = compare_records(primary, secondary)
        comparisons.append(comparison)
        if comparison.matches:
            logger.info("24Horas coincide con T13 (%s)", secondary.fuente)
        else:
            logger.warning("Diferencias encontradas con %s: %s", secondary.fuente, comparison.differences)

    jackpots = _fetch_jackpots(config)

    return DrawReport(
        primary=primary,
        secondary_sources=secondary_sources,
        comparisons=comparisons,
        jackpots=jackpots,
    )

