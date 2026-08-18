.PHONY: help install install-dev format lint type-check test test-cov clean run run-kino ready

help:
	@echo "Available commands:"
	@echo "  install      Install production dependencies"
	@echo "  install-dev  Install development dependencies"
	@echo "  format       Format code with black"
	@echo "  lint         Run ruff linter"
	@echo "  type-check   Run mypy type checker"
	@echo "  test         Run tests"
	@echo "  test-cov     Run tests with coverage"
	@echo "  clean        Clean cache and build files"
	@echo "  run          Run the scraper"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

format:
	black polla_app tests

lint:
	ruff check polla_app tests

type-check:
	mypy polla_app

test:
	pytest -q

test-cov:
	pytest --cov=polla_app --cov-report=term-missing --cov-report=html

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf debug logs storage_state.json

run:
	@echo "Ejecutando el pipeline de pozos (Loto)..."
	python -m polla_app run --sources pozos

run-kino:
	@echo "Ejecutando el pipeline de Kino (Lotería de Concepción)..."
	python -m polla_app run --sources kino

ready:
	SKIP=check-unstaged pre-commit run --all-files
	git add .
