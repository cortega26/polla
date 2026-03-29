# Implementation Plan — Post-Audit Hardening Wave 2

**Versión del plan:** 1.0
**Fecha:** 2026-03-28
**Basado en:** Auditoría técnica completa del repositorio v3.1.0 (commit `cd6a80e`)
**Estado del ciclo anterior:** Todos los ítems de Wave 1 (MON-01 … DOC-01) completados.

---

## 1. Executive Summary

La Wave 1 (Phases 1-3 del plan anterior) cerró los riesgos más críticos: parser monetario determinista, SHA-256 provenance, jittered backoff, consensus quarantine, redacción contextual. El resultado es un pipeline que funciona correctamente en el happy path.

La auditoría post-hardening identificó una nueva categoría de problemas: **el CLI expone parámetros que no tienen efecto funcional real** (`--retries`, `--timeout`, `--no-include-pozos`). Esto no rompe el sistema en condiciones normales, pero crea un contrato de interfaz falso que puede inducir errores operacionales graves cuando alguien intente controlar el comportamiento de red desde el CLI.

La Wave 2 tiene tres objetivos en orden de prioridad:

1. **Restaurar la honestidad del contrato CLI → red** (bugs funcionales reales).
2. **Cubrir los caminos de fallo críticos con tests** (el degraded mode no está testeado).
3. **Eliminar deuda de configuración y CI** (spreadsheet ID expuesto, dry-run mirando hoja equivocada).

Features nuevas solo entran después de que los tres objetivos anteriores estén cumplidos.

---

## 2. Working Assumptions

- Se trabaja sobre Python 3.10+, sin cambios de dependencias salvo justificación explícita.
- Los cambios de firma de funciones públicas (`get_pozo_openloto`, `get_pozo_resultadosloto`) se hacen con parámetros keyword-only para mantener backwards compatibility.
- AGENTS.md es ley: CLI flags existentes no se eliminan sin deprecation notice de al menos 1 MINOR version.
- No se hacen rewrites de módulos completos. Cada cambio es quirúrgico.
- Los tests deben correr sin red (fixtures y monkeypatching). Sin excepciones.
- Un ítem no está "done" hasta que CI pase: `ruff check`, `black --check`, `mypy`, `pytest`, `pytest --doctest-glob`.

---

## 3. Findings Consolidation

### 3.1 Bugs Funcionales (CLI miente sobre su comportamiento)

| ID | Raíz del problema | Síntoma |
|----|-------------------|---------|
| BUG-01 | `--retries` y `--timeout` no llegan al network layer | Operador cree controlar red, no lo hace |
| BUG-02 | `include_pozos=False` no se pasa a `_run_ingestion_for_sources` | `--no-include-pozos` no tiene efecto |
| BUG-03 | `--sources all` llama los 3 loaders → fetches duplicados | Double-voting en consensus |
| BUG-04 | Comando `pozos` sin manejo de errores | ParseError/NetworkError produce traceback crudo |

BUG-01 y BUG-03 están relacionados pero son causas raíz distintas:
- BUG-01: los parámetros sí llegan a `_run_ingestion_for_sources` pero no se pasan al network layer.
- BUG-03: el registro SOURCE_LOADERS tiene entradas que solapan (cada loader de single-source usa `_collect_pozos` que a su vez puede llamar ambas fuentes).

BUG-02 es un dead parameter residual de cuando el pipeline tenía más tipos de datos. La corrección recomendada es deprecación + documentación, no reconexión (porque `include_pozos=False` rompería el pipeline con RuntimeError de todos modos).

### 3.2 Riesgo de Seguridad / Configuración

| ID | Problema | Severidad |
|----|----------|-----------|
| SEC-01 | Spreadsheet ID de producción hardcodeado en workflow público | Medium |
| CI-01 | update.yml hace dry-run contra worksheet "Normalized" pero producción publica en "Proximo Pozo" | Medium |
| CI-02 | scrape.yml hace `black --fix` + `ruff --fix` antes de testear (CI auto-modifica código) | Medium |

