# Plan 004: pages.yml — conservar la última data buena si la ingesta falla (sin sobrescribir con nulos)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- .github/workflows/pages.yml`
> If this file changed since this plan was written, compare the excerpts
> against the live file before proceeding; on a mismatch, treat it as a STOP
> condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW-MED
- **Depends on**: none
- **Category**: bug (availability)
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

El workflow `pages.yml` ingiere pozos con `continue-on-error: true` y luego
ejecuta `polla site` **incondicionalmente**. Si las dos ingestas fallan (una
fuente caída, robots bloqueando, red caída), `polla site` escribe un
`site/data.json` con `loto: null` y `kino: null`, y el deploy reemplaza la
página buena anterior por un dashboard vacío ("—" por todos lados). El
comportamiento correcto: si no hay datos nuevos, conservar la última data
buena generada.

## Current state

`.github/workflows/pages.yml` (tramos verificados):

- Ingesta Loto (líneas ~40-56): `continue-on-error: true` y termina con
  `|| echo "::warning::Loto ingest failed; dashboard will show last known data"`.
- Ingesta Kino (líneas ~59-75): idéntico patrón.
- Generación (líneas ~77-84):

```yaml
      - name: Generate dashboard data
        run: |
          python -m polla_app site \
            --normalized artifacts/normalized.jsonl \
            --normalized-kino artifacts_kino/normalized.jsonl \
            --summary artifacts/run_summary.json \
            --output site/data.json
```

- Subida (líneas ~86-91): `actions/upload-pages-artifact@v3` con `path: site`
  — el artifact reemplaza el deploy anterior completo.

Nota: `polla_app/site.py::_load_ndjson` devuelve `[]` si el archivo no existe;
`build_site_payload` produce secciones `None` y el `site` step termina con
exit 0. No hay señal de fallo → el dashboard se "vacía" silenciosamente.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Validar YAML | `python -c "import yaml; yaml.safe_load(open('.github/workflows/pages.yml'))"` | exit 0 (si pyyaml está instalado; si no, usa `actionlint` o el parser del editor) |
| Tests     | `python -m pytest -q`    | todo pasa (sin cambios de código Python en este plan) |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `.github/workflows/pages.yml` — steps de ingesta, generación y caché de datos del sitio

**Out of scope**:
- `polla_app/site.py` — el comando CLI no cambia (el guard se hace en el workflow).
- `scrape.yml`, `update.yml` — otros workflows, no tocar.
- El sitio ya desplegado (el caché lo resuelve a partir de la próxima corrida).

## Git workflow

- Branch: `advisor/004-pages-last-good-data`
- Un commit: `ci(pages): conservar la última data del dashboard si la ingesta falla`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Restaurar el caché de datos del sitio antes de la generación

Inmediatamente después del step "Install dependencies" (que ya instala
`playwright install chromium`), añade un restore del caché de los datos
generados del sitio:

```yaml
      - name: Restore last dashboard data
        id: restore-site-data
        uses: actions/cache/restore@v5
        with:
          path: |
            site/data.json
            site/stats.json
          key: site-data-${{ github.ref_name }}-${{ github.run_number }}
          restore-keys: |
            site-data-${{ github.ref_name }}-
```

(Patrón idéntico al restore de `pipeline_state` que ya existe en este mismo
workflow para la ingesta.)

### Step 2: Generar solo si hay datos nuevos

Reemplaza el step "Generate dashboard data" por:

```yaml
      - name: Generate dashboard data
        run: |
          if [ -s artifacts/normalized.jsonl ] || [ -s artifacts_kino/normalized.jsonl ]; then
            python -m polla_app site \
              --normalized artifacts/normalized.jsonl \
              --normalized-kino artifacts_kino/normalized.jsonl \
              --summary artifacts/run_summary.json \
              --output site/data.json
          else
            echo "::warning::Ingestas fallidas; se conserva la última data del dashboard"
          fi
```

Con esto, si no hay records nuevos, `site/data.json` y `site/stats.json`
restaurados en el paso 1 quedan intactos y se suben tal cual.

### Step 3: Guardar el caché tras la generación

Justo después del step "Generate dashboard data" (y antes de "Configure
Pages"), añade:

```yaml
      - name: Save dashboard data
        uses: actions/cache/save@v5
        if: always()
        with:
          path: |
            site/data.json
            site/stats.json
          key: site-data-${{ github.ref_name }}-${{ github.run_number }}
```

Nota: en la primera corrida (sin caché previo y con ingesta exitosa) el save
crea la clave; en corridas posteriores el restore la reutiliza vía
`restore-keys` y el save actualiza. El patrón ya se usa en este repo
(`scrape.yml` con `pipeline_state`).

**Verify (pasos 1-3 juntos)**:
- `python -m pytest -q` → todo pasa (no debe haber cambios de código Python).
- Revisión visual del YAML: los tres steps nuevos respetan la indentación de 6
  espacios de los steps existentes. Si `pyyaml` está disponible:
  `python -c "import yaml; yaml.safe_load(open('.github/workflows/pages.yml')); print('yaml ok')"`.

### Step 4: Verificación end-to-end (opcional pero recomendada)

Si el operador lo autoriza, dispara el workflow manualmente dos veces:
`gh workflow run pages.yml --ref <branch>`. Esperado: la primera genera y
cachéa; la segunda, si la ingesta fallara, conserva la data de la primera.
(No bloquees la finalización del plan si no puedes ejecutar GitHub Actions;
la verificación local del YAML + tests es la puerta mínima.)

## Test plan

No hay tests de Python para un cambio de workflow. La verificación es:
- `git diff` del workflow correctamente indentado.
- Opcional: simular localmente la rama de fallo ejecutando
  `polla site --normalized /no/existe --normalized-kino /no/existe --output /tmp/data.json`
  y confirmar que el dashboard resultante es el de "datos no disponibles"
  (comportamiento actual, solo para entender el caso que el guard evita).

## Done criteria

- [ ] `.github/workflows/pages.yml` contiene los 3 steps nuevos (restore,
      guard condicional, save) con el formato exacto del plan
- [ ] `python -m pytest -q` exit 0 (sin cambios fuera del workflow)
- [ ] YAML válido (parser o revisión manual)
- [ ] Solo `.github/workflows/pages.yml` modificado (`git status`)
- [ ] `plans/README.md` fila 004 actualizada

## STOP conditions

Detente y reporta si:

- El workflow difiere del excerpt (drift).
- `polla site` cambia su firma o comportamiento entre ahora y la ejecución.
- El caché de `pipeline_state` en `scrape.yml` usa un patrón incompatible con
  lo copiado aquí (compara antes de copiar; si difiere, usa el patrón real del
  repo y anótalo en el reporte).

## Maintenance notes

- La clave de caché es por `github.ref_name` + `run_number`; si un día se
  quiere retención indefinida, añadir `save-always: true` al save.
- Si se añaden más juegos, añadir sus `normalized` a la condición `[ -s ... ]`
  y sus archivos generados al path del caché.
- Revisar en el PR: que el guard no impida la generación cuando solo uno de
  los juegos tiene datos nuevos (la condición es OR, correcto).
