# Implementation Plans

**Hard rule**: plan files whose status becomes DONE are moved to
`plans/archive/` automatically (by the executor or reviewer when they flip
the status). The index below always reflects the full backlog; archived
files are still the record and must not be deleted.

Tercera ronda: skill improve el 2026-08-15 (auditoría `deep`, commit base
`8a5da7f`). Rondas previas: 001-013 (2026-08-14, base `cb5d5ea`) y 014-018
(2026-08-15, base post-`9180c98`), todos DONE. Ejecutar en el orden
indicado salvo que las dependencias digan lo contrario. Cada executor: lee
el plan completo antes de empezar, respeta sus STOP conditions y actualiza
su fila al terminar.

## Execution order & status

| Plan | Título | Prioridad | Esfuerzo | Depende de | Estado |
|------|--------|-----------|----------|------------|--------|
| 019 | Rotar credenciales quemadas y purgar el historial (SA de Google, .env, check_credentials.yml) | P1 | M | — | IN PROGRESS — cambios de repo aprobados (b1b6e37/b8de891/b9ae010 en `advisor/019-rotate-purge-credentials`); pendiente rotación GCP/Webshare (paso 4) y purge de historial (paso 5) por el operador |
| 020 | Rechazar toda combinación mixta Loto+Kino (`kino,openloto`) | P1 | S | — | DONE |
| 021 | Tests CLI herméticos para `run`, `publish`, `kino` | P1 | M | — | DONE |
| 022 | Excluir pruebas de red del suite por defecto (marcador `network`) | P1 | M | 021 | DONE |
| 023 | Conservar un raw por fuente en modo agregado (`pozos`) | P1 | S | — | DONE |
| 024 | Historias de sorteos reales en el dashboard desde `pipeline_state` | P1 | M | — | DONE |
| 025 | Alinear README/.env.example con el contrato real de variables de entorno | P2 | S | — | DONE |
| 026 | Cerrar 5 gaps de tests (rate limiter, SHA dedup, 429/502/504, monotonicidad, skip Slack) | P2 | S | — | DONE |
| 027 | Consolidar lectores/escritores JSONL en `polla_app/io.py` | P2 | S | — | DONE |
| 028 | Eliminar código muerto (helpers, params, `include_pozos` sin tocar CLI) | P2 | S | — | DONE |
| 029 | Sesión HTTP compartida + redactar userinfo de URLs en logs | P2 | S | — | DONE |
| 030 | Estado por juego: archivo y dedupe con campo `game` | P2 | S | — | DONE |
| 031 | tests.yml con `contents: read` + AGENTS.md realista | P2 | S | — | DONE |
| 032 | Lockfile + cota superior de scrapling; CI instala desde el lock | P2 | M | — | DONE |
| 033 | Pin unificado de playwright + chequeo de paridad chromium + caché | P2 | S | 032 | DONE |
| 034 | `make ready` sin `git add .` previo; pre-commit en requirements-dev | P3 | S | — | TODO |
| 035 | Alinear invocaciones de mypy y `ruff format --check` en todos los gates | P3 | S | — | TODO |
| 036 | pages.yml reutiliza artefactos de scrape.yml en vez de re-ingestar | P3 | M | — | TODO |
| 037 | Reconciliar docs: API.md, CHANGELOG, docs/implementation, observability.md | P3 | M | — | TODO |
| 038 | Eliminar trabajo desperdiciado: soup de Kino y doble build del payload | P3 | S | — | TODO |
| 039 | Registro único de categorías Kino (drift de "Kino Gran Sueldo") | P3 | M | — | TODO |
| 040 | Consolidar los 4 parsers/formatters es-CL en `polla_app/numbers.py` | P3 | M | — | TODO |
| 041 | `_get_or_create_worksheet`: solo capturar WorksheetNotFound | P3 | S | — | TODO |
| 042 | Tolerar puntuación final en montos de openloto (`$1.000.000.-`) | P3 | S | — | TODO |
| 043 | Precios Kino tolerantes a variantes ausentes (como el pendón) | P3 | S | — | TODO |
| 044 | Dedupe de sources: NEXT_DATA, DEFAULT_UA y envelope del payload | P2 | M | — | TODO |
| 045 | Backoff exponencial en el reintento de polla.cl | P2 | S | — | TODO |
| 046 | Re-exports muertos, enforce del SLO de parseo en CI, conftest.py | P2 | S | — | TODO |
| 047 | Validadores de números: reservar y fijar contrato (feature resultados) | P3 | S | — | TODO |

Estado: TODO | IN PROGRESS | DONE | BLOCKED (razón en una línea) | REJECTED (razón).

## Dependency notes

- **022 requiere 021**: excluir las e2e live baja la cobertura de los paths
  de CLI; 021 los reemplaza herméticamente y mantiene verde el gate del 80%.
- **033 recomienda 032**: ambos tocan manifests/workflows; 033 unifica el
  pin de playwright que 032 ya fija en el lock.
