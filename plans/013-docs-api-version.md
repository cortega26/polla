# Plan 013: Corregir versiones de API en la documentación (`docs/VERSIONING.md` dice v1, el código dice v1.2)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- docs/VERSIONING.md docs/API.md README.md`
> If any in-scope file changed since this plan was written, compare the
> excerpts against the live files before proceeding; on a mismatch, treat it
> as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 001 (README/AGENTS/API.md se tocan en ambos; 001 primero)
- **Category**: docs
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

`docs/VERSIONING.md` documenta el contrato de artefactos con
"`api_version` (currently `v1`)" pero el código emite `v1.2`
(`polla_app/contracts.py:6`). Un lector que dependa de la política de
versionado concluirá lo incorrecto sobre compatibilidad. El doc además no
menciona que desde `v1` se añadieron campos aditivos (por ejemplo `precios`
en el record y `current_prizes_clp`/`current_prices` en el payload del sitio).

## Current state

- `polla_app/contracts.py:6`:

```python
API_VERSION = "v1.2"
```

- `docs/VERSIONING.md`, sección "## API Version" (líneas ~8-12):

```markdown
## API Version

Artifacts and results include an `api_version` field (currently `v1`). Changes within `v1` are additive and backward‑compatible. Removals or breaking changes require a new API version (e.g., `v2`).
```

- `docs/API.md` y `README.md` mencionan `api_version` de forma correcta
  (README no dice la versión; API.md tampoco) — verifica con grep.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Doctests  | `python -m pytest --doctest-glob='*.md' README.md docs -q` | exit 0 o 5 (sin doctests) |
| Tests     | `python -m pytest -q`    | todo pasa |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `docs/VERSIONING.md` — actualizar la sección API Version
- (solo si el grep lo encuentra) otras menciones obsoletas de `v1` en `docs/`

**Out of scope**:
- Cambiar `API_VERSION` en el código.
- `docs/DATA-STORE.md`, `docs/GAMES.md`, `docs/SLOs.md` (sin referencias de versión).
- `CHANGELOG.md` — se actualiza en releases, no aquí.

## Git workflow

- Branch: `advisor/013-docs-api-version`
- Un commit: `docs(versioning): api_version actual (v1.2) y política de campos aditivos`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Verificar referencias obsoletas

```bash
grep -rn "api_version\|currently \`v1\`" docs/ README.md
```

**Verify**: localiza todas las menciones de la versión en docs; al menos
`docs/VERSIONING.md:9` dice `currently \`v1\``.

### Step 2: Actualizar `docs/VERSIONING.md`

Reemplaza la sección:

```markdown
## API Version

Artifacts and results include an `api_version` field (currently `v1`). Changes within `v1` are additive and backward‑compatible. Removals or breaking changes require a new API version (e.g., `v2`).
```

por:

```markdown
## API Version

Artifacts and results include an `api_version` field (currently `v1.2`, defined
in `polla_app/contracts.py`). Changes within `v1.x` are additive and backward‑
compatible: new fields may be added (e.g. `precios` in normalized records,
`current_prizes_clp` / `current_prices` in the dashboard payload). Removals or
breaking changes require a new API version (e.g., `v2`).

When adding fields to artifacts, update `tests/test_contracts.py` to lock the
new schema (see AGENTS.md, "Contracts").
```

**Verify**: `grep -n "v1.2" docs/VERSIONING.md` → presente.

### Step 3: Sincronizar cualquier otra mención

Si el grep del paso 1 encontró otras menciones de `v1` como versión *actual*
en `docs/` o `README.md`, actualízalas a `v1.2` o elimínalas (decisión por
contexto: si es la versión actual del artefacto → `v1.2`; si es un ejemplo
genérico de "v2" → déjalo).

**Verify**: `grep -rn "currently \`v1\`" docs/ README.md` → sin coincidencias.

### Step 4: Verificación final

**Verify**:
- `python -m pytest --doctest-glob='*.md' README.md docs -q` → exit 0 o 5
  (sin doctests, igual que antes del cambio).
- `python -m pytest -q` → todo pasa.
- `make ready` → todos los hooks pasan.

## Test plan

Sin tests de código. Verificación: greps + doctests (pasos 1-4).

## Done criteria

- [ ] `docs/VERSIONING.md` menciona `v1.2` y la política de campos aditivos
- [ ] `grep -rn "currently \`v1\`" docs/ README.md` sin coincidencias
- [ ] `python -m pytest -q` exit 0
- [ ] Solo archivos de docs modificados (`git status`)
- [ ] `plans/README.md` fila 013 actualizada

## STOP conditions

Detente y reporta si:

- `API_VERSION` ya no es `v1.2` (drift — el plan deja de ser correcto tal cual).
- El grep encuentra una doc con la versión correcta pero el texto difiere
  (compara y ajusta solo el texto del paso 2, no improvises otros cambios).

## Maintenance notes

- `API_VERSION` solo debe cambiarse desde `contracts.py`; este doc es el
  espejo. Si se bump a `v2` en el futuro, actualizar aquí también.
- `tests/test_contracts.py` es el lock del schema; al añadir campos nuevos,
  extenderlo (ya cubierto por AGENTS.md).
