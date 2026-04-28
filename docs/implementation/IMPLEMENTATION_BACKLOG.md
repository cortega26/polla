# Implementation Backlog — Wave 2 Post-Audit

**Repositorio:** `polla` v3.1.0
**Última actualización:** 2026-03-28
**Plan de referencia:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
**Wave anterior (completada):** MON-01, PROV-01, PIPE-01, NET-01, REG-01, OBS-01, F-001, F-002, DOC-01

---

## Vista rápida por fase

| Fase | Ítems | Esfuerzo total | Prioridad máxima |
|------|-------|---------------|------------------|
| 0 — Saneamiento inmediato | 4 | 4×S | P0 |
| 1 — Correctitud funcional CLI | 3 | 2×M + 1×S | P0-P1 |
| 2 — Robustez y testing | 5 | 5×S-M | P1 |
| 3 — Deuda, CI y docs | 13 | 12×S + 1×M | P2-P3 |
| 4 — Features nuevas | 5 | 2×S + 2×M + 1×L | P4 |

---

## Backlog Completo

### FASE 0 — Saneamiento Inmediato

---

#### SEC-01 — Remover spreadsheet ID hardcodeado de scrape.yml

| Campo | Valor |
|-------|-------|
| **ID** | SEC-01 |
| **Tipo** | `hardening` |
| **Fuente** | F-08 (auditoría) |
| **Prioridad** | P0 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 0 |
| **Archivos** | `.github/workflows/scrape.yml` |

**Problema:** El ID de producción del spreadsheet Google (`16WK4Qg59…`) está hardcodeado en línea 244 del workflow público como fallback. Viola 12-Factor y expone configuración de producción en código público.

**Pasos de implementación:**
1. En `.github/workflows/scrape.yml`, reemplazar el bloque:
   ```bash
   if [ -z "${GOOGLE_SPREADSHEET_ID}" ]; then
       export GOOGLE_SPREADSHEET_ID="16WK4Qg59G38mK1twGzN8tq2o3Y3DnYg11Lh2LyJ6tsc";
   fi
   ```
   por:
   ```bash
   if [ -z "${GOOGLE_SPREADSHEET_ID}" ]; then
       echo "::warning::GOOGLE_SPREADSHEET_ID secret not configured; skipping publish."
       exit 0
   fi
   ```
2. Verificar que el Secret `GOOGLE_SPREADSHEET_ID` está configurado en el repositorio GitHub antes de mergear.

**Criterio de aceptación:** El archivo `scrape.yml` no contiene ningún ID de spreadsheet. El workflow falla gracefully si el secret falta (exit 0 con warning, no error de CI).

**Validación:** `grep -n "16WK4" .github/workflows/scrape.yml` retorna vacío.

**Rollback:** Revertir el commit. Sin impacto en producción si el Secret está correctamente configurado.

---

#### CI-01 — Alinear worksheet de dry-run con producción

| Campo | Valor |
|-------|-------|
| **ID** | CI-01 |
| **Tipo** | `ci` |
| **Fuente** | F-14 (auditoría) |
| **Prioridad** | P0 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 0 |
| **Archivos** | `.github/workflows/update.yml` |

**Problema:** `update.yml` (dry-run diario) usa `--worksheet "Normalized"` pero `scrape.yml` (producción) publica en `--worksheet "Proximo Pozo"`. El dry-run compara un diff contra la hoja equivocada.

**Pasos de implementación:**
1. En `.github/workflows/update.yml`, línea 68, cambiar:
   `--worksheet "Normalized"` → `--worksheet "Proximo Pozo"`

**Criterio de aceptación:** `update.yml` y `scrape.yml` usan el mismo worksheet name en sus respectivos comandos `publish`.

**Validación:** `grep "worksheet" .github/workflows/update.yml .github/workflows/scrape.yml` muestra el mismo valor.

---

#### CI-02 — Eliminar auto-fix de código en CI

| Campo | Valor |
|-------|-------|
| **ID** | CI-02 |
| **Tipo** | `ci` |
| **Fuente** | F-25 (auditoría) |
| **Prioridad** | P0 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo (puede hacer fallar PRs que antes pasaban silenciosamente — efecto deseado) |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 0 |
| **Archivos** | `.github/workflows/scrape.yml` |

**Problema:** `scrape.yml` corre `black polla_app tests` (sin `--check`) y `ruff check --fix` antes de testear, lo que modifica el código en CI. El código que se testea no es el código del commit. Encubre problemas de formateo del desarrollador.

**Pasos de implementación:**
1. En `.github/workflows/scrape.yml`, reemplazar el step "Run formatting & linting (auto-fix)" por:
   ```yaml
   - name: Check formatting & linting
     run: |
       black --check polla_app tests
       ruff check polla_app tests
   ```
2. Eliminar el segundo `black --check` que era la verificación post-fix.

**Criterio de aceptación:** El step solo verifica, no modifica. Un commit con código mal formateado falla CI.

**Nota:** Este cambio hace el comportamiento de `scrape.yml` idéntico a `tests.yml`. Unificar ambos es trabajo de CI-04.

