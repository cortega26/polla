# Risk Register — polla v3.1.0

**Fecha:** 2026-03-28
**Scope:** Riesgos activos antes de completar Wave 2.
**Formato:** Probabilidad × Impacto = Exposición (H/M/L)

Solo se registran riesgos que no son obvios o que requieren atención operacional activa. Los riesgos ya mitigados por Wave 1 no se incluyen.

---

| ID | Descripción | Prob | Impacto | Exposición | Estado | Mitigación | Ítem del backlog |
|----|-------------|------|---------|------------|--------|------------|-----------------|
| R-01 | Un operador configura `--timeout` o `--retries` creyendo que controla la red. El comportamiento real ignora esos valores → timeouts inesperadamente largos o reintentos no esperados | Alta | Medio | **Alta** | Activo | BUG-01 | BUG-01 |
| R-02 | Una fuente falla parcialmente en producción. El pipeline puede: (a) completar con datos de solo una fuente sin indicarlo, o (b) lanzar RuntimeError sin artifacts. Comportamiento actual no verificado | Media | Alto | **Alta** | Activo | TEST-01 + FEAT-01 | TEST-01, TEST-05 |
| R-03 | El dry-run diario (update.yml) compara diff contra hoja "Normalized". La publicación real va a "Proximo Pozo". El operador ve un diff que no refleja lo que se va a publicar | Alta | Medio | **Alta** | Activo | CI-01 | CI-01 |
| R-04 | Spreadsheet ID de producción expuesto en repo público. Si las credenciales de la service account tienen permisos más amplios de lo necesario, el ID facilita un ataque dirigido | Baja | Medio | **Media** | Activo | SEC-01 | SEC-01 |
| R-05 | `--sources all` activa fetches duplicados en producción si alguien experimenta con el flag. Cada fuente aparece 2× en el consensus, distorsionando el resultado | Baja | Medio | **Media** | Latente | BUG-03 | BUG-03 |
| R-06 | `force_publish` tiene semánticas distintas en `run` vs `publish`. Un operador usa `run --force-publish` esperando override de quarantine, no lo logra. Publica datos en disputa sin saberlo | Baja | Alto | **Media** | Activo | DEBT-01 | DEBT-01 |
| R-07 | CI en scrape.yml auto-corrige formato antes de testear. Un commit con código mal formateado pasa CI (el workflow lo arregla silenciosamente). La rama puede acumular commits con formato inconsistente | Media | Bajo | **Media** | Activo | CI-02 | CI-02 |
| R-08 | No hay umbral de cobertura en CI. La adición de código nuevo sin tests puede erosionar la cobertura sin alertar. Actualmente se sube a Codecov pero no hay enforcement | Alta | Bajo | **Media** | Activo | CI-03 | CI-03 |
| R-09 | `_should_redact_key("jockey")` → `True`. Cualquier campo de log cuyo nombre contenga "key" como substring es redactado. Si se añaden campos de diagnóstico con nombres como "monkey_patch_key", sus valores serán ocultos en logs | Baja | Bajo | **Baja** | Latente | DEBT-02 | DEBT-02 |
| R-10 | robots.txt cacheado sin TTL. En un proceso de larga duración (no el caso hoy), un cambio en la política robots.txt de una fuente no sería detectado hasta reiniciar | Muy baja | Medio | **Baja** | Latente | No planificado (aceptar riesgo para el modelo actual de scheduled jobs) | — |

---

## Riesgos Aceptados (no se toman acciones)

| ID | Descripción | Justificación |
|----|-------------|---------------|
| R-10 | robots.txt TTL | El sistema corre como scheduled job de ~segundos. El riesgo solo materializa en procesos long-lived, que no es el modelo actual. |
| R-11 | `requests.Session` per call sin connection pooling | Impacto negligible para 2 requests/run en job diario. |
| R-12 | BeautifulSoup usa `html.parser` en lugar de `lxml` (más lento) | `lxml` no es dependencia del proyecto. El parsing tarda <150ms para las fuentes actuales. Añadir dependencia no vale el beneficio. |

---

## Escalada

Si R-01 o R-02 se manifiestan en producción antes de que BUG-01/TEST-01 estén resueltos:

**R-01 workaround:** Setear `POLLA_MAX_RETRIES` y `POLLA_BACKOFF_FACTOR` como env vars del workflow en lugar de depender de `--retries`/`--timeout`. Estas env vars sí tienen efecto.

**R-02 workaround:** Monitorear los artifacts de cada run. Si `comparison_report.json` tiene `sources.pozos.premios: 0` con una sola fuente en provenance, investigar manualmente.
