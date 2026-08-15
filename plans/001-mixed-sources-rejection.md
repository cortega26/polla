# Plan 001: Rechazar runs mixtos `pozos,kino` con un error accionable (categorías de otro juego con sorteo/fecha equivocados)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/pipeline.py tests/test_phase3_hardening.py AGENTS.md README.md docs/API.md`
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

`run_pipeline(sources=["pozos", "kino"])` (o `["all"]`) produce un **único
record** cuyas categorías mezclan Loto y Kino pero con `sorteo`/`fecha` del
primer juego recolectado (Loto). Consecuencias:

- `publish` escribe las filas de Kino en la hoja con el número de sorteo y la
  fecha de Loto (datos incorrectos silenciosamente).
- `site.py` muestra las categorías de Kino dentro de la sección Loto del
  dashboard (duplicadas respecto a la sección Kino).

CI ya ejecuta Loto y Kino como invocaciones separadas con hojas separadas; el
modo combinado solo aporta datos corruptos. La solución de menor riesgo es
rechazar el modo combinado con un mensaje que indique cómo ejecutarlo bien.

## Current state

- `polla_app/pipeline.py` — `_normalize_sources` (líneas 36-52) es el único
  punto de entrada que decide qué fuentes se recolectan:

```python
def _normalize_sources(requested: Sequence[str]) -> list[str]:
    lowered = {item.lower() for item in requested}
    if "all" in lowered or ("pozos" in lowered and "kino" in lowered):
        return ["pozos", "kino"]
    if "pozos" in lowered:
        # "pozos" is the Loto aggregate; it absorbs redundant per-source requests
        return ["pozos"]

    normalised: list[str] = []
    for item in requested:
        key = item.lower()
        if key not in SOURCE_LOADERS:
            raise ValueError(f"Unsupported source '{item}'. Available: {', '.join(SOURCE_LOADERS)}")
        if key not in normalised:
            normalised.append(key)
    return normalised
```

- El record único se construye en `_run_ingestion_for_sources`
  (`pipeline.py:501-521`): `primary = collected[0]`, luego
  `sorteo = primary.get("sorteo")`, `fecha = primary.get("fecha")`, y
  `"pozos_proximo": merged_pozos` (montos de ambos juegos).
- `tests/test_phase3_hardening.py:73-89` (`test_normalize_sources_deduplication`)
  fija el comportamiento actual con `["all"] == ["pozos", "kino"]` y
  `["pozos", "kino"] -> ["pozos", "kino"]`.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Lint      | `ruff check polla_app tests` | exit 0, no output  |
| Format    | `black --check polla_app tests` | exit 0            |
| Typecheck | `mypy polla_app`         | "Success: no issues found in N source files" |
| Tests     | `python -m pytest -q`    | all pass (N passed) |
| Full gate | `make ready`             | all hooks pass     |

(Ajusta `python`/`mypy` al intérprete del entorno; el repo usa `.venv/bin/python`.)

## Scope

**In scope** (los únicos archivos que debes modificar):
- `polla_app/pipeline.py` — `_normalize_sources`
- `tests/test_phase3_hardening.py` — actualizar el test de normalización
- `tests/test_pipeline.py` — añadir tests de rechazo
- `AGENTS.md`, `README.md`, `docs/API.md` — textos que documentan `all`/`pozos,kino`

**Out of scope** (NO tocar, aunque parezcan relacionados):
- `polla_app/site.py`, `polla_app/publish.py` — el fix es preventivo; no se
  cambia cómo se publican records (CI ya separa por juego).
- La lógica de recolección en `_run_ingestion_for_sources` — solo cambia
  `_normalize_sources`.
- `.github/workflows/*` — CI ya invoca los juegos por separado.

## Git workflow

- Branch: `advisor/001-mixed-sources-rejection`
- Un commit; mensaje estilo conventional commits en español, como el historial
  reciente (ej. `fix(pipeline): rechazar runs mixtos pozos,kino — sorteo/fecha por juego`).
- NO hacer push ni abrir PR salvo que el operador lo indique.

## Steps

### Step 1: Rechazar el modo combinado en `_normalize_sources`

En `polla_app/pipeline.py`, reemplaza el bloque:

```python
    if "all" in lowered or ("pozos" in lowered and "kino" in lowered):
        return ["pozos", "kino"]
```

por:

```python
    if "all" in lowered or ("pozos" in lowered and "kino" in lowered):
        raise ValueError(
            "Mixing 'pozos' and 'kino' in one run is not supported: each game "
            "must run as a separate invocation (--sources pozos, then --sources kino) "
            "so sorteo/fecha and sheets stay per game"
        )
```

Mantén el resto de la función intacto (`"pozos"` solo sigue absorbiendo
`openloto`/`polla`; las fuentes individuales siguen validándose contra
`SOURCE_LOADERS`).

**Verify**: `python -m pytest tests/test_phase3_hardening.py -q` → el test
`test_normalize_sources_deduplication` fallará (esperado, se arregla en el
siguiente paso).