---

#### DOCS-02 — Corregir autor placeholder en pyproject.toml

| Campo | Valor |
|-------|-------|
| **ID** | DOCS-02 |
| **Tipo** | `docs` |
| **Fuente** | F-22 (auditoría) |
| **Prioridad** | P0 |
| **Esfuerzo** | S |
| **Riesgo** | Ninguno |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 0 |
| **Archivos** | `pyproject.toml` |

**Problema:** `pyproject.toml` tiene `authors = [{name = "Your Name", email = "your.email@example.com"}]`.

**Pasos de implementación:**
1. Reemplazar con datos reales del autor del repositorio.

**Criterio de aceptación:** `pyproject.toml` contiene datos reales de autor.

---

### FASE 1 — Correctitud Funcional del CLI

---

#### BUG-01 — Conectar --timeout y --retries al network layer

| Campo | Valor |
|-------|-------|
| **ID** | BUG-01 |
| **Tipo** | `bugfix` |
| **Fuente** | F-01 (auditoría) — Quick Win #1 |
| **Prioridad** | P0 |
| **Esfuerzo** | M |
| **Riesgo** | Medio (cambio de firmas en cadena — mitigado con tests) |
| **Estado** | `done` |
| **Dependencias** | CI-02 (CI limpio para mergear con confianza) |
| **Fase** | 1 |
| **Archivos** | `polla_app/net.py`, `polla_app/sources/pozos.py`, `polla_app/pipeline.py` |

**Problema:** `run_pipeline(timeout=30, retries=3)` acepta y loguea esos valores en el report, pero nunca los pasa al network layer. `fetch_html` usa `timeout=20` hardcodeado y `POLLA_MAX_RETRIES` env var (default 3) independientemente de lo que el CLI reciba.

**Pasos de implementación:**

1. **`polla_app/net.py` — `fetch_html`**: Añadir parámetro `retries: int | None = None`. Si es `None`, leer `POLLA_MAX_RETRIES` del env (comportamiento actual como fallback).
   ```python
   def fetch_html(url: str, ua: str, timeout: int = 20, *, retries: int | None = None) -> FetchMetadata:
       max_retries = retries if retries is not None else int(os.getenv("POLLA_MAX_RETRIES", "3"))
   ```

2. **`polla_app/sources/pozos.py` — `_fetch_pozos`**: Añadir `retries: int | None = None` y pasarlo a `fetch_html`.
   ```python
   def _fetch_pozos(*, url, ua, timeout, allow_total, retries: int | None = None):
       metadata = fetch_html(url, ua=..., timeout=timeout, retries=retries)
   ```

3. **`polla_app/sources/pozos.py` — `get_pozo_openloto` y `get_pozo_resultadosloto`**: Añadir `retries: int | None = None` (keyword-only) y pasarlo a `_fetch_pozos`. Backward compatible: callers existentes sin `retries` siguen funcionando.

4. **`polla_app/pipeline.py` — `_collect_pozos`**: Añadir `timeout: int = 20, retries: int = 3` a la firma. Pasar al fetcher:
   ```python
   payload = fetcher(url=target_url, timeout=timeout, retries=retries) if target_url else fetcher(timeout=timeout, retries=retries)
   ```

5. **`polla_app/pipeline.py` — `SOURCE_LOADERS`**: Los lambdas deben pasar `timeout` y `retries`. Actualizar el tipo de `SOURCE_LOADERS` para que la callable reciba también estos parámetros, o pasar via `**kwargs`.

6. **`polla_app/pipeline.py` — `_run_ingestion_for_sources`**: Pasar `timeout` y `retries` al llamar al loader:
   ```python
   collected.extend(loader(True, source_overrides or {}, timeout, retries))
   ```

   O alternativamente refactorizar los loaders para que acepten `**kwargs` y lo pasen a `_collect_pozos`.

7. **Tests**: Añadir test que verifique que el timeout pasado llega a `fetch_html`:
   ```python
   def test_timeout_reaches_fetch_html(tmp_path, monkeypatch):
       received_timeout = []
       def stub_fetch(url, ua, timeout=20, *, retries=None):
           received_timeout.append(timeout)
           return FetchMetadata(...)
       monkeypatch.setattr("polla_app.net.fetch_html", stub_fetch)
       run_pipeline(..., timeout=7, ...)
       assert received_timeout[0] == 7
   ```

**Criterio de aceptación:**
- `polla run --timeout 7` hace que `fetch_html` reciba `timeout=7`.
- `polla run --retries 1` hace que `fetch_html` reciba `retries=1`.
- Tests existentes en `test_pipeline.py`, `test_parsers.py` pasan sin modificación.
- `mypy polla_app` sin errores nuevos.

**Validación:** Test nuevo en `tests/test_pipeline.py` y/o `tests/test_parsers.py`.

**Rollback:** Si los tests fallan, el PR no se mergea. Sin rollback en producción necesario.

---

#### BUG-04 — Añadir error handling al comando `pozos`

