# Polla App — Ingesta confiable de pozos para el Loto de Chile

*Parte del [ecosistema Tooltician](https://tooltician.com) — datos de pozos confiables y verificados para el Loto de Chile.*

[![Parte de Tooltician](https://img.shields.io/badge/Parte_de-Tooltician.com-6C47FF?v=2)](https://tooltician.com)

Agrega estimaciones del próximo pozo integrando la fuente oficial de `polla.cl` con espejos comunitarios verificados, garantiza la procedencia mediante consenso y publica actualizaciones en Google Sheets.

[![Tests](https://github.com/cortega26/polla/actions/workflows/tests.yml/badge.svg)](https://github.com/cortega26/polla/actions/workflows/tests.yml) [![Docs](https://github.com/cortega26/polla/actions/workflows/docs.yml/badge.svg)](https://github.com/cortega26/polla/actions/workflows/docs.yml) [![Health](https://github.com/cortega26/polla/actions/workflows/health.yml/badge.svg)](https://github.com/cortega26/polla/actions/workflows/health.yml) [![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3130/) [![License](https://img.shields.io/github/license/cortega26/polla)](license.md) [![Last commit](https://img.shields.io/github/last-commit/cortega26/polla)](https://github.com/cortega26/polla/commits/main)

## Características

- Orquestación de ingesta multi-fuente con un registro unificado (`pozos`, `openloto`, `polla`, `kino`) y mecanismos de respaldo deterministas.
- **Kino (Lotería de Concepción)**: parser sobre el pendón oficial (`pendon-kino.loteria.cl`), sin navegador, con validación y dedupe propias.
- Garantía de integridad de datos mediante verificación de hash SHA-256 y cuarentena por consenso basada en magnitud (umbral del 10%).
- Sistema de **Puntaje de Confianza** (`full`, `degraded`, `single_source`) para señalar la fiabilidad de los datos.
- **Dashboard público estático** (`site/`, sin dependencias): `polla site` genera `site/data.json` y GitHub Pages lo publica.
- Envío de **Notificaciones Enriquecidas en Slack** para ejecuciones exitosas y **Alertas de Cuarentena** detalladas ante discrepancias.
- Generación de salidas estructuradas en JSONL y reportes de comparación con trazabilidad completa de procedencia.
- CLI basado en Click (`run`, `publish`, `pozos`, `kino`, `site`, `health`) con previsualización de cambios (dry-run) y salvaguardas automatizadas.
- Manejo elegante de límites de tasa (rate-limiting) con retroceso exponencial (jittered backoff), reintentos ante timeouts/caídas de conexión y respeto a robots.txt.
- Validación de datos por juego (`validation.py`): montos, sorteo y fecha antes de publicar nada sospechoso.
- Comportamiento asegurado con suites de pytest basadas en fixtures y cumplimiento automático de cobertura (umbral del 80%).

## Stack Tecnológico

- Python 3.13+, Click CLI, Requests + parsers BeautifulSoup
- Integración con Google Sheets vía `gspread` + `google-auth` (con lock anti-concurrencia)
- Dashboard estático vanilla (HTML/CSS/JS) publicado con GitHub Pages
- Pruebas: Pytest (+ doctests), fixtures de Faker
- Herramientas: Ruff, Black, Mypy, GitHub Actions (tests, docs, health, scrape, pages)

## Arquitectura de un Vistazo

```mermaid
%%{init: {"themeVariables": {"fontSize":"16px"}, "flowchart": {"htmlLabels": false, "wrap": true}}}%%
flowchart TB
  A[Comando CLI] --> B[Orquestador de Pipeline]
  B --> C{Registro de fuentes}
  C -->|Polla.cl| D[Fetcher Sigiloso]
  C -->|OpenLoto| E[Fuente Espejo]
  C -->|Pendón Kino| F[Fetcher Kino Lotería]
  D & E & F --> G[Validación por juego]
  G --> H[Normalizador]
  H --> I[Motor de Consenso]
  I --> J["Artifacts<br/>(JSONL, reportes, estado)"]
  J --> K{Decisión}
  K -->|Publicar| L[Google Sheets vía gspread]
  K -->|Cuarentena| M[Alerta Detallada en Slack]
  K -->|Omitir| N[Finalización silenciosa]
  J --> O[polla site]
  O --> P[Dashboard estático → GitHub Pages]
  B --> Q["Logging estructurado<br/>(spans + métricas)"]

```

## Inicio Rápido

1. **Valida tu entorno**: Ejecuta la verificación automática para asegurar que todo esté configurado correctamente:

   ```bash
   make ready
   ```

   Si `make ready` falla por falta de pre-commit, instala las dependencias de desarrollo (`pip install -r requirements-dev.txt`) y los hooks (`pre-commit install`).

2. **Ejecuta el pipeline de pozos localmente**:

   ```bash
   python -m polla_app run --sources pozos
   ```

3. **Ejecuta el pipeline de Kino (Lotería de Concepción)**:

   ```bash
   python -m polla_app run --sources kino
   ```

4. **Genera el dashboard estático**:

   ```bash
   python -m polla_app site \
     --normalized artifacts/normalized.jsonl \
     --normalized-kino artifacts_kino/normalized.jsonl \
     --output site/data.json
   ```

5. **Simulacro de publicación** (requiere credenciales):

   ```bash
   python -m polla_app publish --dry-run \
     --normalized artifacts/normalized.jsonl \
     --comparison-report artifacts/comparison_report.json
   ```

### Configuración

| Nombre                               | Tipo        | Por defecto     | Requerido      | Descripción                                                           |
| :----------------------------------- | :---------- | :-------------- | :------------- | :-------------------------------------------------------------------- |
| `GOOGLE_SPREADSHEET_ID`              | string      | —               | Para `publish` | ID de la hoja de cálculo de Google para la publicación.               |
| `GOOGLE_SERVICE_ACCOUNT_JSON`        | string JSON | —               | Condicional    | Credenciales de cuenta de servicio en línea (alternativa a archivo).  |
| `GOOGLE_CREDENTIALS` / `CREDENTIALS` | string JSON | —               | Condicional    | Variables de entorno legacy para autenticación de cuenta de servicio. |
| `service_account.json`               | archivo     | —               | Condicional    | Credenciales en disco si no se proporcionan variables de entorno.     |
| `ALT_SOURCE_URLS`                    | string JSON | `{}`            | No             | Sobrescribe las URLs de las fuentes para espejos o pruebas.           |
| `POLLA_USER_AGENT`                   | string      | Library default | No             | User-agent HTTP personalizado para scraping respetuoso.               |
| `POLLA_RATE_LIMIT_RPS`               | float       | sin definir     | No             | Límite de peticiones por segundo por host.                            |
| `POLLA_MAX_RETRIES`                  | entero      | `3`             | No             | Máximo de intentos de reintento por petición.                         |
| `POLLA_BACKOFF_FACTOR`               | float       | `30.0`          | No             | Multiplicador base del retroceso exponencial (`factor * 2^(intento-1)` segundos; cubre 429/500/502/503/504). |
| `POLLA_429_BACKOFF_SECONDS`          | float       | —               | No             | Alias legacy: se usa como factor de retroceso solo si `POLLA_BACKOFF_FACTOR` no está definido. |
| `GOOGLE_SHEETS_SPREADSHEET_ID`       | string      | —               | Condicional    | Alias legacy de `GOOGLE_SPREADSHEET_ID` (misma hoja).                 |
| `SLACK_WEBHOOK_URL`                  | string      | —               | No             | Destino para resúmenes de ejecución y alertas de discrepancia.        |
| `POLLA_PUBLISH_LOCK_PATH`            | string      | `pipeline_state/publish.lock` | No  | Ubicación del lock anti-concurrencia para `publish`.                  |
| `POLLA_PUBLISH_LOCK_TIMEOUT`         | float       | `300`           | No             | Segundos máximos de espera por el lock de publicación.                |
| `POLLA_STATS_URL`                    | string      | hoja pública de referencia | No   | CSV público con estadísticas de juegos (probabilidades/retornos) que `polla site` sincroniza a `site/stats.json`. |

> **Nota sobre almacenamiento**: la decisión de arquitectura (Google Sheets vs.
> base de datos) está documentada en [docs/DATA-STORE.md](docs/DATA-STORE.md).

## Calidad y Pruebas

- `pytest -q` – ejecuta las suites de unidad e integración con fixtures offline; espera `N passed` en menos de 10s.
- `ruff check polla_app tests` – impone reglas de linting, nomenclatura e higiene de importaciones.
- `mypy polla_app tests` – verifica el tipado estricto (se ignoran stubs de terceros no disponibles).
- `black --check polla_app tests` – mantiene un formato consistente.
- `pytest --doctest-glob='*.md' README.md docs -q` – asegura que los ejemplos de la documentación sigan siendo ejecutables.

CI refleja estos comandos a través de `.github/workflows/tests.yml` y `.github/workflows/docs.yml` para que las ejecuciones locales coincidan con la automatización. Añade `pytest --cov=polla_app` cuando necesites un reporte de cobertura.[^coverage]

## Rendimiento y Confiabilidad

- **Parsing de Alto Rendimiento**: `scripts/benchmark_pozos_parsing.py` asegura que mantengamos un tiempo medio de scraping inferior a **150ms**.
- **Observabilidad**: Métricas y tramas (spans) estructuradas brindan visibilidad profunda sobre el proceso de toma de decisiones de consenso.
- **Confiabilidad**: El flujo programado `health.yml` ejercita el pipeline diariamente para detectar derivas en las fuentes antes de que impacten la producción.

## Hoja de Ruta

- Agregar fixtures de prueba de humo para nuevos espejos agregadores emergentes.
- Implementar parsing de niveles de premios más granulares para la fuente de Polla.

## Por Qué es Importante

- Demuestra empatía operativa: valores por defecto de dry-run, soporte para cuarentena y procedencia explícita reducen el estrés de guardia (on-call).
- Destaca prácticas disciplinadas de scraping respetuosas de la infraestructura de terceros y los límites legales.
- Muestra capacidad para automatizar verificaciones de confiabilidad de extremo a extremo (workflow de salud, ganchos de observabilidad, métricas estructuradas).
- Ilustra el enfoque en la experiencia del desarrollador mediante CLI reproducible, objetivos Make y puertas estrictas de tipado y linting.
- Prueba comodidad con el manejo seguro de credenciales al integrar con APIs de Google Workspace.

## Contribución y Licencia

Las contribuciones son bienvenidas—consulta [CONTRIBUTING.md](CONTRIBUTING.md) para conocer las expectativas de estilo, pruebas y revisión.

Este proyecto se distribuye bajo la [Licencia MIT](license.md).

---

Built and maintained by **Carlos Ortega** — automation, data systems, and web technical hygiene consulting. Portfolio and services: **[tooltician.com](https://tooltician.com/)**.

*Parte del [ecosistema Tooltician](https://tooltician.com) — datos de pozos confiables y verificados para el Loto de Chile.*
