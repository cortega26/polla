"""Application configuration for alternative Loto data ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


DEFAULT_T13_URLS: list[str] = []


@dataclass
class NetworkConfig:
    """Network related configuration."""

    user_agent: str = (
        "polla-alt-scraper/3.0 (+https://github.com/your-org/polla-transparency)"
    )
    accept_language: str = "es-CL,es;q=0.9"
    timeout: int = 20
    backoff_seconds: int = 60
    max_retries: int = 1


@dataclass
class SourceConfig:
    """Configuration pointing to known alternative sources."""

    t13_urls: list[str] = field(default_factory=lambda: list(DEFAULT_T13_URLS))
    h24_tag_url: str = "https://www.24horas.cl/24horas/site/tag/port/all/tagport_2312_1.html"
    openloto_url: str = "https://www.openloto.cl/pozo-del-loto.html"
    resultadosloto_url: str = "https://resultadoslotochile.com/pozo-para-el-proximo-sorteo/"

    def iter_t13_urls(self) -> Sequence[str]:
        """Return configured T13 URLs."""

        return tuple(self.t13_urls)


@dataclass
class GoogleConfig:
    """Google Sheets configuration settings."""

    spreadsheet_id: str = "16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc"
    range_name: str = "Sheet1!A1:H"
    scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/spreadsheets",)
    retry_attempts: int = 3
    retry_delay: int = 5
    read_range: str = "Sheet1!A1:H"


@dataclass
class AppConfig:
    """Top level configuration container."""

    network: NetworkConfig = field(default_factory=NetworkConfig)
    sources: SourceConfig = field(default_factory=SourceConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)

    @classmethod
    def create_default(cls) -> "AppConfig":
        """Create a default configuration instance."""

        return cls()