| Campo | Valor |
|-------|-------|
| **ID** | BUG-04 |
| **Tipo** | `bugfix` |
| **Fuente** | F-12 (auditoría) |
| **Prioridad** | P1 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo |
| **Estado** | `done` |
| **Dependencias** | Ninguna (puede ir en paralelo con BUG-01) |
| **Fase** | 1 |
| **Archivos** | `polla_app/__main__.py` |

**Problema:** El comando `pozos` no tiene manejo de errores. Si cualquier fuente falla (ParseError, NetworkError, RobotsDisallowedError), el traceback crudo se imprime en lugar de un JSON de error estructurado.

**Pasos de implementación:**
1. Envolver cada fetcher en try/except:
   ```python
   @cli.command()
   def pozos() -> None:
       results: dict[str, Any] = {}
       for name, fn in (
           ("resultadoslotochile", get_pozo_resultadosloto),
           ("openloto", get_pozo_openloto),
       ):
           try:
               results[name] = fn()
           except Exception as exc:
               results[name] = {"error": type(exc).__name__, "message": str(exc)}
       _echo_json(results)
   ```
2. Añadir test que verifica que cuando `get_pozo_openloto` lanza `ParseError`, el output JSON incluye `{"openloto": {"error": "ParseError", ...}}` y no propaga la excepción.

**Criterio de aceptación:**
- `pozos` con una fuente fallida retorna JSON con el error de esa fuente y los datos de la otra.
- Exit code 0 cuando hay datos parciales, exit code 1 solo si ambas fuentes fallan (opcional, P3).
- Test cubre el path de error.

---

#### TEST-02 — Completar test monetario placeholder

| Campo | Valor |
|-------|-------|
| **ID** | TEST-02 |
| **Tipo** | `testing` |
| **Fuente** | F-16 (auditoría) — Quick Win #4 |
| **Prioridad** | P1 |
| **Esfuerzo** | S |
| **Riesgo** | Ninguno |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 1 |
| **Archivos** | `tests/test_monetary_parser.py` |

**Problema:** `test_parse_millones_to_clp_absolute_large` contiene solo `pass`. No verifica nada sobre rangos extremos del parser.

**Pasos de implementación:**
1. Reemplazar la función con casos parametrizados para rangos extremos y ambiguos:
   ```python
   @pytest.mark.parametrize("raw, expected", [
       ("99.999", 99_999_000_000),  # large thousands separator
       ("0,1", 100_000),            # sub-million
       ("1.234.567", 1_234_567_000_000),  # three dots
   ])
   def test_parse_millones_to_clp_large_ranges(raw, expected):
       assert _parse_millones_to_clp(raw) == expected
   ```
2. Verificar que el parser maneja correctamente (o falla explícitamente con ParseError) valores en el rango de miles de miles de millones.
3. Asegurarse de que los casos edge están documentados como comentarios.

**Criterio de aceptación:** El test no contiene `pass`. Tiene ≥3 casos parametrizados para rangos fuera del rango "normal" (< 10.000 MM). Todos los casos tienen una expectativa explícita.

---

### FASE 2 — Robustez Operacional y Testing

---

#### TEST-01 — Remover pragma no-cover y testear degraded mode

| Campo | Valor |
|-------|-------|
| **ID** | TEST-01 |
| **Tipo** | `testing` |
| **Fuente** | F-13, F-17 (auditoría) — Quick Win #2 |
| **Prioridad** | P1 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo (podría revelar bugs en el exception path) |
| **Estado** | `done` |

| **Dependencias** | BUG-01 (firma de _collect_pozos estable) |
| **Fase** | 2 |
| **Archivos** | `polla_app/pipeline.py`, `tests/test_pipeline.py` |

**Problema:** El exception handler de `_collect_pozos` (línea ~103) está marcado `# pragma: no cover`. El comportamiento del pipeline cuando una fuente falla es desconocido e intesteado.

**Pasos de implementación:**
1. Remover el comentario `# pragma: no cover` del except en `_collect_pozos`.
2. Añadir `test_pipeline_continues_when_one_source_fails`:
   ```python
   def test_pipeline_continues_when_one_source_fails(tmp_path, monkeypatch):
       from polla_app import pipeline as pm
       def raises(**_): raise RuntimeError("source down")
       valid = {"fuente": "...", "montos": {"Loto": 1_000_000}, "sorteo": 1, "fecha": "2025-01-01"}
       monkeypatch.setattr(pm.pozos_module, "get_pozo_resultadosloto", raises)
       monkeypatch.setattr(pm.pozos_module, "get_pozo_openloto", lambda **_: valid)
       summary = run_pipeline(sources=["pozos"], ...)
       assert summary["publish"] is True
       # Verify warning was logged
   ```
3. Añadir `test_pipeline_raises_when_all_sources_fail`:
   ```python
   def test_pipeline_raises_when_all_sources_fail(tmp_path, monkeypatch):
       from polla_app import pipeline as pm
       def raises(**_): raise RuntimeError("source down")
       monkeypatch.setattr(pm.pozos_module, "get_pozo_resultadosloto", raises)
       monkeypatch.setattr(pm.pozos_module, "get_pozo_openloto", raises)
       with pytest.raises(RuntimeError, match="No sources returned data"):
           run_pipeline(sources=["pozos"], ...)
   ```