SEC-01 y CI-01 son independientes y de esfuerzo S cada uno. Van primero porque no tienen dependencias.

### 3.3 Gaps de Testing Críticos

| ID | Gap | Riesgo real |
|----|-----|-------------|
| TEST-01 | `_collect_pozos` exception handler marcado `# pragma: no cover` | Degraded mode no testeado |
| TEST-02 | Test monetario `test_parse_millones_to_clp_absolute_large` es `pass` | Range extremos sin verificar |
| TEST-03 | No hay test para fallo de una fuente + continuación con la otra | Comportamiento desconocido en producción |
| TEST-04 | No hay test para single-source complete pipeline (resultadoslotochile-only o openloto-only) | — |
| TEST-05 | publish.py: no hay test para filas vacías, múltiples registros, o fallo parcial de gspread | — |

TEST-01 y TEST-03 están vinculados: TEST-03 es el test que cubre el path que TEST-01 excluye con pragma.

### 3.4 Deuda Técnica

| ID | Problema | Impacto |
|----|----------|---------|
| DEBT-01 | `force_publish` semántica diferente en `run` vs `publish` (undocumented) | Confusión operacional |
| DEBT-02 | `_should_redact_key`: substring match para `"key"` produce falsos positivos | Redacción incorrecta de campos como `"monkey"` |
| DEBT-03 | `_init_log_stream` usa duck-typing via attribute injection, bypassa type system | No verificable por mypy |
| DEBT-04 | `_build_report_payload` construye siempre con `mismatched_categories: 0` y lo sobreescribe | Acoplamiento temporal |
| DEBT-05 | `missing_sources` en mismatches nunca se popula (siempre `[]`) | Campo de diagnóstico sin valor |
| DEBT-06 | Tie-breaking del consensus engine es implícito (first-fetcher wins) | No documentado |
| DEBT-07 | `requests.Session()` creada por llamada (sin connection pooling) | Performance minor |

### 3.5 CI / Documentación

| ID | Problema |
|----|----------|
| CI-03 | No hay umbral de cobertura en Codecov |
| CI-04 | `sync-main-to-master.yml` posiblemente vestigial |
| DOCS-01 | README no documenta `POLLA_BACKOFF_FACTOR` ni `POLLA_429_BACKOFF_SECONDS` |
| DOCS-02 | `pyproject.toml` tiene autor placeholder |
| DOCS-03 | Diagrama Mermaid del README llama "fallback" a OpenLoto (no es condicional) |

### 3.6 Features Nuevas

| ID | Feature | Prerequisito |
|----|---------|--------------|
| FEAT-01 | Degraded mode single-source con señalización explícita | TEST-01 resuelto primero |
| FEAT-02 | Notificaciones de quarantine enriquecidas con detalle de mismatch | Ninguno |
| FEAT-03 | Drift detection histórico | Cambio de arquitectura de state |
| FEAT-04 | Smoke fixture framework para nuevas fuentes | FEAT-01 resuelto primero |
| FEAT-05 | Soporte JSON API como tipo de fuente | Refactor mayor del registry |

---

## 4. Prioritization Strategy

Se usa la matriz **Riesgo Real × Esfuerzo × Dependencias**:

1. **P0 — Sin esto el CLI es engañoso o hay exposición de datos de producción**: BUG-01, SEC-01, CI-01, CI-02.
2. **P1 — Sin esto los paths de fallo críticos son ciegos o hay deuda que bloquea otras tareas**: TEST-01, TEST-02, TEST-03, BUG-04.
3. **P2 — Mejoras de calidad que protegen contra regresiones y clarifican contratos**: BUG-02, BUG-03, TEST-04, TEST-05, DEBT-01.
4. **P3 — Deuda técnica, CI y documentación que no bloquea operación**: DEBT-02 … DEBT-07, CI-03, CI-04, DOCS-01 … DOCS-03.
5. **P4 — Features nuevas, solo después de P0-P1 cerrados**: FEAT-01 … FEAT-05.

