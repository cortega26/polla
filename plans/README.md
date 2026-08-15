# Implementation Plans

Generados por la skill improve el 2026-08-14 (auditoría `deep` del repo
`polla-app`, commit base `cb5d5ea`). Ejecutar en el orden indicado salvo que
las dependencias digan lo contrario. Cada executor: lee el plan completo antes
de empezar, respeta sus STOP conditions y actualiza su fila al terminar.

## Execution order & status

| Plan | Título | Prioridad | Esfuerzo | Depende de | Estado |
|------|--------|-----------|----------|------------|--------|
| 001 | Rechazar runs mixtos `pozos,kino` (sorteo/fecha por juego) | P1 | S | — | DONE |
| 002 | Retorno esperado solo con precio vivo (sin fallback a la hoja) | P1 | S | — | DONE |
| 003 | Formato de miles es-CL (punto) en el dashboard | P1 | S | — | DONE |
| 004 | pages.yml: conservar última data buena si la ingesta falla | P1 | M | — | DONE |
| 005 | Reintentar HTTP 502/503/504 en `fetch_html` | P2 | S | — | DONE |
| 006 | Publicación a Sheets en una sola escritura (sin hoja vacía) | P2 | M | — | DONE |
| 007 | Validar sorteo del hub de precios Kino vs pendón | P2 | S | 001 | DONE |
| 008 | verify-secret.yml: no imprimir fragmentos del secreto | P2 | S | — | DONE |
| 009 | Singleton de StealthyFetcher (un navegador por corrida) | P3 | M | 007 | DONE |
| 010 | Eliminar código muerto (ErrorMetric, validate_fecha_is_past, precio_estatico) | P3 | S | 002 | DONE |
| 011 | `scrapling[all]` → `scrapling[fetchers]` (extras innecesarios) | P3 | M | 009 | DONE (bloqueado 1x: base sin curl_cffi; plan refrescado) |
| 012 | Redactar query params sensibles en URLs logueadas | P3 | S | — | DONE |
| 013 | Docs: `api_version` actual (v1.2) en VERSIONING.md | P3 | S | 001 | DONE |

Estado: TODO | IN PROGRESS | DONE | BLOCKED (razón en una línea) | REJECTED (razón).

## Dependency notes

- **007 requiere 001**: ambos editan `polla_app/pipeline.py`; ejecutar 001
  primero evita conflictos de edición para un executor secuencial.
- **009 requiere 007**: ambos tocan `polla_app/sources/prices.py`.
- **010 requiere 002**: ambos tocan `polla_app/stats.py` (002 cambia
  `merge_real_prizes`, 010 elimina el campo `precio_estatico` de
  `merge_real_prices`).
- **011 recomienda 009**: tras el singleton, el único consumidor de scrapling
  es `browser.py`, lo que simplifica verificar el import surface del paquete
  base. (Ejecutable antes si se quiere.)
- **013 recomienda 001**: ambos tocan textos de fuentes en README/API.md.
- 003, 004, 005, 006, 008, 012 son independientes y pueden ejecutarse en
  cualquier orden.

## Findings considered and rejected

- **XSS en el dashboard**: toda la data se renderiza con `textContent`; sin
  HTML dinámico. Rechazado (no hay vector).
- **SSRF vía `source_overrides`/`ALT_SOURCE_URLS`**: config del operador,
  convención by-design (el fetch solo hace GET de texto). Rechazado.
- **Exclusión de "Total estimado" del consenso**: comportamiento intencional
  documentado en `_merge_pozos`. Rechazado.
- **Notificaciones Slack síncronas**: timeout 10s + no-fatal; riesgo bajo y
  no medido. Rechazado (si se vuelve problema, medir primero).
- **Rate limiter con atributo de función**: precedente aceptado del repo
  (caché controlada). Rechazado.
- **Dry-run de publish hace llamadas reales a Google**: documentado en el CLI
  help; útil para el diff. Rechazado.
- **`_load_previous_state` O(n) por corrida**: acotado a
  `MAX_STATE_RECORDS=1000`; irrelevante. Rechazado.
- **F2 (robots.txt bypass en fallback de navegador de precios)**: el usuario
  pidió explícitamente excluir este hallazgo del plan. Registrado para no
  re-auditarlo sin motivo.

## Notas de la auditoría

- Repo pequeño (~3.5K líneas de fuente + ~1.9K de tests + site): la auditoría
  `deep` se hizo directamente (sin subagentes); cada hallazgo fue verificado
  re-leyendo el código citado.
- No auditado a fondo: bodies de los archivos de test (solo estructura y
  greps dirigidos), `notifiers.py`/`obs.py`/`exceptions.py` en profundidad
  (pequeños), JS/CSS del sitio (sin linter JS configurado), y el histórico de
  git previo a la sesión de trabajo actual.
- Comandos de verificación estándar del repo: `ruff check polla_app tests`,
  `black --check polla_app tests`, `mypy polla_app`, `python -m pytest -q`,
  `make ready` (pre-commit: ruff, ruff-format, black, mypy, pytest).
  CI: tests.yml (black/ruff/mypy/pytest + coverage ≥80% vía codecov),
  docs.yml (doctests), health.yml (daily offline), scrape.yml (ingesta diaria),
  update.yml (dry-run diario), pages.yml (dashboard a GitHub Pages).
- Dirección pendiente (no planificada): resultados de Loto + estadísticas de
  frecuencia (D1), pipeline fuera de GitHub Actions para destrabar precios
  Loto en CI (D2), histórico SQLite tras resultados (D3) — ver informe de la
  auditoría.
