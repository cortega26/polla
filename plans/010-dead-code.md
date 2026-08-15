# Plan 010: Eliminar código muerto (`ErrorMetric`, `validate_fecha_is_past`, campo `precio_estatico`)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/exceptions.py polla_app/validation.py polla_app/stats.py tests/test_validation.py tests/test_stats.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 002 (ambos tocan `stats.py`; 002 cambia `merge_real_prizes`,
  010 toca `merge_real_prices` — ejecutar 002 primero evita conflictos)
- **Category**: tech-debt
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

Tres símbolos muertos confunden a quien lea el código por primera vez:

- `ErrorMetric` (`exceptions.py:96-99`): dataclass sin ningún caller.
- `validate_fecha_is_past` (`validation.py:93-96`): función sin callers,
  exportada en `__all__`.
- `precio_estatico` (`stats.py:219,223`): campo escrito por
  `merge_real_prices` que la UI ya no lee (se eliminó el marcado "(ref)").

Quitarlos reduce la superficie de mantenimiento y evita que el siguiente
editor asuma que son parte del contrato.

## Current state

- `polla_app/exceptions.py:96-99` (final del archivo):

```python
@dataclass(frozen=True)
class ErrorMetric:
    code: str
    count: int = 1
```

- `polla_app/validation.py:93-96`:

```python
def validate_fecha_is_past(fecha: str, *, today: date | None = None) -> bool:
    """Return True when ``fecha`` (ISO) is today or in the past."""
    parsed = datetime.fromisoformat(fecha).date()
    return parsed <= (today or date.today())
```

  y su export en `__all__` (línea 108: `"validate_fecha_is_past",`).
  Nota: tras eliminar la función, revisa si `datetime` sigue usándose en el
  archivo (sí: `_fecha_issues` usa `datetime.fromisoformat`) — el import queda.

- `polla_app/stats.py` — `merge_real_prices`, rama con datos vivos
  (líneas ~216-224):

```python
            if scraped:
                row["precio_real_clp"] = scraped.get("delta_clp")
                row["precio_acumulado_clp"] = scraped.get("acumulado_clp")
                row["precio_estatico"] = False
            else:
                row["precio_real_clp"] = None
                row["precio_acumulado_clp"] = None
                row["precio_estatico"] = True
```

- Test que referencia el campo: `tests/test_stats.py`
  (`test_merge_real_prices_marks_unmapped_games_as_static`, líneas ~202-211)
  aserta `exacta["precio_estatico"] is True`.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest tests/test_validation.py tests/test_stats.py -q` | all pass |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/exceptions.py` — eliminar `ErrorMetric` (+ su import `dataclass`
  si queda sin uso — verifica: `dataclass` solo se usa ahí)
- `polla_app/validation.py` — eliminar `validate_fecha_is_past` y su entrada
  en `__all__`
- `polla_app/stats.py` — eliminar las 2 líneas `precio_estatico`
- `tests/test_validation.py` — eliminar `test_validate_fecha_is_past`
- `tests/test_stats.py` — actualizar la aserción de `precio_estatico`

**Out of scope**:
- Cualquier otro símbolo; si encuentras más código muerto, repórtalo, no lo elimines.
- Cambiar comportamiento de `merge_real_prices` (solo quitar el campo).

## Git workflow

- Branch: `advisor/010-dead-code`
- Un commit: `refactor: eliminar código muerto (ErrorMetric, validate_fecha_is_past, precio_estatico)`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Eliminar `ErrorMetric`

En `polla_app/exceptions.py`, borra el bloque final (líneas 96-99). Luego
verifica el import `from dataclasses import dataclass` (línea 7): si
`dataclass` ya no se usa en el archivo, elimina la línea del import.
(`grep -n "dataclass" polla_app/exceptions.py` → si no queda uso, quita el import.)

**Verify**: `ruff check polla_app/exceptions.py` → exit 0 (F401 si el import
quedara sin uso; F821 si algo lo usara — en ese caso detente y reporta).

### Step 2: Eliminar `validate_fecha_is_past`

En `polla_app/validation.py`:
1. Borra la función (líneas 93-96).
2. Borra `"validate_fecha_is_past",` de `__all__` (línea 108).
3. Verifica que `date` (import de `datetime`) siga usándose:
   `grep -n "date" polla_app/validation.py` → `_fecha_issues` usa
   `datetime.fromisoformat` y `validate_pozo_payload` no usa `date`;
   revisa si `date` queda huérfano (`from datetime import date, datetime`) y
   ajusta el import a solo `datetime` si aplica.

**Verify**: `python -m pytest tests/test_validation.py -q` → el test
`test_validate_fecha_is_past` fallará (esperado; se elimina en el paso 4).
`ruff check polla_app/validation.py` → exit 0.

### Step 3: Eliminar `precio_estatico` en `stats.py`

En `polla_app/stats.py`, `merge_real_prices`, deja:

```python
            if scraped:
                row["precio_real_clp"] = scraped.get("delta_clp")
                row["precio_acumulado_clp"] = scraped.get("acumulado_clp")
            else:
                row["precio_real_clp"] = None
                row["precio_acumulado_clp"] = None
```

**Verify**: `python -m pytest tests/test_stats.py -q` →
`test_merge_real_prices_marks_unmapped_games_as_static` fallará (esperado, se
actualiza en el paso 4).

### Step 4: Actualizar los tests

- `tests/test_validation.py`: elimina `test_validate_fecha_is_past`.
- `tests/test_stats.py`, `test_merge_real_prices_marks_unmapped_games_as_static`:
  elimina la línea `assert exacta["precio_estatico"] is True` (deja las
  aserciones de `precio_real_clp is None` y la presencia de
  `"Precio o apuesta"`).

**Verify**: `python -m pytest tests/test_validation.py tests/test_stats.py -q` → todo pasa.

### Step 5: Regresión global

**Verify**: `python -m pytest -q` → todo pasa; `make ready` → todos los hooks pasan.

## Test plan

- Eliminación de tests que solo existían para el código muerto.
- Regresión: `test_stats.py` y `test_validation.py` completos pasan.

## Done criteria

- [ ] `python -m pytest -q` exit 0
- [ ] `grep -rn "ErrorMetric\|validate_fecha_is_past\|precio_estatico" polla_app/ tests/` sin coincidencias
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app` exit 0
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 010 actualizada

## STOP conditions

Detente y reporta si:

- Algún símbolo eliminado resulta estar referenciado en un lugar no previsto
  (F821 de ruff/mypy) — restaura y reporta la referencia.
- `date` o `dataclass` siguen usándose y el ajuste de import rompe algo.
- Alguna verificación falla dos veces tras intento razonable.

## Maintenance notes

- `__all__` de `validation.py` es el contrato público del módulo; al añadir
  funciones nuevas en el futuro, mantener `__all__` sincronizado.
- Si alguien reintroduce "precios de referencia", el campo debe llamarse de
  otra forma y con un consumidor real en la UI.
