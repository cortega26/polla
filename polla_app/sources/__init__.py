"""Parsers for alternative lottery data sources."""

from ._24h import list_24h_result_urls, parse_24h_draw
from .pozos import get_pozo_openloto, get_pozo_resultadosloto
from .t13 import parse_t13_draw

__all__ = [
    "parse_t13_draw",
    "parse_24h_draw",
    "list_24h_result_urls",
    "get_pozo_openloto",
    "get_pozo_resultadosloto",
]