**Criterio de aceptación:**
- `# pragma: no cover` no aparece en `_collect_pozos`.
- Ambos tests pasan.
- Coverage de `pipeline.py` aumenta respecto al baseline.

**Nota:** Si el test revela que el pipeline falla inesperadamente cuando una fuente falla, ese es el bug real (no el test). Documentar el comportamiento observado antes de parchear.

---

#### TEST-03 — Test pipeline single-source (resultadoslotochile-only)

| Campo | Valor |
|-------|-------|
| **ID** | TEST-03 |
| **Tipo** | `testing` |
| **Fuente** | F-18 (auditoría) |
| **Prioridad** | P1 |
| **Esfuerzo** | S |
| **Riesgo** | Ninguno |
| **Estado** | `done` |

| **Dependencias** | BUG-01 |
| **Fase** | 2 |
| **Archivos** | `tests/test_pipeline.py` |

**Problema:** El SOURCE_LOADERS tiene entrada para `"resultadoslotochile"` pero no hay test de pipeline completo para este modo.

**Pasos de implementación:**
1. Añadir test con `sources=["resultadoslotochile"]` que verifica:
   - Solo se llama a `get_pozo_resultadosloto` (no a openloto).
   - El pipeline produce artifacts válidos.
   - El normalized record tiene `source_mode="resultadoslotochile_only"` en el log event.
2. Verificar con monkeypatch que `get_pozo_openloto` NO es llamado.

**Criterio de aceptación:** Test pasa. Confirmed que openloto no es llamado en single-source mode.

---

#### TEST-04 — Mejorar cobertura de publish.py

| Campo | Valor |
|-------|-------|
| **ID** | TEST-04 |
| **Tipo** | `testing` |
| **Fuente** | F-19 (auditoría) |
| **Prioridad** | P2 |
| **Esfuerzo** | M |
| **Riesgo** | Ninguno |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 2 |
| **Archivos** | `tests/test_publish.py` |

**Problema:** `publish.py` no tiene tests para: pozos-only rows (vs premios rows), `_canonical_rows_header` con rows vacíos, múltiples records en normalized (solo se usa el primero).

**Pasos de implementación:**
1. Añadir `test_record_to_rows_pozos_only`: fixture con record sin `premios`, verifica que se generan filas de 2 columnas (categoria, monto).
2. Añadir `test_publish_uses_only_first_normalized_record`: normalized con 2 records, verificar que publish solo procesa el primero.
3. Añadir `test_publish_with_empty_pozos_proximo`: record con `pozos_proximo={}`, verificar comportamiento (0 filas o header vacío sin crash).

**Criterio de aceptación:** ≥3 tests nuevos. `_record_to_rows` con pozos-only está cubierto.

---

#### TEST-05 — Test: ambas fuentes fallan y error es claro

| Campo | Valor |
|-------|-------|
| **ID** | TEST-05 |
| **Tipo** | `testing` |
| **Fuente** | F-17 (auditoría) |
| **Prioridad** | P1 |
| **Esfuerzo** | S |
| **Riesgo** | Ninguno |
| **Estado** | `done` |

| **Dependencias** | TEST-01 |
| **Fase** | 2 |
| **Archivos** | `tests/test_pipeline.py` |

**Nota:** Este ítem puede ir en el mismo PR que TEST-01 (ambos cubren fallo de fuentes).

**Problema:** El path "todas las fuentes fallan" produce `RuntimeError("No sources returned data")` pero no hay test que verifique que el mensaje de error es útil y que no se generan artifacts parciales.

**Pasos de implementación:**
1. Test que verifica que el RuntimeError tiene información del contexto.
2. Test que verifica que cuando el pipeline falla, el log stream cierra correctamente (no deja el archivo abierto).

**Criterio de aceptación:** El error message es accionable. No se crean artifacts parciales.

---

### FASE 3 — Hardening de Contratos, CI y Documentación

---

#### BUG-02 — Deprecar flag --no-include-pozos

| Campo | Valor |
|-------|-------|
| **ID** | BUG-02 |
| **Tipo** | `bugfix` + `docs` |
| **Fuente** | F-02 (auditoría) |
| **Prioridad** | P2 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo |
| **Estado** | `done` |

| **Dependencias** | BUG-01 (la firma está estabilizada) |
| **Fase** | 3 |
| **Archivos** | `polla_app/__main__.py`, `CHANGELOG.md` |

**Problema:** `--no-include-pozos` / `include_pozos=False` no tiene efecto (el param no se pasa a `_run_ingestion_for_sources`). Conectarlo correctamente resultaría en `RuntimeError` porque el pipeline es pozos-only.

**Pasos de implementación:**
1. En el CLI `run`, añadir un `click.echo` de deprecation warning si `include_pozos=False`:
   ```python
   if not include_pozos:
       click.echo("Warning: --no-include-pozos is deprecated and has no effect. It will be removed in v4.0.", err=True)
   ```