**Regla de secuenciación:** BUG-01 es el ítem más impactante pero requiere cambiar firmas de funciones que los tests ya ejercen. Se hace DESPUÉS de que CI-01/SEC-01 (sin dependencias) estén cerrados, pero ANTES de las features.

---

## 5. Phases

---

### Fase 0 — Saneamiento Inmediato (P0 sin dependencias)

**Objetivo:** Eliminar riesgos de configuración y CI que no requieren cambios de código de aplicación.
**Por qué va primero:** Esfuerzo S, riesgo de regresión cero, impacto inmediato.
**No depende de nada.** Puede ejecutarse en paralelo entre sí.

**Tareas:**
- `SEC-01`: Remover spreadsheet ID hardcodeado de `scrape.yml`
- `CI-01`: Alinear worksheet name en `update.yml` con producción ("Proximo Pozo")
- `CI-02`: Convertir `scrape.yml` para usar solo `--check` (no auto-fix)
- `DOCS-02`: Corregir autor placeholder en `pyproject.toml`

**Riesgos de regresión:** Ninguno. CI-02 puede hacer fallar PRs que antes pasaban silenciosamente (el workflow auto-arreglaba el formato). Es el efecto deseado.

**Criterio de salida:**
- `scrape.yml` no contiene el spreadsheet ID.
- `update.yml` usa `--worksheet "Proximo Pozo"`.
- CI no modifica código en el pipeline de test.
- `pyproject.toml` tiene datos reales de autor.

---

### Fase 1 — Correctitud Funcional del CLI (P0-P1)

**Objetivo:** Hacer que `--retries`, `--timeout` y el manejo de errores del CLI reflejen comportamiento real.
**Por qué va segundo:** Es la deuda más grave del sistema. Hasta que esto no esté resuelto, cualquier documentación operacional que incluya esos flags es incorrecta.
**Depende de:** Fase 0 (CI limpio para merges seguros).

**Tareas:**
- `BUG-01`: Conectar `--timeout` y `--retries` al network layer
- `BUG-04`: Añadir error handling al comando `pozos`
- `TEST-02`: Completar `test_parse_millones_to_clp_absolute_large`

**BUG-01 — Detalle de implementación:**

La cadena de cambios requeridos:

```
run_pipeline(timeout, retries)
  → _run_ingestion_for_sources(timeout, retries)   # ya los recibe, no los pasa
    → loader(True, source_overrides)
      → _collect_pozos(include, source_overrides, *, timeout, retries)  # añadir params
        → fetcher(url=..., timeout=timeout)          # pasar timeout
          → get_pozo_resultadosloto(url, *, ua, timeout)  # ya soporta timeout
          → get_pozo_openloto(url, *, ua, timeout)         # ya soporta timeout
```

Para `retries`: `fetch_html` ya lee `POLLA_MAX_RETRIES` del entorno. La opción más limpia es añadir `retries` como parámetro a `fetch_html` con fallback al env var. El CLI seteará la env var dinámicamente antes de llamar o pasará el parámetro directamente.

Cambio de firma recomendado para `fetch_html`:
```python
def fetch_html(url: str, ua: str, timeout: int = 20, *, retries: int | None = None) -> FetchMetadata:
    max_retries = retries if retries is not None else int(os.getenv("POLLA_MAX_RETRIES", "3"))
```

Backward compatible: llamadas existentes sin `retries` siguen usando el env var.

El tipo de `SOURCE_LOADERS` debe cambiar para incluir `timeout` y `retries`:
```python
SOURCE_LOADERS: dict[str, Callable[[bool, Mapping[str, str], int, int], tuple[...]]]
```
O, más limpio, usar `**kwargs` y pasar como keyword args.

