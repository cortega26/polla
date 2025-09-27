
# Alternative Data Sources for Loto Chile (No WAF Interaction)

**Purpose**: Keep the repo updated with **post-draw prize breakdowns por categoría** and **next-draw jackpots (pozos)** without touching `polla.cl` or bypassing any WAF. This document provides **drop-in parsers**, **scheduling hints**, and **tests** optimized for an AI code assistant to implement quickly.

> TL;DR: Parse **T13** post-draw pages for *“Resultados del Loto: Ganadores”* (categoría · premio · ganadores). Use **24Horas** posts as a backup, and optionally pull **próximo pozo** from **OpenLoto** or **ResultadosLotoChile**. Respect robots.txt, identify your UA, cache, and write provenance in your spreadsheet.

---

## Sources (examples)

- **T13** (per-draw article, includes the *Ganadores* table):  
  - Example (Sorteo 5322): <https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5322-del-martes-16-septiembre-16-9-2025>  
  - Example (Sorteo 5198): <https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5198-del-domingo-1-diciembre-2-12-2024>

- **24Horas** (running tag index of Loto result articles; good backup):  
  - Tag index: <https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html>  
  - robots.txt: <https://www.24horas.cl/robots.txt> (declares broad allow; still be polite)

- **OpenLoto** (community aggregator; next-draw *pozo por juego*):  
  - Próximo pozo: <https://www.openloto.cl/pozo-del-loto.html>

- **ResultadosLotoChile** (community aggregator; next-draw *pozo*):  
  - Próximo pozo: <https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/>

> Notes
> - Treat *pozo* figures from aggregators as **estimados**. Record the URL + timestamp.
> - If a T13 page structure changes, fall back to a text-scan heuristic (see parser below).

---

## Data Model (normalized)

**Goal**: A single JSON row per draw:

```json
{
  "sorteo": 5322,
  "fecha": "2025-09-16",
  "fuente": "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5322-del-martes-16-septiembre-16-9-2025",
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

### Task B — Parser: T13 *“Ganadores”* table

**File**: `polla_app/sources/t13.py`

**Function**:
```python
def parse_t13_draw(url: str) -> dict:
    """
    Return {"sorteo": int|None, "fecha": "YYYY-MM-DD"|None, "fuente": url, "premios": [..]}.
    Strategy:
      1) Find H2/H3 containing "Ganadores"; read the next <table> rows.
      2) If no table, scan nearby paragraphs for "Categoría ... $monto ... n".
      3) Extract 'sorteo' and 'fecha' from page text if present.
    """
```

**Heuristics**:
- Column headers typically: **Categoría | Premio | Ganadores**.
- Clean numbers: remove `.` and `$`; parse to `int` (CLP). Default `ganadores=0` if blank.
- Accept alternate category labels: `"Súper Cua Terna"` vs `"Súper Cuaterna"` (normalize spacing only).

**Edge cases**:
- Zero jackpot categories show `$0 | 0`.
- Extra sections like `RECARGADO`, `REVANCHA`, `DESQUITE`, `Jubilazo` may appear; keep them.

---

### Task C — Parser: 24Horas article (backup)

**File**: `polla_app/sources/24h.py`

**Functions**:
```python
def list_24h_result_urls(index_url: str, limit: int = 10) -> list[str]:
    """Return last N article URLs from the Loto tag index."""

def parse_24h_draw(url: str) -> dict:
    """Mirror Task B: try to read a table, else text-scan for Categoría/Premio/Ganadores."""
```

**Notes**:
- The tag index at `<https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html>` lists recent result posts.
- Check `<https://www.24horas.cl/robots.txt>` (they declare broad allow). Be polite (1–2 requests/run).
- 24Horas article structure varies more than T13; keep a robust fallback (paragraph scan).

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

### Task E — Integrate with your Spreadsheet writer

**File**: `polla_app/ingest.py`

**Function**:
```python
def ingest_draw(sorteo_url: str, source: str = "t13") -> dict:
    """Parse + write a row to Sheets. Return the record. Fields: sorteo, fecha, premios[], fuente."""
```

**Steps**:
1. `record = parse_t13_draw(url)` or `parse_24h_draw(url)` depending on `source`.
2. Append `"provenance"` column(s): `source`, `url`, and optional `"html_hash"` for idempotency.
3. Write list of category rows (long format) **or** a single JSON blob (wide format)—match your current sheet layout.
4. (Optional) Enrich with `pozos_proximo` from `get_pozo_openloto()` or `get_pozo_resultadosloto()`.

---

## Code Snippets (copy/paste ready)

