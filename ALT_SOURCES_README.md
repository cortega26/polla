
# Alternative Data Sources for Loto Chile (No WAF Interaction)

**Purpose**: Keep the repo updated with **post-draw prize breakdowns por categoría** and **next-draw jackpots (pozos)** without touching `polla.cl` or bypassing any WAF. This document provides **drop-in parsers**, **scheduling hints**, and **tests** optimized for an AI code assistant to implement quickly.

> TL;DR: Parse **24Horas** post-draw pages for *“Resultados del Loto: Ganadores”* (categoría · premio · ganadores). Optionally pull **próximo pozo** from **ResultadosLotoChile** (primary) and **OpenLoto** (fallback). Respect robots.txt, identify your UA, cache, and write provenance in your spreadsheet.

---

## Sources (examples)

- **24Horas** (running tag index of Loto result articles; good backup):  
  - Tag index: <https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html>  
  - robots.txt: <https://www.24horas.cl/robots.txt> (declares broad allow; still be polite)

- **OpenLoto** (community aggregator; next-draw *pozo por juego*):  
  - Próximo pozo: <https://www.openloto.cl/pozo-del-loto.html>

- **ResultadosLotoChile** (community aggregator; next-draw *pozo*):  
  - Próximo pozo: <https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/>

> Notes
> - Treat *pozo* figures from aggregators as **estimados**. Record the URL + timestamp.
> - If a 24Horas page structure changes, fall back to a text-scan heuristic (see parser below).

---

## Data Model (normalized)

**Goal**: A single JSON row per draw:

```json
{
  "sorteo": 5322,
  "fecha": "2025-09-16",
  "fuente": "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322",
  "premios": [
    {"categoria": "Loto 6 aciertos", "premio_clp": 0, "ganadores": 0},
    {"categoria": "Súper Quina (5 + comodín)", "premio_clp": 0, "ganadores": 0},
    {"categoria": "Quina (5)", "premio_clp": 757970, "ganadores": 3},
    {"categoria": "Súper Cuaterna (4 + comodín)", "premio_clp": 75800, "ganadores": 30},
    {"categoria": "Cuaterna (4)", "premio_clp": 5090, "ganadores": 447},
    {"categoria": "Súper Terna (3 + comodín)", "premio_clp": 3500, "ganadores": 650},
    {"categoria": "Terna (3)", "premio_clp": 1050, "ganadores": 7194},
    {"categoria": "Súper Dupla (2 + comodín)", "premio_clp": 1000, "ganadores": 4945},
    {"categoria": "RECARGADO (6)", "premio_clp": 0, "ganadores": 0},
    {"categoria": "REVANCHA (6)", "premio_clp": 0, "ganadores": 0},
    {"categoria": "DESQUITE (6)", "premio_clp": 0, "ganadores": 0},
    {"categoria": "Jubilazo $1.000.000", "premio_clp": 0, "ganadores": 0}
  ],
  "pozos_proximo": {
    "Loto Clásico": 690000000,
    "Recargado": 180000000,
    "Revancha": 100000000,
    "Desquite": 510000000,
    "Jubilazo $1.000.000": 960000000,
    "Total estimado": 4300000000
  }
}
```

**Normalization rules** (suggested):
- Keep `categoria` **verbatim** from the source page (avoid lossy mapping).
- Parse CLP as integers (no decimals) and store raw values.
- Always include `"fuente"` (URL you parsed) and set `"fecha"` if present on page; else derive from article text when safe.

---

## Implementation Plan (tasks for an AI code assistant)

### Task A — Add a polite fetch helper

**File**: `polla_app/net.py`

**Function signature**:
```python
def fetch_html(url: str, ua: str, timeout: int = 20) -> str:
    """GET url with a descriptive UA and minimal headers; raise for non-200; return text."""
```

**Requirements**:
- Headers: `User-Agent`, `Accept-Language` (`es-CL,es;q=0.9`).
- Back-off on 429 (sleep 60s; single retry).
- No JS/selenium. No proxy rotation. No WAF bypass.
- Optional: robots.txt check (record decision in logs).

---

### Task B — Parser: 24Horas article (primary)

**File**: `polla_app/sources/24h.py`

**Functions**:
```python
def list_24h_result_urls(index_url: str, limit: int = 10) -> list[str]:
    """Return last N article URLs from the Loto tag index."""

def parse_24h_draw(url: str) -> dict:
    # Parser implemented in polla_app/sources/_24h.py
    ...
```

---

**Notes**:
- The tag index at `<https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html>` lists recent result posts.
- Check `<https://www.24horas.cl/robots.txt>` (they declare broad allow). Be polite (1–2 requests/run).
- 24Horas article structure varies; keep a robust fallback (paragraph scan).

---

### Task D — Parser: Próximo *pozo* (estimado)

**File**: `polla_app/sources/pozos.py`

**Functions**:
```python
def get_pozo_openloto(url: str = "https://www.openloto.cl/pozo-del-loto.html") -> dict:
    """Return dict with keys like 'Loto Clásico', 'Recargado', etc. Parse MILLONES -> * 1_000_000."""

def get_pozo_resultadosloto(url: str = "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/") -> dict:
    """Same as above; use regex tolerant of accents & case. Return ints in CLP."""
```

**Important**:
- Mark results as **estimado** and include `"fuente"` + `"fetched_at"`.
- If both sources are available and differ, prefer the one with a more recent “last updated” text or keep both with a note.