2. Añadir nota en `CHANGELOG.md` bajo `[Unreleased]`.
3. **No eliminar el flag** — mantener por ≥1 MINOR version.

**Criterio de aceptación:** `polla run --no-include-pozos` emite deprecation warning en stderr. El pipeline continúa normalmente.

---

#### BUG-03 — Corregir --sources all para evitar double-fetching

| Campo | Valor |
|-------|-------|
| **ID** | BUG-03 |
| **Tipo** | `bugfix` |
| **Fuente** | F-03 (auditoría) |
| **Prioridad** | P2 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo (fix mínimo en _normalize_sources) |
| **Estado** | `done` |

| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `polla_app/pipeline.py` |

**Problema:** `--sources all` retorna `["openloto", "pozos", "resultadoslotochile"]` y los 3 loaders juntos hacen 4 requests HTTP (cada fuente aparece 2 veces en `collected`).

**Pasos de implementación (Opción B — mínimo riesgo):**
1. En `_normalize_sources`, si "pozos" está en la lista resultante junto a "openloto" y/o "resultadoslotochile", colapsar todo a `["pozos"]` ya que "pozos" incluye ambas fuentes.
   ```python
   if "pozos" in normalised and (
       "openloto" in normalised or "resultadoslotochile" in normalised
   ):
       return ["pozos"]
   ```
2. Documentar en el docstring de `_normalize_sources` que "all" es equivalente a "pozos".
3. Añadir test que verifica que `_normalize_sources(["all"])` == `["pozos"]`.

**Criterio de aceptación:**
- `--sources all` produce los mismos resultados que `--sources pozos`.
- Test lo verifica.

---

#### DEBT-01 — Documentar semántica de force_publish en ambos comandos

| Campo | Valor |
|-------|-------|
| **ID** | DEBT-01 |
| **Tipo** | `docs` |
| **Fuente** | F-04 (auditoría) |
| **Prioridad** | P2 |
| **Esfuerzo** | S |
| **Riesgo** | Ninguno |
| **Estado** | `done` |

| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `polla_app/__main__.py` |

**Problema:** `run --force-publish` solo overridea "unchanged/skip". `publish --force-publish` overridea quarantine. Misma bandera, comportamientos distintos, no documentados.

**Pasos de implementación:**
1. En `run`, actualizar el help text:
   ```
   "Force publish even if data is unchanged (does NOT override quarantine — use 'publish --force-publish' for that)."
   ```
2. En `publish`, actualizar el help text:
   ```
   "Override quarantine and publish regardless of run summary decision."
   ```

**Criterio de aceptación:** `polla run --help` y `polla publish --help` explican la diferencia.

---

#### DEBT-02 — Fix _should_redact_key: substring match demasiado amplio

| Campo | Valor |
|-------|-------|
| **ID** | DEBT-02 |
| **Tipo** | `hardening` |
| **Fuente** | F-09 (auditoría) |
| **Prioridad** | P2 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo |
| **Estado** | `done` |

| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `polla_app/obs.py` |

**Problema:** `any(tok in key_l for tok in (..., "key"))` redacta cualquier campo cuyo nombre contenga "key" como substring (e.g., `"monkey"`, `"jockey"`).

**Pasos de implementación:**
1. Reemplazar la detección de `"key"` por una verificación de palabra completa:
   ```python
   return any(
       tok in key_l
       for tok in ("password", "secret", "token", "credential", "apikey", "api_key")
   ) or key_l == "key" or key_l.endswith("_key") or key_l.startswith("key_")
   ```
2. Añadir tests parametrizados:
   - `_should_redact_key("monkey")` → `False`
   - `_should_redact_key("api_key")` → `True`
   - `_should_redact_key("secret_token")` → `True`
   - `_should_redact_key("jockey")` → `False`

**Criterio de aceptación:** Tests pasan. `_should_redact_key("monkey")` retorna `False`.

---

#### DEBT-03 — Refactorizar _init_log_stream a typed Protocol

| Campo | Valor |
|-------|-------|
| **ID** | DEBT-03 |
| **Tipo** | `refactor` |
| **Fuente** | F-05 (auditoría) |
| **Prioridad** | P2 |
| **Esfuerzo** | M |
| **Riesgo** | Bajo (comportamiento idéntico, solo tipos mejoran) |
| **Estado** | `done` |

| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `polla_app/pipeline.py` |

**Problema:** `_init_log_stream` retorna una función con atributos `.close` y `.set_correlation_id` inyectados post-definición. Los `# type: ignore[attr-defined]` en pipeline.py son el síntoma.

**Pasos de implementación:**
1. Definir un `Protocol` o dataclass:
   ```python
   @dataclass
   class _LogStream:
       _fn: Callable[[dict[str, Any]], None]
       close: Callable[[], None]
       set_correlation_id: Callable[[str], None]
       def __call__(self, payload: dict[str, Any]) -> None:
           self._fn(payload)
   ```
