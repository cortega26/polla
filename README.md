# Polla Transparency Ingestor v3.0

HTTP-based ingestion pipeline that leverages public media and community sources to keep Chilean Loto
results transparent without interacting with `polla.cl`.

## Features

- **Polite HTTP fetching**: Custom User-Agent, robots.txt awareness, 429 back-off.
- **Multi-source parsing**: T13, 24Horas, OpenLoto, and ResultadosLotoChile.
- **Data validation**: Cross-check prize tables across sources and highlight discrepancies.
- **Google Sheets export**: Structured summary containing provenance, prize breakdown, and next jackpots.
- **CLI utilities**: Inspect individual sources or run the full ingest workflow.
- **Type-safe**: Full type hints with mypy validation.

## Installation

### Production
```bash
pip install -r requirements.txt
```

### Development
```bash
pip install -r requirements-dev.txt
```

## Usage

### Command Line

```bash
# Run ingest providing explicit T13 URL(s)
python -m polla_app.cli ingest --config-t13 "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5198-del-domingo-1-diciembre-2-12-2024"

# Inspect a single T13 or 24Horas note
python -m polla_app.cli t13 "https://www.t13.cl/noticia/..."
python -m polla_app.cli h24 "https://www.24horas.cl/..."
```

### Environment Variables
- `CREDENTIALS`: Google service account JSON credentials (required)

## Architecture

### Core Components

- **`net.fetch_html`**: HTTP helper that respects robots.txt and throttling.
- **Source parsers**: Convert HTML from T13/24Horas/OpenLoto/ResultadosLotoChile into normalized objects.
- **`ingest.collect_report`**: Combines sources, determines the latest draw, and compares prize tables.
- **`GoogleSheetsManager`**: Publishes the structured report and tracks the last recorded draw.

### Error Handling

- **SIN_T13**: No configured T13 URLs.
- **SIN_DATOS_T13**: All T13 parses failed.
- **NO_PREMIOS / 24H_NO_PREMIOS**: Prize tables missing.
- **SHEETS_* errors**: Google Sheets read/write issues.

## Development

### Running Tests
```bash
# Run all tests
make test
```

### Code Quality
```bash
# Format code
make format

# Run linter
make lint

# Type checking
make type-check
```

## License

MIT