---

### Task C — Integrate with your Spreadsheet writer

**File**: `polla_app/ingest.py`

**Function**:
```python
def ingest_draw(sorteo_url: str, source: str = "24h") -> dict:
    """Parse + write a row to Sheets. Return the record. Fields: sorteo, fecha, premios[], fuente."""
```

**Steps**:
1. `record = parse_24h_draw(url)`.
2. Append `"provenance"` column(s): `source`, `url`, and optional `"html_hash"` for idempotency.
3. Write list of category rows (long format) **or** a single JSON blob (wide format)—match your current sheet layout.
4. (Optional) Enrich with `pozos_proximo` from `get_pozo_openloto()` or `get_pozo_resultadosloto()`.

---

## Code Snippets (copy/paste ready)

### `polla_app/sources/t13.py`
Removed in favor of a single 24Horas parser.

### `polla_app/sources/24h.py`
```python
import re
from bs4 import BeautifulSoup
from .net import fetch_html

INDEX = "https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html"

def list_24h_result_urls(index_url: str = INDEX, limit: int = 10) -> list[str]:
    html = fetch_html(index_url, ua="OddsTransparencyBot/1.0 (+contact@example.com)")
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/loto/" in href or "resultados-loto" in href:
            if href.startswith("/"):
                href = "https://www.24horas.cl" + href
            urls.append(href)
        if len(urls) >= limit:
            break
    return urls

def parse_24h_draw(url: str) -> dict:
    # Parser implemented in polla_app/sources/_24h.py
    ...
```

### `polla_app/sources/pozos.py`
```python
import re
from bs4 import BeautifulSoup
from .net import fetch_html

def _parse_millones_to_clp(txt: str) -> int:
    # accept "690", "690 MILLONES", "$690 MILLONES"
    n = int(re.sub(r"[^0-9]", "", txt or "0") or "0")
    return n * 1_000_000

def get_pozo_openloto(url: str = "https://www.openloto.cl/pozo-del-loto.html") -> dict:
    html = fetch_html(url, ua="OddsTransparencyBot/1.0 (+contact@example.com)")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    pairs = {}
    # Known labels: Loto Clásico, Recargado, Revancha, Desquite, Jubilazo $1.000.000, Total estimado
    for label in ["Loto Clásico", "Recargado", "Revancha", "Desquite", "Jubilazo", "Total"]:
        m = re.search(label + r".{0,30}?\$?([\d\.]+)\s*MILLONES", text, re.I)
        if m:
            key = "Jubilazo $1.000.000" if label.startswith("Jubilazo") else label
            pairs[key] = _parse_millones_to_clp(m.group(1))
    return pairs

def get_pozo_resultadosloto(url: str = "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/") -> dict:
    html = fetch_html(url, ua="OddsTransparencyBot/1.0 (+contact@example.com)")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    labels = ["Loto", "Recargado", "Revancha", "Desquite", "Jubilazo"]
    pairs = {}
    for label in labels:
        m = re.search(label + r".{0,30}?\$?([\d\.]+)\s*MILLONES", text, re.I)
        if m:
            key = "Loto Clásico" if label == "Loto" else ("Jubilazo $1.000.000" if label=="Jubilazo" else label)
            pairs[key] = _parse_millones_to_clp(m.group(1))
    return pairs
```

---

## Tests (HTML fixtures)

**Folder**: `tests/fixtures/`  
- `t13_sorteo_5198.html` — saved source of the example page.  
- `t13_sorteo_5322.html` — saved source of the example page.  
- `openloto_pozo.html` — saved source of the pozo page.  
- `24h_tag_index.html` — saved source of the tag index page.

**File**: `tests/test_parsers.py`
Includes fixture-based tests for 24Horas parsing and pozo aggregators.

Run:
```bash
pytest -q
```

---

## Scheduler

**Strategy**: Run after each draw (3× semana). Use cron in America/Santiago and add jitter.

Example (GitHub Actions):
```yaml
name: ingest_alt_sources
on:
  schedule:
    - cron: "55 0 * * 2,4,0"  # ~21:55 America/Santiago; adjust to your repo timezone
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: python -m polla_app ingest --source 24h "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322"
```

---

## Politeness & Compliance

- **User-Agent**: Identify your project and contact.  
- **robots.txt**: Check and honor. 24Horas explicitly allows generic user-agents; still keep rate low.  
- **Rate limit**: 1–2 requests per run; cache last processed `sorteo`.  
- **No WAF interaction**: Do not touch `polla.cl` endpoints or attempt circumvention.  
- **Provenance**: Store `fuente` URL, parse timestamp, and (optional) `sha256(html)` to keep the run idempotent.  
- **Transparency**: If numbers differ across sources, record both and prefer the one with a clearly timestamped update.

---

## CLI (optional)

**File**: `polla_app/cli.py`
Use the built-in `polla_app.__main__` CLI instead.

Run:
```bash
python -m polla_app ingest --source 24h "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5298-martes-22-de-julio-de-2025--"
python -m polla_app pozos
```

---

## Troubleshooting

- **Table missing**: Use the paragraph fallback; some articles render *Ganadores* as text blocks.
- **Label variance**: Normalize only whitespace; don’t force names—your spreadsheet can map them later.
- **Pozo not found**: Switch aggregator or skip enrichment for that run; mark as `null` and continue.
- **HTTP 429**: Back off 60s, then retry once. If still 429, skip this run and log.

