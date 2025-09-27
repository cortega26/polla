from __future__ import annotations

from polla_app.ingest import collect_report


def test_collect_report(monkeypatch, app_config, read_fixture):
    fixtures = {
        "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5198-del-domingo-1-diciembre-2024": "t13_sorteo_5198.html",
        "https://www.t13.cl/noticia/nacional/resultados-del-loto-sorteo-5322-del-martes-16-septiembre-2025": "t13_sorteo_5322.html",
        app_config.sources.h24_tag_url: "24h_tag_index.html",
        "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5322-martes-16-de-septiembre-de-2025": "24h_sorteo_5322.html",
        "https://www.24horas.cl/te-sirve/loto/resultados-loto-sorteo-5198-domingo-1-de-diciembre-2024": "24h_sorteo_5198.html",
        app_config.sources.openloto_url: "openloto_pozo.html",
        app_config.sources.resultadosloto_url: "resultadosloto_pozo.html",
    }

    from polla_app.sources import _24h, pozos, t13

    def fake_fetch(url, ua=None, timeout=20):
        filename = fixtures.get(url)
        assert filename, f"URL inesperada {url}"
        return read_fixture(filename)

    monkeypatch.setattr(t13, "fetch_html", fake_fetch)
    monkeypatch.setattr(_24h, "fetch_html", fake_fetch)
    monkeypatch.setattr(pozos, "fetch_html", fake_fetch)

    report = collect_report(app_config)
    assert report.sorteo == 5322
    assert report.primary.fuente.endswith("5322-del-martes-16-septiembre-2025")
    assert report.secondary_sources
    assert report.comparisons[0].matches is False
    assert report.jackpots

    sheet_values = report.to_sheet_values()
    assert sheet_values[0][1] == 5322
    assert any("OpenLoto" in row[0] for row in sheet_values if isinstance(row, list))

