import re

text = """
JUBILAZO $1.000.000: $720 MILLONES
JUBILAZO $500.000: $240 MILLONES
JUBILAZO 50 años $1.000.000: $600 MILLONES
JUBILAZO 50 años $500.000: $0 MILLONES
"""

_LABEL_PATTERNS = {
    "Loto Clásico": r"Loto\s+Cl[aá]sico",
    "Recargado": r"Recargado",
    "Revancha": r"Revancha",
    "Desquite": r"Desquite",
    "Jubilazo $1.000.000": r"Jubilazo(?:\s*(?:de\s*)?\$?1\.000\.000)?(?!\s*(?:50\s*a(?:ñ|n)os|Aniversario))",
    "Jubilazo $500.000": r"Jubilazo\s*(?:de\s*)?\$?500\.000",
    "Jubilazo 50 años $1.000.000": r"Jubilazo\s*(?:50\s*a(?:ñ|n)os|Aniversario)(?:\s*de)?\s*\$?1\.000\.000",
    "Jubilazo 50 años $500.000": r"Jubilazo\s*(?:50\s*a(?:ñ|n)os|Aniversario)(?:\s*de)?\s*\$?500\.000",
}

for label, pattern in _LABEL_PATTERNS.items():
    regex = re.compile(pattern + r"[^0-9$]{0,50}\$?([\d\.,]+)", re.IGNORECASE)
    match = regex.search(text)
    if match:
        print(f"{label}: {match.group(1)}")
