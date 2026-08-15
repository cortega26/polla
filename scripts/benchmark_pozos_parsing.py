"""Micro-benchmarks for pozos parsing paths (production code only).

Measures parsing throughput of the production extractors against the
150ms-per-parse target (see docs/SLOs.md). Run:

    python scripts/benchmark_pozos_parsing.py
"""

import functools
import json
import sys
import timeit
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polla_app.sources import pozos  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def load_text(name: str) -> str:
    """Load a fixture and reduce it the same way the production fetcher does."""
    html = (FIXTURES / name).read_text(encoding="utf-8")
    from typing import cast

    from bs4 import BeautifulSoup

    return cast(str, BeautifulSoup(html, "html.parser").get_text(" ", strip=True))


def _avg_ms(fn: Callable[[str], Any], text: str, iters: int) -> float:
    """Average per-call time in milliseconds over ``iters`` runs."""
    return timeit.timeit(functools.partial(fn, text), number=iters) / max(1, iters) * 1000


def bench() -> dict[str, Any]:
    texts = {
        "openloto": load_text("openloto_pozo.html"),
        "resultados": load_text("resultadosloto_pozo.html"),
    }
    iters = 2000

    extract_amounts = functools.partial(pozos._extract_amounts, allow_total=False)
    timings: dict[str, dict[str, float]] = {"amounts": {}, "proximo": {}}
    for name, text in texts.items():
        timings["amounts"][name] = _avg_ms(extract_amounts, text, iters)
        timings["proximo"][name] = _avg_ms(pozos._extract_proximo_info, text, iters)

    total_ms = sum(sum(v for v in game.values()) for game in timings.values())
    return {**timings, "total_ms": total_ms}


if __name__ == "__main__":
    results = bench()
    print(json.dumps(results, indent=2))
    total = results.get("total_ms", 0.0)
    print(f"\nTotal por parse (4 combinaciones): {total:.2f} ms")