2. Hacer que `_init_log_stream` retorne `_LogStream`.
3. Eliminar los `# type: ignore[attr-defined]` en las llamadas a `.close` y `.set_correlation_id`.
4. Actualizar el type hint de `log_event` en `_run_ingestion_for_sources` de `Callable[...]` a `_LogStream`.

**Criterio de aceptación:** `# type: ignore[attr-defined]` eliminados de pipeline.py para log stream. `mypy polla_app` pasa. Tests existentes pasan sin cambios.

---

#### DEBT-04 — Pasar mismatches directamente a _build_report_payload

| Campo | Valor |
|-------|-------|
| **ID** | DEBT-04 |
| **Tipo** | `refactor` |
| **Fuente** | F-21 (auditoría) |
| **Prioridad** | P3 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo |
| **Estado** | `done` |

| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `polla_app/pipeline.py` |

**Problema:** `_build_report_payload` siempre construye con `mismatched_categories: 0` y `mismatches: []`, y luego `_run_ingestion_for_sources` los sobreescribe inmediatamente.

**Pasos de implementación:**
1. Añadir `mismatches: list[dict[str, Any]]` a la firma de `_build_report_payload`.
2. Eliminar las dos líneas de post-hoc overwrite en `_run_ingestion_for_sources`.

**Criterio de aceptación:** `_build_report_payload` construye el payload completo en una sola pasada.

---

#### DEBT-05 — Poplar missing_sources y documentar tie-breaking

| Campo | Valor |
|-------|-------|
| **ID** | DEBT-05 |
| **Tipo** | `hardening` |
| **Fuente** | F-06 (auditoría) |
| **Prioridad** | P3 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo (solo añade información al report, no cambia decisión) |
| **Estado** | `done` |

| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `polla_app/pipeline.py` |

**Problema:** (1) `missing_sources` en cada mismatch siempre es `[]`. No aporta información diagnóstica. (2) Cuando dos fuentes empatan en votos, gana la primera en iteración (first-fetcher wins) pero esto no está documentado.

**Pasos de implementación:**
1. En `_merge_pozos`, calcular qué fuentes existen en el colectado pero no reportaron un valor para esa categoría, y popularlo en `missing_sources`.
2. Añadir docstring explícito en `_merge_pozos` describiendo la regla de desempate.
3. Añadir test que verifica que `missing_sources` se popula correctamente cuando una fuente no tiene una categoría que la otra sí tiene.

**Criterio de aceptación:** `missing_sources` tiene datos reales en el report cuando aplica. Docstring documenta tie-breaking.

---

#### CI-03 — Añadir umbral de cobertura en Codecov

| Campo | Valor |
|-------|-------|
| **ID** | CI-03 |
| **Tipo** | `ci` |
| **Fuente** | F-26 (auditoría) |
| **Prioridad** | P3 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo (puede hacer fallar CI si la cobertura cae, que es el objetivo) |
| **Estado** | `done` |

| **Dependencias** | TEST-01, TEST-03 (para que el baseline de coverage sea real) |
| **Fase** | 3 |
| **Archivos** | `.github/workflows/scrape.yml` o `.codecov.yml` |

**Problema:** Coverage se sube a Codecov pero `fail_ci_if_error: false` y no hay threshold definido. La cobertura puede erosionarse silenciosamente.

**Pasos de implementación:**
1. Crear `.codecov.yml` con coverage target (≥80% recomendado, ajustar al baseline real tras Fase 2):
   ```yaml
   coverage:
     status:
       project:
         default:
           target: 80%
           threshold: 2%
   ```
2. Cambiar `fail_ci_if_error: false` a `fail_ci_if_error: true` en el action de Codecov.

**Criterio de aceptación:** Un PR que reduzca cobertura por debajo del threshold falla CI.

---

#### CI-04 — Evaluar y eliminar sync-main-to-master.yml

| Campo | Valor |
|-------|-------|
| **ID** | CI-04 |
| **Tipo** | `ci` |
| **Fuente** | F-24 (auditoría) |
| **Prioridad** | P3 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo (solo si nadie depende de `master`) |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `.github/workflows/sync-main-to-master.yml` |

**Pasos de implementación:**
1. Verificar si la rama `master` tiene dependencias externas (otras Actions, integrations, badges).
2. Si no hay dependencias: eliminar el workflow y archivar la rama `master`.
3. Si hay dependencias: documentar qué las usa y planificar migración.

**Criterio de aceptación:** Decisión tomada y ejecutada. Si se elimina, el workflow no existe.

---

#### DOCS-01 — Documentar env vars faltantes en README

| Campo | Valor |
|-------|-------|
| **ID** | DOCS-01 |
| **Tipo** | `docs` |
| **Fuente** | F-27 (auditoría) |
| **Prioridad** | P3 |
| **Esfuerzo** | S |
| **Riesgo** | Ninguno |
| **Estado** | `done` |

| **Dependencias** | BUG-01 (para documentar el comportamiento correcto post-fix) |
| **Fase** | 3 |
| **Archivos** | `README.md` |