### `polla_app/sources/t13.py`
```python
import re, datetime as dt
from bs4 import BeautifulSoup
from .net import fetch_html

def _to_int(s: str) -> int:
    return int(re.sub(r"[^0-9]", "", s or "0") or "0")

def parse_t13_draw(url: str) -> dict:
    html = fetch_html(url, ua="OddsTransparencyBot/1.0 (+contact@example.com)")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # sorteo and date (best-effort)
    m_sor = re.search(r"[Ss]orteo\s+(\d{4,})", text)
    sorteo = int(m_sor.group(1)) if m_sor else None

    m_date = re.search(r"(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})", text)  # e.g., 16 de septiembre de 2025
    fecha = None
    if m_date:
        try:
            months = {
                "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
                "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,"noviembre":11,"diciembre":12
            }
            d, mes, y = re.findall(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", m_date.group(1))[0]
            fecha = dt.date(int(y), months[mes.lower()], int(d)).isoformat()
        except Exception:
            fecha = None

    # Locate "Ganadores" table
    anchor = None
    for tag in soup.find_all(["h2","h3"]):
        if "Ganadores" in tag.get_text(strip=True):
            anchor = tag
            break

    premios = []
    table = anchor.find_next("table") if anchor else None
    if table:
        rows = table.find_all("tr")
        # Skip header if present
        start = 1 if rows and "Categoría" in rows[0].get_text() else 0
        for tr in rows[start:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td","th"])]
            if len(cells) >= 3:
                categoria, premio, ganadores = cells[0], cells[1], cells[2]
                premios.append({
                    "categoria": re.sub(r"\s+", " ", categoria).strip(),
                    "premio_clp": _to_int(premio),
                    "ganadores": _to_int(ganadores),
                })

    # Fallback: greedy pattern in paragraphs
    if not premios:
        block = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
        pat = re.compile(r"([A-Za-z\s\u00C0-\u017F\$\d\(\)\+]+?)\s*\$([\d\.]+)\s*(\d+)", re.I)
        for cat, monto, gan in pat.findall(block):
            premios.append({
                "categoria": re.sub(r"\s+", " ", cat).strip(),
                "premio_clp": _to_int(monto),
                "ganadores": _to_int(gan),
            })

    return {"sorteo": sorteo, "fecha": fecha, "fuente": url, "premios": premios}
```

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
    # Mirror parse_t13_draw; structure varies more, so rely on text-fallback.
    from .t13 import parse_t13_draw as _parse  # reuse logic
    return _parse(url)
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
```python
from polla_app.sources.t13 import parse_t13_draw
from polla_app.sources.pozos import get_pozo_openloto
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"

def read_fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")

def test_t13_table_parse(monkeypatch):
    def fake_fetch(url, ua, timeout=20):
        return read_fixture("t13_sorteo_5198.html")
    monkeypatch.setenv("NO_NET", "1")
    from polla_app import net
    net.fetch_html = fake_fetch
    record = parse_t13_draw("https://example.test")
    assert isinstance(record["premios"], list)
    assert any(p["categoria"].lower().startswith("terna") for p in record["premios"])

def test_openloto_pozo(monkeypatch):
    def fake_fetch(url, ua, timeout=20):
        return read_fixture("openloto_pozo.html")
    from polla_app import net
    net.fetch_html = fake_fetch
    pozos = get_pozo_openloto()
    assert "Loto Clásico" in pozos
    assert pozos["Loto Clásico"] > 0
```

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
      - run: python -m polla_app.cli ingest --source t13 --latest-from 24h
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
```python
import argparse, json
from .sources.t13 import parse_t13_draw
from .sources._24h import parse_24h_draw, list_24h_result_urls
from .sources.pozos import get_pozo_openloto, get_pozo_resultadosloto

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["t13", "24h", "pozos"])
    ap.add_argument("--url")
    args = ap.parse_args()

    if args.cmd == "t13":
        print(json.dumps(parse_t13_draw(args.url), ensure_ascii=False, indent=2))
    elif args.cmd == "24h":
        print(json.dumps(parse_24h_draw(args.url), ensure_ascii=False, indent=2))
    else:
        p = get_pozo_openloto() or {}
        q = get_pozo_resultadosloto() or {}
        print(json.dumps({"openloto": p, "resultadoslotochile": q}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

Run:
```bash
python -m polla_app.cli t13 --url "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5198-del-domingo-1-diciembre-2-12-2024"
python -m polla_app.cli 24h --url "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5298-martes-22-de-julio-de-2025--"
python -m polla_app.cli pozos
```

---

## Troubleshooting

- **Table missing**: Use the paragraph fallback; T13 sometimes renders *Ganadores* as text blocks.
- **Label variance**: Normalize only whitespace; don’t force names—your spreadsheet can map them later.
- **Pozo not found**: Switch aggregator or skip enrichment for that run; mark as `null` and continue.
- **HTTP 429**: Back off 60s, then retry once. If still 429, skip this run and log.
