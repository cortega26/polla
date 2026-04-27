from unittest.mock import MagicMock

import pytest

from polla_app.exceptions import ParseError
from polla_app.sources.pozos import get_pozo_polla


def test_get_pozo_polla_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_fetcher_cls = MagicMock()
    mock_fetcher_instance = MagicMock()
    mock_page = MagicMock()

    mock_page.status = 200
    mock_page.text = """
        <li>
            <span>POZO TOTAL ESTIMADO A REPARTIR ENTRE TODAS LAS CATEGORÍAS</span>
            <span class="prize">$2.300</span>
            <span>MILLONES</span>
        </li>
        <li class="sub-game">
            <span class="img-wrap"><img src="/static/assets/new_loto_logo.png"/></span>
            <span class="prize">$140</span>
            <span>MILLONES</span>
        </li>
        Fecha Próximo Sorteo: 26 de abril de 2026 Sorteo N° 5417
    """
    mock_page.text_content = mock_page.text

    mock_fetcher_instance.fetch.return_value = mock_page
    mock_fetcher_cls.return_value = mock_fetcher_instance

    monkeypatch.setattr("scrapling.StealthyFetcher", mock_fetcher_cls)

    result = get_pozo_polla()

    assert result["user_agent"] == "Scrapling/StealthyFetcher"
    assert result["fuente"] == "https://www.polla.cl/es/"
    assert result["estimado"] is True
    assert result["montos"]["Total estimado"] == 2300000000
    assert result["montos"]["Loto Clásico"] == 140000000
    assert result["sorteo"] == 5417
    assert result["fecha"] == "2026-04-26"


def test_get_pozo_polla_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_fetcher_cls = MagicMock()
    mock_fetcher_instance = MagicMock()
    mock_page = MagicMock()

    mock_page.status = 403
    mock_fetcher_instance.fetch.return_value = mock_page
    mock_fetcher_cls.return_value = mock_fetcher_instance

    monkeypatch.setattr("scrapling.StealthyFetcher", mock_fetcher_cls)

    with pytest.raises(ParseError, match="Polla.cl returned status 403"):
        get_pozo_polla()


def test_extract_proximo_info_new_formats() -> None:
    from polla_app.sources.pozos import _extract_proximo_info

    # Test format: Resultados Sorteo : 5417 Fecha : abril 26, 2026
    text = "Resultados Sorteo : 5417 Fecha : abril 26, 2026"
    sorteo, fecha = _extract_proximo_info(text)
    assert sorteo == 5417
    assert fecha == "2026-04-26"

    # Test format: Próximo sorteo número 5418, será sorteado el martes, 28 de abril del 2026.
    text2 = "Próximo sorteo número 5418, será sorteado el martes, 28 de abril del 2026."
    sorteo2, fecha2 = _extract_proximo_info(text2)
    assert sorteo2 == 5418
    assert fecha2 == "2026-04-28"

    # Test format: Sorteo #24298 abril 27, 2026
    text3 = "Sorteo #24298 abril 27, 2026"
    sorteo3, fecha3 = _extract_proximo_info(text3)
    assert sorteo3 == 24298
    assert fecha3 == "2026-04-27"
