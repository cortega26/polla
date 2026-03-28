# Implementation Backlog — Polla Scraper: Hardening & Evolution

Este backlog operativo rastrea la ejecución del [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Está ordenado por prioridad técnica y secuencia recomendada de ejecución.

## Backlog Operativo

| ID | Title | Category | Source Finding | Type | Priority | Status | Impact | Effort | Risk | Target Files |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **MON-01** | **Deterministic Monetary Parser** | Correctness | MON-01 | `hardening` | **P0** | `done` | Critical | M | Low | `polla_app/sources/pozos.py` |
| **PROV-01** | **SHA-256 Content-Hash Ingestion** | Observability | PROV-01 | `hardening` | **P1** | `done` | Medium | S | Low | `polla_app/net.py`, `polla_app/pipeline.py` |
| **PIPE-01** | **Pipeline Cleanup & Legacy Purge** | Architecture | PIPE-01 | `refactor` | **P1** | `done` | High | M | Medium | `polla_app/pipeline.py` |
| **NET-01** | **Jittered/Configurable Backoff** | Resilience | NET-01 | `hardening` | **P1** | `done` | Medium | S | Low | `polla_app/net.py` |
| **REG-01** | **Full Source Registry Sync** | Architecture | REG-01 | `cleanup` | **P2** | `done` | Medium | S | Low | `polla_app/pipeline.py` |
| **OBS-01** | **Key-based Contextual Redaction** | Observability | RED-01 | `refactor` | **P2** | `done` | Low | S | Low | `polla_app/obs.py`, `polla_app/exceptions.py` |
| **F-001** | **Consensus Quarantine Logic** | Feature | - | `feature` | **P2** | `done` | High | L | Medium | `polla_app/pipeline.py` |
| **F-002** | **CLI Result Diffing (Dry-run)** | DX | - | `feature` | **P3** | `done` | Medium | M | Low | `polla_app/__main__.py`, `polla_app/publish.py` |
| **DOC-01** | **API & SLOs Documentation Update** | Docs | - | `docs` | **P3** | `done` | Low | S | Low | `docs/API.md`, `README.md` |

---

## Detalle de Items Prioritarios

### MON-01: Deterministic Monetary Parser
*   **Acceptance Criteria:** 
    - Reemplazar `_parse_millones_to_clp` por un motor de parsing que no asuma separadores fijos.
    - Soportar explícitamente sufijos (MM, M, Mil) y prefijos ($).
    - Validar que el resultado sea siempre un `int` representativo de CLP absoluto.
*   **Validation:** Ejecutar `tests/test_parsers.py` ampliado con 20 casos de borde.

### PROV-01: SHA-256 Content-Hash Ingestion
*   **Acceptance Criteria:**
    - El hash debe generarse en `FetchMetadata` (ya existe) y persistirse en el campo `provenance` de cada record.
    - El orquestador debe usar este hash para evitar ruidos en el log de "cambio detectado" si el HTML es idéntico bit-a-bit.
*   **Validation:** Verificar que los archivos `normalized.jsonl` incluyen el campo `sha256` bajo cada fuente.

### PIPE-01: Pipeline Cleanup & Legacy Purge
*   **Acceptance Criteria:**
    - Eliminar las funciones comentadas y los "TODO: legacy" en `pipeline.py`.
    - Unificar el despacho de ejecución para que no haya duplicidad entre el modo de una fuente y multi-fuente.
*   **Validation:** Comparación de salida JSON entre la versión anterior y la refactorizada.

---

## Immediate Next 3 Tasks
1.  **[MON-01]** Implementar el nuevo parser con suite de pruebas reforzada.
2.  **[PROV-01]** Asegurar la persistencia del SHA-256 en el flujo de normalización.
3.  **[PIPE-01]** Refactorizar `pipeline.py` para eliminar la deuda técnica "legacy".

## High-Leverage Tasks
*   **F-001 (Quarantine):** Proporciona una red de seguridad automática ante fallos de scraping en fuentes de terceros.

## Deferred / Not Now
*   **Historical Drift Monitoring:** Requiere una base de datos de estado más persistente que simples archivos JSONL para ser realmente útil.
*   **Schema Enforcement (Pydantic):** Postpuesto hasta que la arquitectura de fuentes esté 100% estable.