**Problema:** README no documenta `POLLA_BACKOFF_FACTOR`, `POLLA_429_BACKOFF_SECONDS` (compat alias), ni `POLLA_MAX_RETRIES`. Tampoco actualiza la tabla de configuración post BUG-01.

**Pasos de implementación:**
1. Añadir las tres env vars a la tabla de configuración del README.
2. Post BUG-01: actualizar la descripción de `--retries` y `--timeout` para reflejar que ahora realmente controlan el comportamiento.

**Criterio de aceptación:** `grep "POLLA_BACKOFF_FACTOR" README.md` retorna resultado.

---

#### DOCS-03 — Corregir diagrama Mermaid

| Campo | Valor |
|-------|-------|
| **ID** | DOCS-03 |
| **Tipo** | `docs` |
| **Fuente** | F-28 (auditoría) |
| **Prioridad** | P3 |
| **Esfuerzo** | S |
| **Riesgo** | Ninguno |
| **Estado** | `done` |
| **Dependencias** | Ninguna |
| **Fase** | 3 |
| **Archivos** | `README.md` |

**Problema:** El diagrama llama "OpenLoto fallback" cuando en realidad ambas fuentes se consultan siempre (no hay activación condicional).

**Pasos de implementación:**
1. Cambiar `|OpenLoto fallback|` a `|OpenLoto|` en el diagrama Mermaid.
2. Añadir nodo de consensus engine explícito entre el normalizer y la decisión publish.

---

### FASE 4 — Features de Alto Valor

---

#### FEAT-02 — Notificaciones de quarantine enriquecidas

| Campo | Valor |
|-------|-------|
| **ID** | FEAT-02 |
| **Tipo** | `feature` |
| **Fuente** | Feature-4 (auditoría) |
| **Prioridad** | P4 |
| **Esfuerzo** | S |
| **Riesgo** | Bajo |
| **Estado** | `done` |
| **Dependencias** | Fases 0-3 cerradas |
| **Fase** | 4 |
| **Archivos** | `polla_app/notifiers.py`, `polla_app/pipeline.py` |

**Problema:** Cuando el pipeline entra en quarantine, el operador recibe solo un fallo de CI genérico (o nada si no hay webhook). El detalle del mismatch (qué fuentes, qué categorías, qué valores) queda en los artifacts.

**Pasos de implementación:**
1. Añadir función `notify_quarantine(mismatches, run_id, webhook_url)` en `notifiers.py`.
2. Llamar desde `_run_ingestion_for_sources` cuando `decision_status == "quarantine"`.
3. El mensaje de Slack incluye: run_id, categorías en discrepancia, valores por fuente, max_deviation.
4. Test con webhook URL mockeada.

**Criterio de aceptación:** Un quarantine con SLACK_WEBHOOK_URL configurado emite un mensaje con detalle de mismatch. Sin webhook, silencio (no error).

---

#### FEAT-01 — Degraded mode single-source con campo `confidence`

| Campo | Valor |
|-------|-------|
| **ID** | FEAT-01 |
| **Tipo** | `feature` |
| **Fuente** | Feature-1 (auditoría) |
| **Prioridad** | P4 |
| **Esfuerzo** | M |
| **Riesgo** | Medio (cambio de schema → API_VERSION bump requerido) |
| **Estado** | `done` |
| **Dependencias** | TEST-01 (comportamiento de fallo verificado), Fases 0-3 cerradas |
| **Fase** | 4 |
| **Archivos** | `polla_app/pipeline.py`, `polla_app/contracts.py`, `docs/API.md` |

**Problema:** Cuando una fuente falla, el pipeline continúa con la restante pero el resultado no indica que la confianza es reducida. No hay forma de distinguir en el output si el consensus fue con 2 fuentes o con 1.

**Pasos de implementación:**
1. Añadir campo `"confidence": "full" | "degraded" | "single_source"` al normalized record.
2. "full": todas las fuentes solicitadas respondieron y acordaron.
3. "degraded": alguna fuente falló pero el consensus fue con las restantes.
4. "single_source": solo una fuente respondió (no hay consensus posible).
5. Bumpar `API_VERSION` de "v1.1" a "v1.2" (additive change).
6. Actualizar `docs/API.md` y `tests/test_contracts.py`.

**Criterio de aceptación:**
- `normalized.jsonl` incluye campo `confidence`.
- `API_VERSION == "v1.2"`.
- Test verifica el campo en cada scenario (full, degraded, single_source).
- `docs/API.md` actualizado.

---

#### FEAT-03 — Drift detection histórico (últimos N runs)

| Campo | Valor |
|-------|-------|
| **ID** | FEAT-03 |
| **Tipo** | `feature` |
| **Fuente** | Feature-2 (auditoría) |
| **Prioridad** | P4 |
| **Esfuerzo** | M |
| **Riesgo** | Medio (requiere cambio de arquitectura del state file) |
| **Estado** | `todo` |
| **Dependencias** | FEAT-01 (schema estable) |
| **Fase** | 4 |
| **Archivos** | `polla_app/pipeline.py` |