**Riesgos de regresión:** Cambios de firma en `_collect_pozos`, `get_pozo_*` y `fetch_html`. Todos los tests existentes deben seguir pasando (usan defaults o monkeypatch).

**Criterio de salida:**
- `pytest tests/ -v` pasa completo.
- Un test nuevo verifica que `run_pipeline(timeout=5)` pasa `timeout=5` a `fetch_html`.
- `mypy polla_app` sin errores nuevos.
- `polla run --timeout 5` realmente usa timeout de 5s (verificable con `curl --max-time` equivalente en test).

---

### Fase 2 — Robustez Operacional y Testing (P1)

**Objetivo:** Cubrir los caminos de fallo operacionalmente más probables con tests reales.
**Por qué va después de Fase 1:** Los tests de degraded mode dependen de que la firma de `_collect_pozos` sea estable (modificada en BUG-01).
**Depende de:** Fase 1 (BUG-01).

**Tareas:**
- `TEST-01`: Remover `# pragma: no cover` del exception handler de `_collect_pozos` + test real
- `TEST-03`: Test: una fuente falla, pipeline continúa con la otra + resultado marcado correctamente
- `TEST-04`: Test: pipeline completo con single source (`--sources resultadoslotochile`)
- `TEST-05`: Mejorar cobertura de `publish.py` (filas vacías, múltiples registros en normalized)

**TEST-01/TEST-03 — Detalle:**

El test debe:
1. Patchear `get_pozo_resultadosloto` para que lance `NetworkError`.
2. Patchear `get_pozo_openloto` para que retorne datos válidos.
3. Verificar que el pipeline completa (no lanza excepción).
4. Verificar que `collected` tiene exactamente 1 entrada.
5. Verificar que el log emite un warning con el nombre de la fuente fallida.
6. Verificar que el result tiene `publish=True` con los datos de la fuente que funcionó.

**Comportamiento actual no verificado:** Si ambas fuentes fallan, `collected = []` → `RuntimeError("No sources returned data")`. Este path también necesita un test que verifique que el error es limpio y trazable.

**Riesgos de regresión:** Bajo. Son tests nuevos, no cambios de código de producción (salvo remover el pragma).

**Criterio de salida:**
- `# pragma: no cover` eliminado de `_collect_pozos`.
- Coverage del módulo `pipeline.py` aumenta.
- `pytest -v tests/test_pipeline.py` incluye al menos:
  - `test_pipeline_continues_when_one_source_fails`
  - `test_pipeline_raises_when_all_sources_fail`
  - `test_single_source_resultadoslotochile_produces_valid_artifacts`
- `pytest -v tests/test_publish.py` incluye al menos:
  - `test_publish_with_empty_pozos_proximo`
  - `test_publish_reads_only_first_normalized_record`

---

### Fase 3 — Hardening de CI, Contratos y Documentación (P2-P3)

**Objetivo:** Limpiar deuda técnica, alinear CI con la realidad, y mejorar la documentación para que refleje el comportamiento correcto post-Fase 1.
**Por qué va aquí:** No tiene dependencias de Fase 2, pero conviene hacerlo después para no documentar comportamiento que va a cambiar en Fase 1.
**Depende de:** Fase 1 (documentación debe reflejar params reales).