- **024 antes de 027** (recomendado): ambos tocan `site.py`; 027 migra los
  readers que 024 puede usar (`read_jsonl` con `tolerant`).
- **030 después de 024** (recomendado): 024 lee el state file para el
  historial; 030 lo separa por juego (Loto y Kino) y 024 debe adaptar la
  lectura a `last_run_kino.jsonl`.
- **030 antes de 036** (recomendado): ambos tocan pages.yml.
- **042 después de 040** (recomendado): ambos tocan `_parse_millones_to_clp`;
  042 aplica el fix dentro de `polla_app/numbers.py` si 040 ya aterrizó.
- **044 después de 039/040/042/043** (recomendado): todos tocan
  kino.py/prices.py/pozos.py; ejecutar en secuencia para un executor único.
- **045 después de 044** (recomendado): ambos tocan `get_pozo_polla`.
- **046 independiente**: el conftest.py se coordina con 021 (misma carpeta
  tests/) — añadir a la misma conftest sin duplicar `write_ndjson`.

## Findings considered and rejected (ronda 3)

- **PERF-03 (12 escaneos regex en pozos.py)**: el benchmark mide ~0.05 ms
  por parse; el SLO de 150 ms tiene margen enorme. No vale la pena.
- **DEBT-06 (split de pipeline.py/__main__.py)**: esfuerzo L, riesgo MED
  en el archivo más caliente; repo pequeño y sano. Diferido.
- **DEBT-07 (introspection `inspect.signature`)**: funciona hoy; confianza
  MED; valor bajo.
- **DEBT-05 (4 patrones de error inconsistentes)**: outputs visibles al
  usuario; requiere decisión de contrato. Diferido.
- **DEPS-05 (lxml en vez de html.parser)**: riesgo MED para ganancia
  marginal; el benchmark muestra margen enorme.
- **PERF-06 (logs/run.jsonl sin rotación)**: años para importar (KB/run).
- **SEC-05 completo (redacción de userinfo)**: absorbido por el plan 029.
- **Rate limiter sin aplicar al fallback de browser**: cortesía, impacto
  bajo; notado en el índice de 029.
- **Dirección D2 (LOTO resultados) y D3 (dry-run nocturno observable)**:
  opciones del mantenedor, no planes (ver "Dirección" abajo).
- **DUP-E parcial (helpers de test en test_hardening_net.py)**: el plan 046
  mueve `_fail_once` solo si porta limpio; si no, queda local (valor
  marginal).
- **get_pozo_polla sin reusar fetch_html**: mecanismo distinto
  (StealthyFetcher con page action); no es duplicación. Ver plan 045.

## Dirección (opciones del mantenedor, no planes)

- **D1 — Historial real + detección de drift**: cubierto por el plan 024
  (el `pipeline_state` ya guarda 1000 registros deduplicados por sorteo;
  024 los expone en el dashboard y habilita alertas de drift cross-run).
- **D2 — LOTO resultados (números ganadores)**: GAMES.md:30-34 lo rankea
  como la mejor expansión valor/esfuerzo; todos los ingredientes existen
  sin uso (`validate_kino_numbers`, extractor `__NEXT_DATA__`, path de
  `premios` de publish siempre `[]`). Spike de esfuerzo L; habilita las
  estadísticas de frecuencia que DATA-STORE.md señala como gatillo de
  SQLite. No planificado (decisión del mantenedor).
- **D3 — Hacer observable el dry-run nocturno y el health online**:
  update.yml corre el pipeline + `publish --dry-run` a las 02:00 pero su
  diff muere en artefactos; SLOs.md define políticas de fallas online que
  ningún workflow ejecuta; health.yml corre solo offline. Esfuerzo S,
  riesgo LOW (solo añade un paso de alerta y un cron con `health --online`).

## Notas de la auditoría (ronda 3)

- **Fusión 2026-08-17**: ramas advisor/019..031 fusionadas a `main`
  (ahora `a05e05a`, pushed a origin). Se resolvieron 3 conflictos
  cross-branch (site.py: 024×027; test_hardening_net.py: 026×029;
  test_pipeline.py: 023×026×030) + ajustes de firma post-028/030 en tests.
  Verificación integrada: 197 passed, 1 skip, 4 deselected (hermético).
- Veredicto "todo lo netamente positivo": 25 hallazgos → 25 planes
  (019-043), todos con evidencia verificada en el código (`8a5da7f`).
- 019 (ejecutado y aprobado): el plan original no cubría el patrón de
  nombre real del archivo quemado (`polla-chilena*.json`); el executor
  añadió ese patrón a `.gitignore` (desviación documentada, aprobada).
- No auditado: comportamiento de red en vivo, costos de API de gspread,
  contenido completo de docs/implementation (re-etiquetado en 037).
- El árbol de trabajo al momento de la planificación contenía solo los
  movimientos de archivo de la ronda 2 (plans/ → plans/archive/), sin
  cambios de código pendientes.
- Hallazgos con credenciales: solo referencias a archivo/commit; ningún
  valor secreto reproducido en los planes (ver plan 019, regla de
  rotación).
