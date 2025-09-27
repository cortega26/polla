from __future__ import annotations

from pathlib import Path

from polla_app import net
from polla_app.sources import _24h, pozos, t13

FIX = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_t13_table_parse(monkeypatch):
    def fake_fetch(url, ua, timeout=20):
        return read_fixture("t13_sorteo_5198.html")

    monkeypatch.setattr(t13, "fetch_html", fake_fetch)
    record = t13.parse_t13_draw("https://example.test")
    assert isinstance(record["premios"], list)
    assert any(p["categoria"].lower().startswith("terna") for p in record["premios"])
    assert record["sorteo"] == 5198
    assert record["fecha"] == "2024-12-01"


def test_t13_paragraph_parse(monkeypatch):
    def fake_fetch(url, ua, timeout=20):
        return read_fixture("t13_sorteo_5322.html")

    monkeypatch.setattr(t13, "fetch_html", fake_fetch)
    record = t13.parse_t13_draw("https://example.test")
    assert record["sorteo"] == 5322
    assert len(record["premios"]) >= 3


def test_openloto_pozo(monkeypatch):
    def fake_fetch(url, ua=net.DEFAULT_UA, timeout=20):
        return read_fixture("openloto_pozo.html")

    monkeypatch.setattr(pozos, "fetch_html", fake_fetch)
    pozos_dict = pozos.get_pozo_openloto()
    assert "Loto Clásico" in pozos_dict
    assert pozos_dict["Total estimado"] == 4300000000


def test_resultadosloto_pozo(monkeypatch):
    def fake_fetch(url, ua=net.DEFAULT_UA, timeout=20):
        return read_fixture("resultadosloto_pozo.html")

    monkeypatch.setattr(pozos, "fetch_html", fake_fetch)
    pozos_dict = pozos.get_pozo_resultadosloto()
    assert pozos_dict["Loto Clásico"] == 650000000


def test_24h_index(monkeypatch):
    def fake_fetch(url, ua=net.DEFAULT_UA, timeout=20):
        return read_fixture("24h_tag_index.html")

    monkeypatch.setattr(_24h, "fetch_html", fake_fetch)
    entries = _24h.list_24h_result_urls("https://example.test", limit=5)
    assert entries[0]["sorteo"] == 5322
    assert len(entries) == 2


def test_24h_article(monkeypatch):
    def fake_fetch(url, ua=net.DEFAULT_UA, timeout=20):
        if "5322" in url:
            return read_fixture("24h_sorteo_5322.html")
        return read_fixture("24h_sorteo_5198.html")

    monkeypatch.setattr(_24h, "fetch_html", fake_fetch)
    record = _24h.parse_24h_draw("https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322")
    assert record["sorteo"] == 5322
    assert len(record["premios"]) == 3

