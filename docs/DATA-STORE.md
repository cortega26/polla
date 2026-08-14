# Almacenamiento de datos: decisión arquitectónica

Fecha: 2026-08-14 · Estado: **adoptado (Opción A mejorada + capa de presentación propia)**

## Pregunta

Google Sheets es hoy el único "frontend" del proyecto. ¿Conviene migrar a base de
datos + visualización propia?

## Criterios evaluados

| Criterio | Opción A (Sheets mejorado) | Opción B (DB + UI propia) |
|---|---|---|
| Complejidad | Baja | Alta (SQLite/Postgres + API + hosting) |
| Costo | $0 | $0 (SQLite) a $$$ (Supabase/Postgres) |
| Mantenimiento | Bajo | Medio-alto |
| Confiabilidad | Media (API externa) | Alta |
| Velocidad | Media (API) | Alta |
| Historial | Solo último + discrepancias | Completo |
| Backup | API / export | Archivo o dump |
| Vendor lock-in | Medio (formato propietario) | Bajo |
| Consultas/estadísticas | Frágil | Poderosas |

## Hallazgo clave del despliegue

El pipeline corre en **GitHub Actions (runners efímeros)**. Cualquier almacén
local — SQLite incluido — se pierde cuando expira el cache de `pipeline_state`.
Es decir: la migración a SQLite **no añade durabilidad real** en el despliegue
actual; el único almacén durable es Google Sheets (o un servicio externo).

## Decisión: Opción A mejorada + dashboard estático propio

1. **Se mantiene Google Sheets** como almacén público durable y destino de
   publicación (sin break de contrato): hojas `Proximo Pozo`, `Kino` y tabs de
   discrepancias.
2. **Se añade un dashboard estático** (`site/`, sin dependencias, sin build):
   HTML/CSS/JS que consume `site/data.json` generado por `polla site`, publicado
   en GitHub Pages por `.github/workflows/pages.yml`. Responde a la necesidad de
   presentación profesional (ver sección 5 del plan de revamp) sin infraestructura.
3. **Mejoras de robustez del lado Sheets** ya implementadas (Wave 1):
   lock anti-concurrencia (`_PublishLock`), dedupe de records por `(sorteo, fecha)`,
   y worksheet por juego (evita mezclar categorías Loto/Kino).
4. **SQLite queda descartado hoy** y se revisará si se incorporan resultados de
   sorteos con historial largo y estadísticas de frecuencia de números
   (requiere una fuente de números ganadores; hoy el alcance es pozos-only).

## Migración de datos

No aplica: no se descarta ningún dato. Los artifacts (`artifacts/`, `artifacts_kino/`)
se siguen generando por corrida y el estado deduplicado (`pipeline_state/`) mantiene
el historial acotado a `MAX_STATE_RECORDS` sorteos.

## Evolución futura (si el producto crece)

- Resultados de sorteos (números) → SQLite local o Supabase como system-of-record.
- Expansión a otros juegos → misma arquitectura: parser → validación → consenso → sheets + dashboard.