**Tareas:**
- `BUG-02`: Deprecar `--no-include-pozos` (añadir deprecation warning en CLI, no eliminar)
- `BUG-03`: Documentar limitación de `--sources all` o corregir el registry
- `DEBT-01`: Aclarar semántica de `force_publish` en help text de ambos comandos
- `DEBT-02`: Fix `_should_redact_key` substring match para `"key"`
- `DEBT-03`: Refactorizar `_init_log_stream` para retornar typed Protocol/dataclass
- `DEBT-04`: Pasar `mismatches` directamente a `_build_report_payload`
- `DEBT-05`: Poplar `missing_sources` en el consensus mismatch report
- `DEBT-06`: Documentar tie-breaking del consensus engine en docstring de `_merge_pozos`
- `CI-03`: Añadir umbral de cobertura en Codecov (≥80%)
- `CI-04`: Evaluar `sync-main-to-master.yml` — eliminar si no hay dependencias externas de `master`
- `DOCS-01`: Documentar `POLLA_BACKOFF_FACTOR` y `POLLA_429_BACKOFF_SECONDS` en README
- `DOCS-03`: Corregir descripción del diagrama Mermaid en README

**BUG-03 — Análisis de opciones:**

Opción A (recomendada): Documentar que `--sources all` es equivalente a `--sources pozos` y no fetch multiple sources simultaneously. Eliminar `"resultadoslotochile"` y `"openloto"` como entradas de SOURCE_LOADERS y usar `source_overrides` para single-source. Esto es un breaking change de interfaz menor: quienes usen `--sources openloto` deberían usar `--source-url resultadoslotochile=skip` en su lugar.

Opción B: Mantener SOURCE_LOADERS como está pero detectar en `_normalize_sources` que "all" solapa con "pozos" y retornar solo ["pozos"].

La opción B tiene menos riesgo de regresión. La opción A es arquitectónicamente más limpia. Se recomienda la opción B primero (como fix de correctitud) con la opción A como refactor posterior en Fase 4.

**DEBT-03 — Detalle de refactor de `_init_log_stream`:**

```python
@dataclass
class LogStream:
    _emit: Callable[[dict[str, Any]], None]
    close: Callable[[], None]
    set_correlation_id: Callable[[str], None]

    def __call__(self, payload: dict[str, Any]) -> None:
        self._emit(payload)
```

O usar un Protocol. Elimina los `# type: ignore[attr-defined]` en `pipeline.py`.

**Criterio de salida:**
- `mypy polla_app` sin `# type: ignore` en `pipeline.py` para los métodos de log stream.
- `_should_redact_key("monkey_bar")` retorna `False`.
- README documenta todas las env vars que `net.py` consume.
- `_merge_pozos` tiene docstring explicando tie-breaking.
- `missing_sources` está poblado correctamente o el campo se documenta como "reserved".

---

### Fase 4 — Features de Alto Valor (P4)

**Objetivo:** Añadir features que aumentan el valor operacional real del sistema.
**Por qué va al final:** Las features construyen sobre el sistema estabilizado. FEAT-01 (degraded mode) depende de que TEST-01/TEST-03 establezcan el comportamiento correcto de fallo primero.
**Depende de:** Fases 1, 2 y 3 cerradas.

**Tareas (en orden de prioridad):**
- `FEAT-02`: Notificaciones de quarantine enriquecidas (detalle de mismatch en Slack)
- `FEAT-01`: Degraded mode single-source con campo `confidence` en output
- `FEAT-03`: Drift detection histórico (últimos N runs en state)
- `FEAT-04`: Smoke fixture framework para nuevas fuentes
- `FEAT-05`: Soporte JSON API como tipo de fuente

FEAT-02 va primero porque es de esfuerzo S y solo requiere cambios en `notifiers.py` y `pipeline.py`. El valor operacional es alto (quarantine es el evento más accionable del sistema).

FEAT-01 requiere extender el schema de `normalized.jsonl` con un campo `confidence` → implica bump de `API_VERSION`. Hacer DESPUÉS de que el schema esté estable.

FEAT-03 requiere cambios en el state file (mantener múltiples records, no solo el último). Es arquitectónicamente más invasivo.

FEAT-05 es el más complejo y queda para cuando el registry esté limpio (post BUG-03).

---

## 6. Execution Order (Recommended)

