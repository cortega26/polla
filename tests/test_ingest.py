from __future__ import annotations

import copy

import pytest

from polla_app import ingest


@pytest.fixture
def draw_record() -> dict[str, object]:
    return {
        "sorteo": 5198,
        "fecha": "2024-12-01",
        "fuente": "https://example.test/t13/5198",
        "premios": [
            {"categoria": "Loto 6 aciertos", "premio_clp": 0, "ganadores": 0},
        ],
        "provenance": {},
    }


def test_ingest_draw_merges_pozo_data(monkeypatch, draw_record) -> None:
    monkeypatch.setitem(ingest.PARSERS, "t13", lambda url: copy.deepcopy(draw_record))

    primary = {
        "fuente": "https://openloto.test",
        "fetched_at": "2024-12-02T00:00:00+00:00",
        "montos": {"Loto Clásico": 123_000_000},
        "user_agent": "pytest",
        "estimado": True,
    }
    alternative = {
        "fuente": "https://resultado.test",
        "fetched_at": "2024-12-02T00:05:00+00:00",
        "montos": {"Recargado": 456_000_000},
        "user_agent": "pytest",
        "estimado": True,
    }

    monkeypatch.setattr(ingest, "POZO_FETCHERS", (lambda: primary, lambda: alternative))

    record = ingest.ingest_draw("https://example.test/t13/5198", source="t13")

    assert record["pozos_proximo"]["Loto Clásico"] == 123_000_000
    assert record["pozos_proximo"]["Recargado"] == 456_000_000
    assert record["provenance"]["pozos"]["primary"]["fuente"] == "https://openloto.test"
    assert record["provenance"]["pozos"]["alternatives"][0]["fuente"] == "https://resultado.test"


def test_ingest_draw_without_pozos(monkeypatch, draw_record) -> None:
    monkeypatch.setitem(ingest.PARSERS, "t13", lambda url: copy.deepcopy(draw_record))
    monkeypatch.setattr(ingest, "POZO_FETCHERS", tuple())

    record = ingest.ingest_draw("https://example.test/t13/5198", source="t13", include_pozos=False)

    assert "pozos_proximo" not in record
    assert record["provenance"]["source"] == "t13"
    assert "ingested_at" in record["provenance"]
