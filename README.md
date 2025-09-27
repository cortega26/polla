# Polla App — Alternative Lottery Source Ingestor

This project normalises **Loto Chile** results without touching `polla.cl`. It
parses public news articles (T13, 24Horas) and community aggregators to produce
a consistent JSON structure containing per-categoría payouts and próximo pozo
estimates.

## Features

- ✅ **No WAF interaction** – HTTP requests are performed with `requests` and a
  descriptive User-Agent, honouring `robots.txt`.
- 📰 **Multiple draw sources** – Parse T13 draw articles and fall back to
  24Horas posts when necessary.
- 💰 **Próximo pozo enrichment** – Fetch jackpot estimates from OpenLoto and
  ResultadosLotoChile, keeping provenance metadata.
- 🧪 **Deterministic tests** – Parsers are covered with fixture-based unit tests.
- 🛠️ **CLI tooling** – Inspect draw URLs, list recent 24Horas posts, and fetch
  pozo estimates directly from the command line.

## Installation

```bash
pip install -r requirements.txt
```

For local development with formatting and linting tools:

```bash
pip install -r requirements-dev.txt
```

## Usage

### Parse a draw

```bash
python -m polla_app ingest --source t13 "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5198"
```

- `--source` accepts `t13` (default) or `24h`.
- `--no-pozos` disables próximo pozo enrichment.
- `--compact` prints the record on a single JSON line.

### List recent 24Horas result posts

```bash
python -m polla_app list-24h --limit 5
```

### Fetch próximo pozo estimates

```bash
python -m polla_app pozos
```

## Data Model

Each draw record emitted by `ingest` follows this schema:

```json
{
  "sorteo": 5322,
  "fecha": "2025-09-16",
  "fuente": "https://www.t13.cl/…",
  "premios": [
    {"categoria": "Loto 6 aciertos", "premio_clp": 0, "ganadores": 0},
    {"categoria": "Quina (5)", "premio_clp": 757970, "ganadores": 3}
  ],
  "pozos_proximo": {
    "Loto Clásico": 690000000,
    "Recargado": 180000000,
    "Total estimado": 4300000000
  },
  "provenance": {
    "source": "t13",
    "url": "https://www.t13.cl/…",
    "ingested_at": "2025-09-17T02:15:00+00:00",
    "pozos": {"primary": {"fuente": "https://www.openloto.cl/…"}}
  }
}
```

## Development

### Tests

```bash
pytest -q
```

### Formatting & Linting

```bash
black polla_app tests
ruff check polla_app tests
```

## License

MIT
