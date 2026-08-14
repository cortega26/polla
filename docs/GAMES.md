# Expansión: otros juegos legales de Chile (ranking)

Fecha: 2026-08-14 · Basado en verificación en vivo de fuentes oficiales (polla.cl, loteria.cl).

## Evidencia de campo (auditoría en vivo)

| Juego | Operador | Verificación en vivo |
|---|---|---|
| LOTO / Recargado / Revancha / Desquite / Jubilazo | Polla Chilena | Home polla.cl muestra sorteo 5464 con números + pozos ✓ |
| LOTO 3, LOTO 4, RACHA, BOLETO | Polla Chilena | Página oficial de resultados (`/es/view/resultados`) los lista con sorteo, fecha y números ✓ |
| **Kino** | **Lotería de Concepción** | `pendon-kino.loteria.cl/pendonkino` con pozo del sorteo 3266 ✓ (ya integrado) |
| Kino5, Mega Sorteo, Boleto, Al Fin le Achunté, Multiplica tus Lucas | Lotería de Concepción | Menú oficial `loteria.cl` ✓ |
| Polla Gol | Polla Chilena (Xperto) | Resultados en `xperto.polla.cl/es/view/pool-betting-results` ✓ |

**Hallazgo clave**: Kino ya no es de Polla Chilena (transferido a Lotería de Concepción);
polla.cl lo retiró de sus juegos. Cualquier parser de "Kino de Polla" estaría roto hoy.

## Ranking multifactorial

| # | Juego | Usuarios | Resultados públicos | Estabilidad fuente | Dificultad scraping | Valor | Prioridad |
|---|---|---|---|---|---|---|---|
| 1 | **LOTO (resultados + pozos)** | Muy altos | Alta (página oficial) | Alta | Media (SPA, ya resuelto) | Alto | **P1 — ya cubierto** |
| 2 | **Kino (pozos)** | Altos | Alta (pendón JSON) | Alta | Baja | Alto | **P1 — ya integrado** |
| 3 | LOTO 3 / LOTO 4 / RACHA / BOLETO | Medios | Alta (misma página) | Alta | Media | Medio | P2 |
| 4 | Kino resultados (números) | Altos | Media (hub requiere sesión) | Media | Alta | Alto | P2 (requiere sesión) |
| 5 | Polla Gol | Medios | Alta (xperto) | Media | Media | Medio | P2 |
| 6 | Kino5 / Mega Sorteo (Lotería) | Medios | Media | Media | Media | Medio | P3 |
| 7 | Raspes / videojuegos | Altos | No aplica (sin sorteo) | — | — | Bajo | No |

## Recomendación

1. **Resultados de LOTO** (números ganadores del sorteo, ya visibles en `/es/view/resultados`)
   es la siguiente expansión con mejor relación valor/esfuerzo: misma infraestructura,
   añade frecuencia de números y estadísticas reales al dashboard.
2. **Kino números** está bloqueado por el hub autenticado (rckino.loteria.cl redirige
   a la home sin sesión); usar solo pozos del pendón hasta que haya endpoint público.
3. No incorporar juegos marginales (raspes/videojuegos) — no aportan al pipeline de pozos.

## Criterios aplicados (del plan de revamp)

- Fuentes oficiales verificadas en vivo; sin suposiciones de vigencia legal.
- Valor para el usuario > tráfico potencial > facilidad de scraping.
- Un juego solo se incorpora si puede automatizarse de forma confiable.
