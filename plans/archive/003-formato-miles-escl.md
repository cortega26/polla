# Plan 003: Formato de miles consistente es-CL en el dashboard (puntos, no comas)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/site.py tests/test_site.py site/app.js`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

El dashboard mezcla dos convenciones de separador de miles: las cadenas
generadas en Python (`pozos_millones`, `total_millones`) usan coma
(`"8,370"`), mientras que los valores formateados en JavaScript con
`Intl.NumberFormat("es-CL")` usan punto (`"14.300"`). En el mismo ticket se
ve "Kino $8,370 MM" (categorías) junto a "$14.300 MM" (total). El formato
chileno es punto como separador de miles; la inconsistencia es visible para
cualquier usuario.

## Current state

- `polla_app/site.py` — `_format_millones` (líneas 33-35). El docstring dice
  "Chilean grouping" pero el formato produce comas:

```python
def _format_millones(value: int) -> str:
    """Format CLP as 'X.XXX' (millones) with Chilean grouping."""
    return f"{value / 1_000_000:,.0f}"
```

  Uso: `_game_section` (líneas 48-49) y el historial (líneas 106-107) para
  `pozos_millones` y `total_millones`.
- `site/app.js` — `const fmtCLP = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 });`
  produce puntos (es-CL). El total del ticket y la tabla de stats pasan por
  `fmtCLP`; las categorías del ticket y la tabla de historial renderizan las
  cadenas de Python directamente.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest tests/test_site.py -q` | all pass |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/site.py` — `_format_millones`
- `tests/test_site.py` — aserciones de formato

**Out of scope**:
- `site/app.js` — no requiere cambios (ya formatea es-CL con puntos); NO lo modifiques.
- `polla_app/stats.py` — los `(num)` del stats.json son números, no strings.
- Cualquier otro formateador.

## Git workflow

- Branch: `advisor/003-formato-miles-escl`
- Un commit: `fix(site): separador de miles es-CL (punto) en los valores del dashboard`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Corregir `_format_millones`

En `polla_app/site.py`, reemplaza el cuerpo:

```python
    return f"{value / 1_000_000:,.0f}"
```

por:

```python
    return f"{value / 1_000_000:,.0f}".replace(",", ".")
```

(`f"{...:,.0f}"` agrupa con coma; el `replace` convierte a la convención
chilena de punto. Solo aplica a miles — no hay decimales porque `:.0f`.)

**Verify**: `python -m pytest tests/test_site.py -q` → el test
`test_build_site_payload_loto_and_kino` fallará en
`payload["kino"]["pozos_millones"]["Kino"] == "8,370"` (esperado, se actualiza
en el paso 2).

### Step 2: Actualizar aserciones en `tests/test_site.py`

En `test_build_site_payload_loto_and_kino` (líneas ~28-45), cambia:

```python
    assert payload["loto"]["pozos_millones"]["Loto Clásico"] == "690"
    assert payload["loto"]["total_millones"] == "790"
    assert payload["kino"]["pozos_millones"]["Kino"] == "8,370"
```

por:

```python
    assert payload["loto"]["pozos_millones"]["Loto Clásico"] == "690"
    assert payload["loto"]["total_millones"] == "790"
    assert payload["kino"]["pozos_millones"]["Kino"] == "8.370"
```

Añade un test dedicado del formato:

```python
def test_format_millones_uses_dot_thousands_separator() -> None:
    from polla_app.site import _format_millones

    assert _format_millones(8_370_000_000) == "8.370"
    assert _format_millones(14_300_000_000) == "14.300"
    assert _format_millones(690_000_000) == "690"
```

**Verify**: `python -m pytest tests/test_site.py -q` → todo pasa.

### Step 3: Verificación global

**Verify**:
- `python -m pytest -q` → todo pasa.
- `grep -n '",' polla_app/site.py` → sin coincidencias sospechosas de formato
  de miles (el `",".replace` queda, revisa manualmente que solo esté en
  `_format_millones`).
- `grep -n '"8,370"\|"14,300"' tests/ site/` → sin coincidencias.

## Test plan

- Test nuevo `test_format_millones_uses_dot_thousands_separator` (paso 2).
- Actualización del fixture de aserciones del payload.
- Regresión: `tests/test_site.py` completo pasa; el resto de la suite no toca
  estas cadenas.

## Done criteria

- [ ] `python -m pytest -q` exit 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app` exit 0
- [ ] `grep -n '"8,370"' site/ tests/` sin coincidencias
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 003 actualizada

## STOP conditions

Detente y reporta si:

- `_format_millones` no coincide con el excerpt (drift).
- `site/app.js` formatea las categorías del ticket con su propio formateador
  (en ese caso el fix va en JS, no en Python — reporta antes de tocar app.js).
- Alguna verificación falla dos veces tras intento razonable.

## Maintenance notes

- Si se añaden nuevos campos formateados en `site.py`, deben pasar por
  `_format_millones` o un helper equivalente con punto.
- La tabla de stats (`stats.json`) ya formatea en JS con es-CL; mantener así.
- Revisar en el PR: que no queden comas en ninguna cadena de `data.json`.
