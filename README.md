# Polla.cl Prize Scraper v2.0

Async Playwright-based scraper for Chilean lottery (Polla.cl) prize data with Google Sheets integration.

## Features

- **Async Playwright**: Modern, fast, and reliable browser automation
- **Robust error handling**: Detects and handles WAF/captcha blocks gracefully
- **Session persistence**: Maintains cookies across runs via `storage_state.json`
- **Google Sheets integration**: Updates spreadsheet automatically with prize data
- **Comprehensive testing**: 85%+ test coverage with pytest
- **CI/CD ready**: GitHub Actions workflow for automated daily scraping
- **Type-safe**: Full type hints with mypy validation

## Installation

### Production
```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps
```

### Development
```bash
pip install -r requirements-dev.txt
playwright install chromium
playwright install-deps
```

## Usage

### Command Line
```bash
# Run headless (default)
python -m polla_app scrape

# Run with visible browser
python -m polla_app scrape --show

# With custom timeout and log level
python -m polla_app scrape --timeout 60 --log-level DEBUG
```

### Environment Variables
- `CREDENTIALS`: Google service account JSON credentials (required)
- `DISABLE_HEADLESS`: Set to "true" to run headed (deprecated, use --show flag)

## Architecture

### Core Components

- **PlaywrightManager**: Manages browser lifecycle and configuration
- **PollaScraper**: Implements scraping logic with retry mechanism
- **GoogleSheetsManager**: Handles spreadsheet updates
- **PrizeData**: Data model for the 7 lottery prize values

### Error Handling

The scraper implements smart error detection:
- **ACCESS_DENIED**: WAF/captcha detected, saves screenshot and exits
- **TIMEOUT_ERROR**: Page load timeout
- **SCRAPE_ERROR**: General scraping failure
- **UPDATE_ERROR**: Google Sheets update failure

Exit codes:
- 0: Success
- 1: General error
- 2: Access denied
- 3: Unexpected error

## Development

### Running Tests
```bash
# Run all tests
make test

# With coverage
make test-cov

# Specific test file
pytest tests/test_parser.py -v
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

## CI/CD

GitHub Actions workflow runs:
1. **On push**: Linting, type checking, and tests
2. **Daily schedule**: Full scraping job at 10:00 AM Chile time
3. **Manual trigger**: Via workflow dispatch

## Migration from Selenium

Key improvements over the Selenium version:
- Async/await pattern for better performance
- Native Playwright wait strategies (no explicit sleeps)
- Built-in auto-waiting for elements
- Simplified cookie persistence
- Removed stealth libraries and CDP hacks
- Cleaner error handling with structured exceptions

## License

MIT
