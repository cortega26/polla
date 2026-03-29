import re

text = """
POZO PRÓXIMO SORTEO 5405
Fecha Próximo Sorteo: 29/03/2026

POZO TOTAL:
$5.850 MILLONES

LOTO: $2.400 MILLONES
RECARGADO: $950 MILLONES
REVANCHA: $660 MILLONES
DESQUITE: $280 MILLONES
JUBILAZO $1.000.000: $720 MILLONES
JUBILAZO $500.000: $240 MILLONES
JUBILAZO 50 años $1.000.000: $600 MILLONES
JUBILAZO 50 años $500.000: $0 MILLONES
"""

_LABEL_PATTERNS = {
    "Loto Clásico": r"Loto",  # simplified
    "Jubilazo $1.000.000": r"Jubilazo(?:\s*\$?1\.000\.000)?",
    "Jubilazo $500.000": r"(?:Jubilazo\s+Aniversario(?:\s*de\s*\$?500\.000)?|Jubilazo\s*\$?500\.000)",
}

for label, pattern in _LABEL_PATTERNS.items():
    regex = re.compile(pattern + r"[^0-9$]{0,50}\$?([\d\.,]+)", re.IGNORECASE)
    match = regex.search(text)
    if match:
        print(f"{label}: {match.group(1)}")

