"""Alternative-source ingestion utilities for Chilean Loto draws."""

__version__ = "3.0.0"

from .exceptions import ScriptError
from .ingest import ingest_draw, list_24h_result_urls
from .sources import (
    get_pozo_openloto,
    get_pozo_resultadosloto,
    parse_24h_draw,
    parse_t13_draw,
)

__all__ = [
    "ScriptError",
    "ingest_draw",
    "list_24h_result_urls",
    "parse_t13_draw",
    "parse_24h_draw",
    "get_pozo_openloto",
    "get_pozo_resultadosloto",
]
