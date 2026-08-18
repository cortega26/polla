# Plan 011: Adelgazar `scrapling[all]` → `scrapling[fetchers]` (eliminar extras innecesarios)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- requirements.txt pyproject.toml`
> If any in-scope file changed since this plan was written, compare the
> excerpts against the live files before proceeding; on a mismatch, treat it
> as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M
- **Risk**: MED
- **Depends on**: 009 (recomendado — tras el singleton, el único consumidor de
  scrapling es `browser.py`; se puede ejecutar antes, pero 009 simplifica la
  verificación del import surface)
- **Category**: deps
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

`requirements.txt` declara `scrapling[all]>=0.4.7` y además `playwright>=1.49.0`
por separado. El extra `[all]` de scrapling arrastra paquetes que el proyecto
no usa (p. ej. drivers de navegador alternativos/adicionales según los extras
de la versión instalada). Reducir a `scrapling>=0.4.7` (base) + `playwright`
explícito (que ya está) recorta el árbol de instalación en CI y la superficie
de supply chain. Solo es aceptable si `StealthyFetcher` y el flujo de pozos
siguen funcionando — eso se verifica en este plan antes de aceptar.

## Current state

- `requirements.txt`:

```
beautifulsoup4>=4.12.3
click>=8.1.7
requests>=2.33.1
gspread>=6.1.0
google-auth>=2.30.0
google-auth-oauthlib>=1.0.0
oauthlib>=3.2.2
requests-oauthlib>=1.3.1
scrapling[fetchers]>=0.4.7
```

  (Nota: el `requirements.txt` del repo raíz no lista `playwright` — el
  `pyproject.toml` sí: `"scrapling[all]>=0.4.7", "playwright>=1.49.0"`.)

- Uso real de scrapling en el código: `from scrapling import StealthyFetcher`
  en `polla_app/sources/pozos.py:284` (y en `prices.py`/`browser.py` tras el
  plan 009). Nada más se importa de scrapling (`grep -rn "scrapling" polla_app/`).

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Install (venv nuevo) | `python -m venv /tmp/scrapling-check && /tmp/scrapling-check/bin/pip install -r requirements.txt` | exit 0 |
| Import check | `/tmp/scrapling-check/bin/python -c "from scrapling import StealthyFetcher; print('ok')"` | imprime `ok` |
| Tests       | `.venv/bin/python -m pytest -q` | todo pasa (suite actual) |
| Lint/format/type | `ruff check polla_app tests` / `black --check polla_app tests` / `mypy polla_app` | exit 0 |

## Scope

**In scope**:
- `requirements.txt` — cambiar la línea de scrapling
- `pyproject.toml` — cambiar la entrada de dependencias
- `.github/workflows/*` — NINGUNO (solo si el paso de install fallara por algo
  relacionado; ver STOP conditions)

**Out of scope**:
- Actualizar la versión mínima de scrapling/playwright (solo cambiar el extra).
- Cualquier cambio en `polla_app/` (el plan 009 ya centraliza el import).

## Git workflow

- Branch: `advisor/011-deps-scrapling-base`
- Un commit: `build(deps): scrapling base sin extras [all]`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Cambiar la declaración

- `requirements.txt`: `scrapling[all]>=0.4.7` → `scrapling[fetchers]>=0.4.7`
- `pyproject.toml` (dependencias, ~línea 17): `"scrapling[all]>=0.4.7",` →
  `"scrapling>=0.4.7",` (mantén `"playwright>=1.49.0",` tal cual).

**Verify**: `git diff requirements.txt pyproject.toml` muestra solo esas dos líneas.

### Step 2: Verificar el import surface en un venv limpio

Crea un venv temporal y instala desde `requirements.txt`:

```bash
python -m venv /tmp/scrapling-check
/tmp/scrapling-check/bin/pip install -r requirements.txt
/tmp/scrapling-check/bin/python -c "from scrapling import StealthyFetcher; print('ok')"
```

**Verify**: install exit 0 y el import imprime `ok`. Si `StealthyFetcher` no
está disponible en el paquete base (import falla), **STOP y reporta**: la
dependencia mínima correcta puede ser `scrapling[playwright]` o similar según
la versión instalada — no improvises el extra; reporta el nombre del extra que
falte según el error.

### Step 3: Suite completa en el venv del repo

**Verify**:
- `.venv/bin/python -m pytest -q` → todo pasa.
- `ruff check polla_app tests` y `black --check polla_app tests` y
  `mypy polla_app` → exit 0.
- `make ready` → todos los hooks pasan.

### Step 4: (Opcional) Verificar una corrida real local

Si el entorno local tiene red y el navegador instalado, ejecuta
`python -m polla_app pozos` y `python -m polla_app kino` y confirma que
producen JSON con `montos` (el flujo de polla.cl con Scrapling es el camino
que ejercita `StealthyFetcher`). Si no puedes ejecutarlo, el paso 2-3 es la
puerta mínima.

## Test plan

No hay tests de Python para dependencias. La verificación es de entorno:
venv limpio + import + suite completa (pasos 2-3).

## Done criteria

- [ ] `requirements.txt` y `pyproject.toml` usan `scrapling[fetchers]>=0.4.7` (sin `[all]`)
- [ ] Venv limpio: `pip install -r requirements.txt` exit 0 y
      `from scrapling import StealthyFetcher` funciona
- [ ] `python -m pytest -q` exit 0
- [ ] Solo `requirements.txt` y `pyproject.toml` modificados (`git status`)
- [ ] `plans/README.md` fila 011 actualizada

## STOP conditions

Detente y reporta si:

- El import de `StealthyFetcher` falla con el paquete base (reporta el error
  y el extra necesario — no lo adivines).
- `pip install` falla por resolución de versiones.
- La suite falla por razones no relacionadas con el cambio (drift del repo).

## Maintenance notes

- El `pyproject.toml` es la fuente para installs editable (`pip install -e .`);
  mantenerlo sincronizado con `requirements.txt`.
- Si mañana se necesita otro componente de scrapling (p. ej.
  `AdaptiveFetcher` con otro driver), evaluar el extra mínimo en lugar de
  volver a `[all]`.
- CI instala desde `requirements.txt` (workflows) y `pip install -e .`
  (docs.yml); ambos quedan cubiertos por la verificación.