### Inmediatamente (pueden ir en paralelo en un PR):
1. `SEC-01` — Remover spreadsheet ID de workflow
2. `CI-01` — Alinear worksheet en update.yml
3. `CI-02` — Quitar auto-fix de CI
4. `DOCS-02` — Fix pyproject.toml author
5. `TEST-02` — Completar test placeholder monetario

### Segunda ronda (un PR por ítem o agrupados por área):
6. `BUG-01` — Conectar timeout/retries al network layer ← **el más importante**
7. `BUG-04` — Error handling en comando `pozos`

### Tercera ronda (tests de robustez):
8. `TEST-01` + `TEST-03` — Degraded mode testing (van juntos, mismo archivo)
9. `TEST-04` — Single-source complete pipeline
10. `TEST-05` — Publish coverage

### Cuarta ronda (deuda y CI):
11. `BUG-02` — Deprecation warning para --no-include-pozos
12. `BUG-03` — Fix _normalize_sources para "all"
13. `DEBT-01` — Documentar force_publish semántica
14. `DEBT-02` — Fix _should_redact_key
15. `DEBT-03` — Refactor _init_log_stream
16. `DEBT-04` + `DEBT-05` + `DEBT-06` — Consensus engine cleanup (un PR)
17. `CI-03` — Codecov threshold
18. `CI-04` — Evaluar sync-main-to-master
19. `DOCS-01` + `DOCS-03` — README updates

### Quinta ronda (features):
20. `FEAT-02` — Quarantine notifications
21. `FEAT-01` — Degraded mode
22. `FEAT-03` — Drift detection
23. `FEAT-04` — Smoke fixture framework
24. `FEAT-05` — JSON API sources

---

## 7. What NOT to Do Yet

- **No eliminar `--no-include-pozos`**: Requiere MAJOR version bump o deprecation de 1 MINOR cycle. Solo añadir warning por ahora.
- **No reescribir `pipeline.py`**: Los cambios son quirúrgicos. La arquitectura es correcta.
- **No añadir Pydantic para schema enforcement**: Deuda extra de dependencia sin beneficio claro sobre el JSON schema actual. Evaluar solo si FEAT-01 introduce complejidad de validación real.
- **No cambiar el formato de `normalized.jsonl` hasta que FEAT-01 esté especificado**: Un cambio de schema requiere bump de `API_VERSION` y migración.
- **No tocar `sync-main-to-master.yml` hasta verificar que nadie depende de la rama `master`**.
- **No hacer FEAT-03 (drift detection) antes de FEAT-01**: FEAT-01 define cómo el schema evoluciona; FEAT-03 depende del schema estable.

---

## 8. Regression Strategy

Cada PR debe pasar:
```bash
ruff check polla_app tests
black --check polla_app tests
mypy polla_app
pytest -q
pytest --doctest-glob='*.md' README.md docs -q
```

Para BUG-01 (cambio de firmas): antes de la PR, correr los tests existentes y verificar que todos pasan sin modificar ningún test (solo añadiendo). Si algún test falla, es una regresión real, no un test que hay que actualizar.

Para DEBT-03 (refactor _init_log_stream): el comportamiento observable del pipeline (artifacts generados, log events emitidos) debe ser idéntico antes y después. Verificar con el test existente `test_pozos_pipeline_produces_artifacts`.

---

## 9. Definition of Done por Fase

| Fase | DoD |
|------|-----|
| 0 | CI verde. Workflow sin spreadsheet ID hardcodeado. update.yml usa worksheet correcto. |
| 1 | `polla run --timeout 5` pasa timeout=5 a fetch_html. Test lo verifica. mypy sin errores nuevos. |
| 2 | `# pragma: no cover` eliminado de _collect_pozos. Tests cubren degraded mode. Coverage ≥ previo. |
| 3 | mypy sin `# type: ignore` en pipeline.py para log stream. README documenta todos los env vars. |
| 4 | Cada feature tiene tests, está documentada en README/CHANGELOG, y API_VERSION bumpeada si el schema cambia. |
