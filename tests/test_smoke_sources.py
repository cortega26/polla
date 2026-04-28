import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from polla_app.net import FetchMetadata
from polla_app.sources.pozos import get_pozo_openloto, get_pozo_polla

# Mapping of source directory names to their fetcher functions
SOURCE_MAP = {
    "polla": get_pozo_polla,
    "openloto": get_pozo_openloto,
}

FIXTURE_BASE = Path(__file__).parent / "fixtures" / "sources"


def get_source_dirs() -> list[str]:
    if not FIXTURE_BASE.exists():
        return []
    return [d.name for d in FIXTURE_BASE.iterdir() if d.is_dir()]


@pytest.mark.parametrize("source_name", get_source_dirs())
def test_source_smoke_fixture(source_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    source_dir = FIXTURE_BASE / source_name
    html_path = source_dir / "page.html"
    expected_path = source_dir / "expected.json"

    assert html_path.exists(), f"Missing page.html for {source_name}"
    assert expected_path.exists(), f"Missing expected.json for {source_name}"

    html_content = html_path.read_text(encoding="utf-8")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    fetcher = SOURCE_MAP.get(source_name)
    if not fetcher:
        pytest.skip(f"No fetcher mapped for source: {source_name}")

    # Mock the appropriate network layer
    if source_name == "polla":
        # Polla uses scrapling.StealthyFetcher
        mock_fetcher_cls = MagicMock()
        mock_fetcher_instance = MagicMock()
        mock_page = MagicMock()
        mock_page.status = 200
        mock_page.text = html_content
        mock_page.text_content = html_content
        mock_fetcher_instance.fetch.return_value = mock_page
        mock_fetcher_cls.return_value = mock_fetcher_instance
        monkeypatch.setattr("scrapling.StealthyFetcher", mock_fetcher_cls)
    else:
        # Others use fetch_html
        from datetime import datetime, timezone

        metadata = FetchMetadata(
            url="http://mock-source.test",
            user_agent="smoke-test",
            fetched_at=datetime.now(timezone.utc),
            html=html_content,
        )
        monkeypatch.setattr("polla_app.sources.pozos.fetch_html", lambda *_, **__: metadata)

    # Execute
    result = fetcher()

    # Verify results
    for key, expected_val in expected.items():
        assert result[key] == expected_val, f"Mismatch in {key} for {source_name}"