### Step 2: Actualizar `tests/test_phase3_hardening.py`

En `test_normalize_sources_deduplication` (líneas 73-89), reemplaza las
aserciones:

```python
    # "all" expands to both games; "pozos" collapses to the Loto aggregate
    assert _normalize_sources(["all"]) == ["pozos", "kino"]
```

y

```python
    assert _normalize_sources(["all", "openloto"]) == ["pozos", "kino"]
```

por aserciones de rechazo:

```python
    with pytest.raises(ValueError, match="separate invocation"):
        _normalize_sources(["all"])
    with pytest.raises(ValueError, match="separate invocation"):
        _normalize_sources(["pozos", "kino"])
    with pytest.raises(ValueError, match="separate invocation"):
        _normalize_sources(["all", "openloto"])
```

Añade además en el mismo test (o en uno nuevo `test_mixed_sources_rejected` en
`tests/test_pipeline.py`) la verificación vía pipeline:

```python
def test_mixed_sources_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="separate invocation"):
        run_pipeline(
            sources=["pozos", "kino"],
            source_overrides={},
            raw_dir=tmp_path / "raw",
            normalized_path=tmp_path / "normalized.jsonl",
            comparison_report_path=tmp_path / "comparison.json",
            summary_path=tmp_path / "summary.json",
            state_path=tmp_path / "state.jsonl",
            log_path=tmp_path / "run.jsonl",
            retries=1,
            timeout=5,
            fail_fast=False,
            mismatch_threshold=0.5,
            include_pozos=True,
        )
```

Patrón a seguir: `tests/test_pipeline.py::test_pipeline_unsupported_source_raises_error`
(usa el mismo set de argumentos de `run_pipeline`).

**Verify**: `python -m pytest tests/test_phase3_hardening.py tests/test_pipeline.py -q` → todo pasa.

### Step 3: Actualizar la documentación de fuentes

- `AGENTS.md` sección `## CLI` — el texto actual dice
  "`run`: pozos (Loto) and/or kino ingestion (`--sources pozos|kino|pozos,kino|all`)".
  Cámbialo a: "`run`: ingestion per game — `--sources pozos` (Loto) o
  `--sources kino`; mezclar ambos en una invocación se rechaza (ejecuta dos
  invocaciones separadas)".
- `README.md` — busca menciones de `all` o `pozos,kino` en la sección de
  inicio rápido/arquitectura y elimínalas o reemplázalas por las dos
  invocaciones separadas (ya documentadas como pasos 2 y 3).
- `docs/API.md` — la fila de `sources` dice
  "List of sources to ingest: `"pozos"`, `"polla"`, `"openloto"`, `"kino"` or `"all"` (Loto + Kino)".
  Reemplaza `or "all" (Loto + Kino)` por `— use one game per invocation`.

**Verify**: `grep -rn "pozos,kino\|Loto + Kino\|\"all\"" AGENTS.md README.md docs/` → sin
coincidencias (o solo las nuevas advertencias de rechazo).

## Test plan

- Tests nuevos/actualizados (paso 2): rechazo de `["all"]`, `["pozos","kino"]`,
  `["all","openloto"]` en `_normalize_sources`; y rechazo end-to-end vía
  `run_pipeline(sources=["pozos","kino"])`.
- Caso de regresión que NO debe romperse: `_normalize_sources(["pozos"])` sigue
  devolviendo `["pozos"]` y `["openloto"]` → `["openloto"]` (aserciones ya
  presentes en `test_normalize_sources_deduplication`).
- `python -m pytest -q` → todo pasa (espera ~N passed, sin skips nuevos).

## Done criteria

- [ ] `ruff check polla_app tests` exit 0
- [ ] `black --check polla_app tests` exit 0
- [ ] `mypy polla_app` exit 0
- [ ] `python -m pytest -q` exit 0, con los tests de rechazo presentes
- [ ] `grep -rn "pozos,kino" AGENTS.md README.md docs/` no devuelve referencias obsoletas
- [ ] No hay archivos fuera del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 001 actualizada

## STOP conditions

Detente y reporta (no improvises) si:

- El código de `_normalize_sources` no coincide con el excerpt (drift).
- Alguna verificación falla dos veces tras un intento razonable de arreglo.
- El fix parece requerir tocar un archivo fuera del Scope.
- Descubres que algún consumidor real (CI, scripts, docs de terceros) depende
  de `--sources all`/`pozos,kino` y se rompería — reporta el consumidor.

## Maintenance notes

- Si en el futuro se implementan records por juego (uno por `sorteo`/`fecha`),
  este rechazo puede eliminarse: busca el mensaje "separate invocation" para
  localizar todos los puntos.
- El `docs/GAMES.md` menciona el pipeline por juego; no requiere cambios.
- Revisar en el PR: que el mensaje de error sea claro para un usuario de CLI
  (aparece como `ValueError` en `run_pipeline` y como excepción de Click).
