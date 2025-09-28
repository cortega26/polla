"""
Synthetic micro-benchmarks for pozos parsing paths.

Measures impact of precompiled regexes vs. the previous on-the-fly approach.

Run:
  python scripts/benchmark_pozos_parsing.py
"""

from __future__ import annotations

import json
import sys
import timeit
from pathlib import Path
from typing import Any

# Ensure repository root is importable when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polla_app.sources import pozos as new  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_text(name: str) -> str:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    try:
        # Use BeautifulSoup in the same way as production code
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    except Exception:
        # Fallback: naive text
        return html


def old_extract_amounts(text: str, *, allow_total: bool = True) -> dict[str, int]:
    patterns = new._LABEL_PATTERNS  # type: ignore[attr-defined]
    out: dict[str, int] = {}
    for label, pattern in patterns.items():
        if not allow_total and label == "Total estimado":
            continue
        regex = __import__("re").compile(
            pattern + r"[^0-9$]{0,40}\$?([\d\.,]+)\s*(?:MM|MILLON(?:ES)?)?",
            __import__("re").IGNORECASE,
        )
        m = regex.search(text)
        if m:
            out[label] = new._parse_millones_to_clp(m.group(1))  # type: ignore[attr-defined]
    return out


def old_extract_proximo_info(text: str) -> tuple[int | None, str | None]:
    import re

    sorteo: int | None = None
    m_sorteo = re.search(r"Sorteo\s*(?:N[°º]\s*)?(\d{4,})", text, re.IGNORECASE)
    if m_sorteo:
        try:
            sorteo = int(m_sorteo.group(1))
        except ValueError:
            sorteo = None
    m_fecha_block = re.search(r"Fecha\s+Pr[oó]ximo\s+Sorteo[:\s]*([^\n]+)", text, re.IGNORECASE)
    fecha_iso = None
    if m_fecha_block:
        fecha_iso = new._parse_spanish_date(m_fecha_block.group(1))  # type: ignore[attr-defined]
    if not fecha_iso:
        fecha_iso = new._parse_spanish_date(text)  # type: ignore[attr-defined]
    return sorteo, fecha_iso


def bench() -> dict[str, Any]:
    texts = {
        "openloto": load_text("openloto_pozo.html"),
        "resultados": load_text("resultadosloto_pozo.html"),
    }
    iters = 2000

    timings: dict[str, dict[str, float]] = {"amounts": {}, "proximo": {}}
    for name, text in texts.items():
        t_old = timeit.timeit(
            lambda t=text: old_extract_amounts(t, allow_total=False), number=iters
        )
        t_new = timeit.timeit(
            lambda t=text: new._extract_amounts(t, allow_total=False), number=iters  # type: ignore[attr-defined]
        )
        timings["amounts"][name] = t_old / max(1, iters), t_new / max(1, iters)

        t_old2 = timeit.timeit(lambda t=text: old_extract_proximo_info(t), number=iters)
        t_new2 = timeit.timeit(
            lambda t=text: new._extract_proximo_info(t), number=iters  # type: ignore[attr-defined]
        )
        timings["proximo"][name] = t_old2 / max(1, iters), t_new2 / max(1, iters)

    return timings


if __name__ == "__main__":
    results = bench()
    print(json.dumps(results, indent=2))
