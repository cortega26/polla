# Plan 009: Reutilizar una sola instancia de StealthyFetcher por corrida (pozos polla + precios Loto)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/sources/pozos.py polla_app/sources/prices.py polla_app/sources/browser.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: MED
- **Depends on**: 007 (ambos tocan `sources/prices.py`; ejecutar 007 primero)
- **Category**: perf
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

Cada corrida puede lanzar el navegador headless **dos veces**: una en
`get_pozo_polla` (`polla_app/sources/pozos.py:317` →
`fetcher = StealthyFetcher(headless=True)`) y otra en el fallback de precios
(`polla_app/sources/prices.py` → `_fetch_game_page` →
`fetcher = StealthyFetcher(headless=True)`). Cada lanzamiento de Chromium
cuesta varios segundos (inicialización del perfil persistente) y duplica el
tiempo total de corrida cuando ambos caminos se ejecutan. Un singleton a nivel
de proceso, siguiendo el precedente del rate limiter del repo ("controlled
caches", ver `polla_app/net.py` `fetch_html._last_seen`), reduce a un único
lanzamiento.

## Current state

- `polla_app/sources/pozos.py:316-318`:

```python
        # StealthyFetcher can take some time to initialize; we use the timeout for the fetch itself
        fetcher = StealthyFetcher(headless=True)
```

- `polla_app/sources/prices.py` (`_fetch_game_page`, ~líneas 185-196):

```python
        LOGGER.info("Plain fetch of %s failed (%s); retrying with browser", url, type(exc).__name__)
        try:
            fetcher = StealthyFetcher(headless=True)
            page = fetcher.fetch(url, timeout=timeout)
```

- Precedente de caché controlada: `polla_app/net.py` usa un atributo de
  función como estado (`fetch_html._last_seen`) para el rate limiter — el
  patrón aceptado en este repo para estado global controlado.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest -q`    | todo pasa |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/sources/browser.py` — NUEVO módulo con el singleton
- `polla_app/sources/pozos.py` — usar el singleton en `get_pozo_polla`
- `polla_app/sources/prices.py` — usar el singleton en `_fetch_game_page`
- `tests/test_browser.py` — NUEVO test del singleton

**Out of scope**:
- Cambiar el comportamiento de fetch de Scrapling (timeouts, retries).
- Tocar `kino.py`, `net.py`.
- Ninguna refactorización de `get_pozo_polla` más allá de la línea del fetcher.

## Git workflow

- Branch: `advisor/009-browser-singleton`
- Un commit: `perf(sources): reutilizar una sola instancia de StealthyFetcher por corrida`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Crear `polla_app/sources/browser.py`

Crea el módulo con un singleton perezoso (thread-safe no es necesario:
proceso único; sigue el estilo del repo — imports con `from __future__ import
annotations`, docstring, typing estricto):

```python
"""Shared headless-browser fetcher for sources that block plain HTTP.

poll a.cl blocks plain HTTP clients from some networks; the pipeline falls
back to Scrapling's StealthyFetcher. A single instance is reused per process
to avoid launching Chromium more than once per run.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

_fetcher: Any | None = None


def get_stealthy_fetcher() -> Any:
    """Return the process-wide StealthyFetcher instance, creating it once."""
    global _fetcher  # noqa: PLW0603 - controlled process-wide cache (see net.py rate limiter)
    if _fetcher is None:
        from scrapling import StealthyFetcher

        _fetcher = StealthyFetcher(headless=True)
        LOGGER.info("Launched shared StealthyFetcher instance")
    return _fetcher


__all__ = ["get_stealthy_fetcher"]
```

(Revisa si ruff exige `PLW0603` en la lista de selección — el repo selecciona
E/W/F/I/B/UP/N; `global` no está en la lista, así que el `noqa` puede omitirse
si ruff no lo exige; pruébalo y ajusta.)

**Verify**: `ruff check polla_app/sources/browser.py` → exit 0.

### Step 2: Usar el singleton en `pozos.py`

En `polla_app/sources/pozos.py`, dentro de `get_pozo_polla`, reemplaza:

```python
        fetcher = StealthyFetcher(headless=True)
```

por:

```python
        from .browser import get_stealthy_fetcher

        fetcher = get_stealthy_fetcher()
```

(El `from scrapling import StealthyFetcher` de arriba sigue siendo necesario
para el chequeo de import opcional — déjalo tal cual.)

**Verify**: `python -m pytest tests/test_pozo_polla.py tests/test_smoke_sources.py -q` → todo pasa
(los tests existentes mockean `scrapling.StealthyFetcher`; verifica que siguen
mockeando la clase — si el mock apunta a `scrapling.StealthyFetcher` y ahora
el import va por `browser.py`, ajusta el mock a
`polla_app.sources.browser.StealthyFetcher`... en realidad el import vive
dentro de `get_stealthy_fetcher`, así que el mock debe apuntar a
`polla_app.sources.browser.StealthyFetcher`. Si un test falla por esto,
actualiza SOLO el destino del monkeypatch en ese test — es parte de este plan).

### Step 3: Usar el singleton en `prices.py`

En `polla_app/sources/prices.py`, dentro de `_fetch_game_page`, reemplaza:

```python
            fetcher = StealthyFetcher(headless=True)
```

por:

```python
            from .browser import get_stealthy_fetcher

            fetcher = get_stealthy_fetcher()
```

**Verify**: `python -m pytest tests/test_prices.py -q` → todo pasa.

### Step 4: Test del singleton

Crea `tests/test_browser.py`:

```python
"""Tests for the shared StealthyFetcher singleton."""

from __future__ import annotations

import pytest


def test_get_stealthy_fetcher_returns_same_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    from polla_app.sources import browser

    instances: list[object] = []

    class FakeFetcher:
        def __init__(self, **kwargs: object) -> None:
            instances.append(self)

    monkeypatch.setattr(browser, "_fetcher", None)
    monkeypatch.setattr("polla_app.sources.browser.StealthyFetcher", FakeFetcher)

    first = browser.get_stealthy_fetcher()
    second = browser.get_stealthy_fetcher()

    assert first is second
    assert len(instances) == 1
```

**Verify**: `python -m pytest tests/test_browser.py -q` → pasa.

### Step 5: Regresión global

**Verify**: `python -m pytest -q` → todo pasa; `make ready` → todos los hooks pasan.

## Test plan

- Test del singleton: dos llamadas → misma instancia, una sola construcción
  (mockeando `StealthyFetcher`).
- Regresión: `test_pozo_polla.py`, `test_smoke_sources.py`, `test_prices.py`
  (ajustando el destino del monkeypatch de `scrapling.StealthyFetcher` a
  `polla_app.sources.browser.StealthyFetcher` si es necesario).

## Done criteria

- [ ] `python -m pytest -q` exit 0
- [ ] `grep -rn "StealthyFetcher(headless=True)" polla_app/` sin coincidencias (solo en `browser.py`)
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app` exit 0
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 009 actualizada

## STOP conditions

Detente y reporta si:

- Los tests existentes mockean `StealthyFetcher` de forma que el singleton
  rompe su semántica (p. ej. esperan una instancia nueva por llamada) — en ese
  caso actualiza el mock según el paso 2; si eso rompe otros tests, reporta.
- `get_stealthy_fetcher` con import lazy falla en el entorno (scrapling no
  instalado) — el ImportError debe propagarse como hoy en `get_pozo_polla`
  (el bloque `except ImportError` existente lo maneja; verifícalo).
- Alguna verificación falla dos veces tras intento razonable.

## Maintenance notes

- El estado global `_fetcher` es el segundo caché controlado del repo (tras el
  rate limiter de `net.py`); cualquier nuevo consumidor debe usar
  `get_stealthy_fetcher()` y nunca construir `StealthyFetcher` directo.
- Si un día se necesita cerrar el navegador al final de la corrida, añadir una
  función `close_stealthy_fetcher()` aquí y llamarla en el `finally` de
  `run_pipeline`.
- Revisar en el PR: que el mock de los tests de smoke apunte al módulo real
  (evitar "testing the mock").