**Problema:** El state file mantiene solo el último run (1 record). No hay historial para detectar que una fuente lleva 5 runs reportando valores 40% por encima de la otra.

**Pasos de implementación:**
1. Cambiar `_write_jsonl(state_path, [record])` para mantener los últimos N records (configurable via `POLLA_STATE_HISTORY_SIZE`, default 10).
2. Añadir función `_detect_drift(history, current_record) -> list[dict]` que retorna alertas de drift.
3. Incluir drift alerts en el comparison report.
4. Test con historial sintético que verifica detección de drift ≥ X% en los últimos N runs.

**Criterio de aceptación:** State file mantiene hasta N records. Drift alerts aparecen en comparison report cuando aplican.

---

#### FEAT-04 — Smoke fixture framework para nuevas fuentes

| Campo | Valor |
|-------|-------|
| **ID** | FEAT-04 |
| **Tipo** | `feature` |
| **Fuente** | Feature-5 (auditoría) |
| **Prioridad** | P4 |
| **Esfuerzo** | M |
| **Riesgo** | Bajo |
| **Estado** | `done` |
| **Dependencias** | BUG-03 (registry limpio) |
| **Fase** | 4 |
| **Archivos** | `tests/fixtures/`, `tests/test_smoke_sources.py` |

**Problema:** Añadir una nueva fuente requiere código + tests escritos a mano. No hay estructura declarativa para registrar "para esta fuente, dado este HTML, esperamos estos montos".

**Pasos de implementación:**
1. Crear estructura `tests/fixtures/sources/<nombre_fuente>/` con `page.html` + `expected.json`.
2. Escribir test parametrizado que descubre automáticamente todas las entradas en ese directorio y las ejecuta.
3. Documentar el proceso en `CONTRIBUTING.md`.

**Criterio de aceptación:** Añadir una nueva fuente requiere solo: HTML fixture + expected.json + entrada en SOURCE_LOADERS. Sin código de test manual.

---

#### FEAT-05 — Soporte JSON API como tipo de fuente

| Campo | Valor |
|-------|-------|
| **ID** | FEAT-05 |
| **Tipo** | `feature` |
| **Fuente** | Feature-3 (auditoría) |
| **Prioridad** | P4 |
| **Esfuerzo** | L |
| **Riesgo** | Alto (refactor mayor del registry y del contrato de fuentes) |
| **Estado** | `todo` |
| **Dependencias** | FEAT-04 (framework de fixtures), BUG-03 (registry limpio) |
| **Fase** | 4 |
| **Archivos** | `polla_app/sources/`, `polla_app/pipeline.py` |

**Problema:** El sistema solo soporta fuentes HTML (BeautifulSoup). Si una fuente expone una API JSON, no hay forma de integrarla sin código de scraping redundante.

**Pasos de implementación:**
1. Definir un protocolo `SourceFetcher` que cualquier fuente debe satisfacer (retorna el dict estándar).
2. Implementar `JsonFetcher` como clase que recibe una URL + schema de mapping de campos.
3. Registrar fuentes JSON en SOURCE_LOADERS de la misma forma que las HTML.
4. Tests con fixture JSON.

**Criterio de aceptación:** Una fuente JSON puede registrarse y usarse sin código HTML de scraping.

---

## Vista por Prioridad

| Prioridad | IDs |
|-----------|-----|
| **P0** | SEC-01, CI-01, CI-02, DOCS-02, BUG-01 |
| **P1** | BUG-04, TEST-01, TEST-02, TEST-03, TEST-05 |
| **P2** | BUG-02, BUG-03, DEBT-01, TEST-04 |
| **P3** | DEBT-02, DEBT-03, DEBT-04, DEBT-05, CI-03, CI-04, DOCS-01, DOCS-03 |
| **P4** | FEAT-01, FEAT-02, FEAT-03, FEAT-04, FEAT-05 |

## Vista por Quick Wins

| ID | Título | Esfuerzo | Impacto |
|----|--------|----------|---------|
| SEC-01 | Remover spreadsheet ID hardcodeado | S | Seguridad |
| CI-01 | Alinear worksheet dry-run | S | Operacional |
| CI-02 | Quitar auto-fix en CI | S | Calidad de CI |
| TEST-02 | Completar test monetario | S | Cobertura |
| BUG-04 | Error handling pozos CLI | S | UX operacional |
| DEBT-01 | Documentar force_publish | S | Claridad |
| DEBT-02 | Fix _should_redact_key | S | Corrección |
| BUG-03 | Fix --sources all | S | Correctitud |
| FEAT-02 | Quarantine notifications | S | Valor operacional |

## Ítems Deferred (No ahora)

| ID | Razón del defer |
|----|----------------|
| FEAT-05 | Requiere refactor mayor del registry. No hay fuente JSON disponible hoy. |
| FEAT-03 | Requiere decisión de arquitectura sobre el state file. Hacer después de FEAT-01. |
| DEBT-06 | `requests.Session` per-call — impacto negligible para 2 requests/run. |
