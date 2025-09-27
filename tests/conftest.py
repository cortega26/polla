from pathlib import Path
from typing import Callable, Iterator

import pytest

from polla_app.config import AppConfig

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def app_config() -> AppConfig:
    config = AppConfig.create_default()
    config.sources.t13_urls = [
        "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5198-del-domingo-1-diciembre-2024",
        "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5322-del-martes-16-septiembre-2025",
    ]
    return config


@pytest.fixture()
def fixture_path() -> Path:
    return FIXTURES


@pytest.fixture()
def read_fixture() -> Iterator[Callable[[str], str]]:
    def _reader(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    yield _reader

