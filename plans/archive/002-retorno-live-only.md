# Plan 002: Retorno esperado solo con precio vivo — eliminar el fallback al precio de la hoja

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/stats.py tests/test_stats.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none (ejecutar tras 001 es opcional; archivos distintos)
- **Category**: bug
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

El retorno esperado mostrado en el dashboard debe calcularse solo con datos
vivos (premio scrapeado ÷ combinaciones ÷ apuesta scrapeada). Hoy, cuando el
precio vivo de Loto no está disponible (polla.cl bloquea los runners de GitHub
con 403), el código cae al precio manual de la hoja de referencia
(`Precio o apuesta (num)`), que puede estar desactualizado (cambia en sorteos
especiales). El resultado es un porcentaje "exacto" calculado con un precio
que no lo es — exactamente lo que el dueño del producto pidió eliminar
("valores concretos, objetivos y exactos; sin datos de referencia").

## Current state

- `polla_app/stats.py` — función `merge_real_prizes` (líneas ~228-262). El
  tramo del retorno:

```python
            real = _real_prize_for(game, row, prizes)
            row["premio_real_clp"] = real
            combinations = row.get("Combinaciones totales (num)")
            bet = row.get("precio_real_clp")
            if bet is None:
                bet = row.get("Precio o apuesta (num)")
            if real is not None and combinations and bet:
                row["retorno_real_pct"] = round(real / combinations / bet * 100, 2)
            else:
                row["retorno_real_pct"] = None
```

- `merge_live_kino` (líneas ~134-201) ya calcula su propio retorno con
  `delta` vivo y **no** usa el fallback — no debe tocarse.
- `site/app.js` renderiza `retorno_real_pct` directamente; si es `null`
  muestra "—" (no requiere cambios).
- Test existente que fija el fallback:
  `tests/test_stats.py::test_merge_real_prizes_overlays_live_data` usa el
  fixture `stats_sample.csv` (que tiene "Precio o apuesta" 1.000) **sin**
  precios vivos, y espera `retorno_real_pct == 13.79`. Ese test debe cambiar:
  sin precio vivo, el retorno debe ser `None`.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest tests/test_stats.py -q` | all pass |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Format    | `black --check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/stats.py` — `merge_real_prizes` (solo el cálculo de `bet`/retorno)
- `tests/test_stats.py` — actualizar tests que dependen del fallback

**Out of scope**:
- `merge_live_kino` y `merge_real_prices` (otro plan, 010, limpia `precio_estatico`).
- `site/app.js` / `site/index.html` — la UI ya maneja `null` → "—".
- Cualquier cambio en cómo se scrapean los precios.

## Git workflow

- Branch: `advisor/002-retorno-live-only`
- Un commit, mensaje estilo conventional commits (ej. `fix(stats): retorno esperado solo con precio vivo — sin fallback a la hoja`).
- NO push/PR salvo instrucción.

## Steps

### Step 1: Eliminar el fallback al precio de la hoja

En `polla_app/stats.py`, dentro de `merge_real_prizes`, reemplaza:

```python
            bet = row.get("precio_real_clp")
            if bet is None:
                bet = row.get("Precio o apuesta (num)")
```

por:

```python
            bet = row.get("precio_real_clp")
```

El resto del bloque (condición `if real is not None and combinations and bet:`
→ retorno, `else` → `None`) queda igual. Con esto, sin precio vivo el retorno
es `None` y la UI muestra "—".

**Verify**: `python -m pytest tests/test_stats.py::test_merge_real_prizes_overlays_live_data -q`
→ fallará (esperado; se actualiza en el paso 2).

### Step 2: Actualizar los tests

En `tests/test_stats.py`:

1. `test_merge_real_prizes_overlays_live_data` (líneas ~111-123): llama a
   `merge_real_prizes(payload, _prizes())` **sin** precios vivos. Cambia las
   aserciones de retorno por:

```python
    clasico = loto["Loto Clásico"]
    assert clasico["premio_real_clp"] == 620_000_000
    # Sin precio vivo, el retorno NO se calcula con el precio de la hoja
    assert clasico["retorno_real_pct"] is None
```

   (Mantén el resto de aserciones de premios.)

2. Añade un test nuevo `test_retorno_uses_live_price_when_available` que
   combine `merge_real_prices(payload, _loto_prices())` **antes** de
   `merge_real_prizes(payload, _prizes())` y verifique:
   - `clasico["retorno_real_pct"] == pytest.approx(13.79, abs=0.01)`
     (620.000.000 / 4.496.388 / 1000 — con `_loto_prices()` ya definido en el
     archivo).
   - `revancha["retorno_real_pct"] == pytest.approx(14.09, abs=0.01)`
     (190.000.000 / 4.496.388 / 300).

   Patrón a seguir: `tests/test_stats.py::test_merge_real_prices_overlays_live_loto_prices`
   (ya combina ambos merges).

**Verify**: `python -m pytest tests/test_stats.py -q` → todo pasa.

### Step 3: Verificar la UI no cambia

`grep -n "retorno_real_pct" site/app.js` → el renderizado usa
`row["retorno_real_pct"] != null ? ... : "—"`. No hay cambios que hacer; si el
excerpt difiere, detente (STOP) y reporta.

**Verify**: `python -m pytest -q` → todo pasa.

## Test plan

- Test 1 actualizado: sin precios vivos, `retorno_real_pct is None`.
- Test 2 nuevo: con precios vivos (Loto), retorno = premio/combos/precio
  (13,79% y 14,09%).
- Regresión: `merge_live_kino` sigue produciendo retornos con precio vivo
  (test existente `test_merge_live_kino_rebuilds_section_with_all_additional_games`
  con 187,78% y 72,24% — no debe cambiar).

## Done criteria

- [ ] `python -m pytest -q` exit 0 (incluye los 2 tests de este plan)
- [ ] `grep -n "Precio o apuesta (num)" polla_app/stats.py` no aparece dentro de `merge_real_prizes`
- [ ] `ruff check polla_app tests` y `black --check polla_app tests` exit 0
- [ ] `mypy polla_app` exit 0
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 002 actualizada

## STOP conditions

Detente y reporta si:

- El código de `merge_real_prizes` no coincide con el excerpt (drift).
- Alguna verificación falla dos veces tras intento razonable.
- `site/app.js` renderiza el retorno de otra forma (por ejemplo mostrando el
  valor de la hoja) — no lo "arregles" tú, reporta.

## Maintenance notes

- Si más adelante se añade un precio vivo para juegos sin fuente pública, el
  retorno aparecerá automáticamente al poblarse `precio_real_clp`.
- En CI (polla.cl bloqueado) los retornos de Loto quedarán en "—" hasta que el
  pipeline corra fuera de GitHub Actions (ver plans/README, dirección D2).
- Revisar en el PR: que `merge_live_kino` no use el fallback (debe seguir
  usando `delta`).
