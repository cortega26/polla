# Plan 008: verify-secret.yml — dejar de imprimir caracteres del secreto en los logs

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- .github/workflows/verify-secret.yml`
> If this file changed since this plan was written, compare the excerpts
> against the live file before proceeding; on a mismatch, treat it as a STOP
> condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

El workflow `verify-secret.yml` (disparado manualmente) imprime en los logs
públicos del run la longitud del secreto de la service account de Google y su
primer y último carácter:

```bash
echo "Secret length: ${#GOOGLE_SHEETS_CREDENTIALS}"
echo "First character: ${GOOGLE_SHEETS_CREDENTIALS:0:1}"
echo "Last character: ${GOOGLE_SHEETS_CREDENTIALS: -1}"
```

Eso filtra 2 caracteres + longitud del JSON de credenciales a los logs del
workflow. Un secreto comprometido debe rotarse (la rotación ya está
documentada en el AGENTS del repo: "Do not leak secrets"). El fix es mínimo:
validar presencia y forma JSON sin imprimir ningún fragmento del valor.

## Current state

`.github/workflows/verify-secret.yml` — step "Verify GOOGLE_SHEETS_CREDENTIALS":

```yaml
      - name: Verify GOOGLE_SHEETS_CREDENTIALS
        run: |
          if [ -n "$GOOGLE_SHEETS_CREDENTIALS" ]; then
            echo "Secret exists and is not empty"
            echo "Secret length: ${#GOOGLE_SHEETS_CREDENTIALS}"
            echo "First character: ${GOOGLE_SHEETS_CREDENTIALS:0:1}"
            echo "Last character: ${GOOGLE_SHEETS_CREDENTIALS: -1}"
            if [[ ${GOOGLE_SHEETS_CREDENTIALS:0:1} == "{" && ${GOOGLE_SHEETS_CREDENTIALS: -1} == "}" ]]; then
              echo "✅ Secret appears to be valid JSON"
            else
              echo "❌ Secret does not appear to be valid JSON"
            fi
          else
            echo "❌ Secret is empty"
          fi
        env:
          GOOGLE_SHEETS_CREDENTIALS: ${{ secrets.GOOGLE_SHEETS_CREDENTIALS }}
```

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Validar shell | `bash -n .github/workflows/verify-secret.yml` no aplica (es YAML); valida con un extracto en un script temporal | exit 0 |
| Tests     | `python -m pytest -q`    | todo pasa (sin cambios de código Python) |

## Scope

**In scope**:
- `.github/workflows/verify-secret.yml` — solo el step de credenciales

**Out of scope**:
- Los steps de `GOOGLE_SPREADSHEET_ID` y `CODECOV_TOKEN` — ya solo imprimen
  presencia/longitud; la longitud de un ID/token corto también es información
  menor, pero se dejan como están (no empeoran).
- GitHub Settings / rotación de secretos — acción manual del operador (si el
  secreto ya está comprometido, rotarlo; este plan solo evita futuras fugas).

## Git workflow

- Branch: `advisor/008-verify-secret-no-leak`
- Un commit: `ci(security): no imprimir fragmentos del secreto en verify-secret`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Quitar las líneas que imprimen el valor

En `.github/workflows/verify-secret.yml`, reemplaza el bloque del step por:

```yaml
      - name: Verify GOOGLE_SHEETS_CREDENTIALS
        run: |
          if [ -n "$GOOGLE_SHEETS_CREDENTIALS" ]; then
            echo "Secret exists and is not empty"
            if [[ ${GOOGLE_SHEETS_CREDENTIALS:0:1} == "{" && ${GOOGLE_SHEETS_CREDENTIALS: -1} == "}" ]]; then
              echo "✅ Secret appears to be valid JSON"
            else
              echo "❌ Secret does not appear to be valid JSON"
            fi
          else
            echo "❌ Secret is empty"
          fi
        env:
          GOOGLE_SHEETS_CREDENTIALS: ${{ secrets.GOOGLE_SHEETS_CREDENTIALS }}
```

(Cambios: se eliminan las dos líneas `echo "Secret length..."` y
`echo "First character..."` y `echo "Last character..."`. La validación JSON
sigue usando los substrings sin imprimirlos.)

**Verify**: revisa el diff — `grep -n "First character\|Last character\|Secret length" .github/workflows/verify-secret.yml`
→ sin coincidencias. `python -m pytest -q` → todo pasa.

### Step 2: Verificación local del script

Extrae el bloque `run:` a un script temporal y valida sintaxis y
comportamiento con una variable simulada:

```bash
GOOGLE_SHEETS_CREDENTIALS='{"type":"service_account"}' bash -c '
if [ -n "$GOOGLE_SHEETS_CREDENTIALS" ]; then
  echo "Secret exists and is not empty"
  if [[ ${GOOGLE_SHEETS_CREDENTIALS:0:1} == "{" && ${GOOGLE_SHEETS_CREDENTIALS: -1} == "}" ]]; then
    echo "✅ Secret appears to be valid JSON"
  else
    echo "❌ Secret does not appear to be valid JSON"
  fi
else
  echo "❌ Secret is empty"
fi'
```

**Verify**: salida esperada (sin ningún carácter del valor impreso):

```
Secret exists and is not empty
✅ Secret appears to be valid JSON
```

## Test plan

No hay tests de Python. Verificación: pasos 1-2 + revisión del diff.

## Done criteria

- [ ] `grep -n "First character\|Last character\|Secret length" .github/workflows/verify-secret.yml` sin coincidencias
- [ ] La validación JSON del step sigue presente
- [ ] `python -m pytest -q` exit 0
- [ ] Solo `.github/workflows/verify-secret.yml` modificado (`git status`)
- [ ] `plans/README.md` fila 008 actualizada

## STOP conditions

Detente y reporta si:

- El step difiere del excerpt (drift).
- Descubres otros prints de secretos en workflows (reporta la ubicación, no el
  valor; no los arregles en este plan).

## Maintenance notes

- Los logs de GitHub Actions retienen los runs; si este workflow se ejecutó en
  el pasado, los fragmentos ya están en el historial — la rotación del secreto
  queda a criterio del operador.
- Si se añaden más secretos a verificar, el patrón correcto es presencia +
  validación de forma, nunca substrings impresos.
