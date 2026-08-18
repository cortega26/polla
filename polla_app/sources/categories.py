"""Canonical category label registries per game.

Single source of truth for category labels. Consumers (kino.py, prices.py,
stats.py, site.py) import from here; the strings ARE the contract with the
Google Sheet and the dashboard — never rename a label here without a
migration.
"""

KINO_CATEGORY_LABELS: frozenset[str] = frozenset(
    {
        "Kino",
        "ReKino",
        "RequeteKino",
        "Chao Jefe $2 Millones",
        "Chao Jefe $3 Millones",
        "Súper Combo Marraqueta",
        "Kino Gran Sueldo",
    }
)

# pendón field -> canonical label (kino.py's _POZO_FIELDS, moved here)
KINO_POZO_FIELDS: dict[str, str] = {
    "F_SrtKinAproxSrt": "Kino",
    "F_SrtKinRevAprox": "ReKino",
    "F_SrtKinRev2Aprox": "RequeteKino",
    "F_SrtKinRevSd2Aprox": "Chao Jefe $2 Millones",
    "F_SrtKinRevCJ4Aprox": "Chao Jefe $3 Millones",
    "F_SrtKinRevCJ2Aprox": "Súper Combo Marraqueta",
    "F_SrtKinRevGMSdAprox": "Kino Gran Sueldo",
}

# Stats rows are emitted per category (merge_live_kino appends a sheet row
# per label); "Kino Gran Sueldo" has no hub price field today, so it stays
# OUT of the stats set — a blank row is worse than no row. Close the gap
# here (and in KINO_PRICE_FIELDS) when the hub publishes it. Derived from
# KINO_POZO_FIELDS (not the frozenset) so the six labels keep the official
# hub order — frozenset iteration order is hash-seed dependent, and the
# sheet rows must be deterministic.
KINO_STATS_CATEGORIES: tuple[str, ...] = tuple(
    label for label in KINO_POZO_FIELDS.values() if label != "Kino Gran Sueldo"
)

# hub field -> canonical label (prices.py's _KINO_PRICE_FIELDS, moved here)
KINO_PRICE_FIELDS: tuple[tuple[str, str], ...] = (
    ("PrecioKino", "Kino"),
    ("PrecioReKino", "ReKino"),
    ("PrecioRequeteKino", "RequeteKino"),
    ("PrecioChaoJefe2M", "Chao Jefe $2 Millones"),
    ("PrecioChaoJefe3M", "Chao Jefe $3 Millones"),
    ("PrecioComboMarraqueta", "Súper Combo Marraqueta"),
)
