# Plan 006: Publicación a Google Sheets sin ventana de hoja vacía (una sola escritura)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/publish.py tests/test_publish.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

`_update_canonical_worksheet` ejecuta `ws.clear()` y después `ws.update()`:
dos llamadas a la API de Google. Si la segunda falla (timeout, red, cuota), la
hoja canónica queda **vacía** hasta la próxima corrida — datos visibles
perdidos. El lock anti-concurrencia (ya implementado) evita publishes
paralelos pero no esta falla parcial. La alternativa: una sola escritura que
sobrescriba el rango completo (incluyendo el sobrante anterior) en una
llamada `values_update`, previa lectura del tamaño actual.

## Current state

- `polla_app/publish.py` — `_update_canonical_worksheet` (líneas ~161-171):

```python
def _update_canonical_worksheet(
    spreadsheet: Any, worksheet_name: str, rows: list[list[Any]]
) -> int:
    """Write canonical rows and return the number of updated rows."""
    if not rows:
        return 0
    header = _canonical_rows_header(rows)
    ws = _get_or_create_worksheet(spreadsheet, worksheet_name)
    ws.clear()
    ws.update([header] + rows)
    return len(rows)
```

- La llamada ocurre dentro del `with _PublishLock():` en
  `publish_to_google_sheets` (~líneas 296-306).
- Los tests faken la hoja con `MagicMock`; el patrón está en
  `tests/test_publish.py::test_discrepancy_sheet_written_on_allow_quarantine`
  (stub de credenciales + `client.open_by_key(...)` mockeado) y en los tests
  dry-run. Ver también `tests/test_publish.py::test_publish_pozos_only`
  (líneas ~140-172) que verifica filas de 4 columnas.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest tests/test_publish.py -q` | all pass |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/publish.py` — `_update_canonical_worksheet` (y helpers mínimos)
- `tests/test_publish.py` — tests nuevos del flujo de escritura

**Out of scope**:
- `_update_discrepancy_sheet` (tab de discrepancias) — mismo riesgo pero menor
  impacto; no cambiar en este plan.
- El lock `_PublishLock` — ya implementado, no tocar.
- El flujo dry-run y de decisión (`_parse_publish_decision`).

## Git workflow

- Branch: `advisor/006-publish-atomic`
- Un commit: `fix(publish): escritura canónica en una sola llamada — sin hoja vacía intermedia`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Reescribir `_update_canonical_worksheet`

Reemplaza la función por una versión que: (1) lea las filas actuales, (2)
escriba `[header] + rows` rellenado con celdas vacías hasta cubrir el tamaño
anterior (para borrar el sobrante), en **una** llamada `values_update`:

```python
def _update_canonical_worksheet(
    spreadsheet: Any, worksheet_name: str, rows: list[list[Any]]
) -> int:
    """Write canonical rows atomically and return the number of updated rows.

    A single ``values_update`` overwrites the full range, padding blank rows
    when the dataset shrank, so the sheet never goes empty mid-publish.
    """
    if not rows:
        return 0
    header = _canonical_rows_header(rows)
    ws = _get_or_create_worksheet(spreadsheet, worksheet_name)
    try:
        current = ws.get_all_values()
    except Exception:  # noqa: BLE001 - treat read failure as empty; write still proceeds
        current = []
    payload = [header] + rows
    if len(current) > len(payload):
        payload += [[] for _ in range(len(current) - len(payload))]
    ws.update(payload)
    return len(rows)
```

Notas:
- `ws.update(values)` de gspread ya es una sola llamada
  `spreadsheets.values.update` sobre el rango implícito; las filas vacías
  rellenadas borran el contenido previo sobrante.
- El `except` de la lectura: si no se puede leer el estado actual, se escribe
  igual (sin padding) — la escritura sigue siendo una sola llamada.
- Mantén el docstring original actualizado y el `return len(rows)`.

**Verify**: `python -m pytest tests/test_publish.py -q` → los tests dry-run
existentes siguen pasando (no tocan la escritura real).

### Step 2: Tests del nuevo comportamiento

En `tests/test_publish.py`, añade un test que fike la hoja y verifique: (a)
una sola llamada `update`, (b) sin `clear()`, (c) padding cuando el dataset
se achicó:

```python
def test_canonical_update_is_single_call_with_padding(
    normalized_file: Path, comparison_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import polla_app.publish as pub

    calls: list[dict] = []
    fake_ws = type(
        "FakeWs",
        (),
        {
            "get_all_values": lambda self: [["sorteo", "fecha", "categoria", "pozo_clp"]]
            + [["1", "2024-01-01", "x", "1"]] * 5,
            "update": lambda self, values: calls.append({"values": values}),
        },
    )()
    fake_spreadsheet = type("FakeSpreadsheet", (), {"worksheet": lambda self, name: fake_ws})()

    # stub credentials + client via monkeypatch de pub._load_credentials
    def fake_credentials() -> object:
        return type("FakeClient", (), {"open_by_key": lambda self, k: fake_spreadsheet})()

    monkeypatch.setattr(pub, "_load_credentials", fake_credentials)
    monkeypatch.setenv("GOOGLE_SPREADSHEET_ID", "dummy")

    result = pub.publish_to_google_sheets(
        normalized_path=normalized_file,
        comparison_report_path=comparison_file,
        summary=None,
        worksheet_name="Normalized",
        discrepancy_tab="Discrepancies",
        dry_run=False,
        force_publish=False,
        allow_quarantine=True,
    )

    assert result["updated_rows"] == 1
    assert len(calls) == 1
    assert len(calls[0]["values"]) == 7  # 1 header + 1 record + 5 padding
    assert calls[0]["values"][-1] == []
```

Ajusta el fixture `normalized_file` (define un record pozos-only de 4 columnas,
p. ej. `{"sorteo": 5198, "fecha": "2024-12-01", "pozos_proximo": {"Loto": 100_000_000}}`)
para que el flujo de `_record_to_rows` produzca filas de 4 columnas (el fixture
existente usa `premios` → 8 columnas; si lo reutilizas, ajusta el conteo de
padding en consecuencia).

**Verify**: `python -m pytest tests/test_publish.py -q` → todo pasa, incluido
el test nuevo.

### Step 3: Regresión global

**Verify**: `python -m pytest -q` → todo pasa; `make ready` → todos los hooks pasan.

## Test plan

- Test nuevo: una sola llamada `update`, sin `clear()`, con padding al
  encoger (5 filas viejas → 1 nueva + 5 vacías).
- Regresión: dry-run, discrepancy sheet, pozos-only, decision parsing
  (tests existentes de `test_publish.py`).

## Done criteria

- [ ] `python -m pytest -q` exit 0
- [ ] `grep -n "ws.clear()" polla_app/publish.py` sin coincidencias
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app` exit 0
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 006 actualizada

## STOP conditions

Detente y reporta si:

- La firma o ubicación de `_update_canonical_worksheet` difiere del excerpt (drift).
- `ws.update` del gspread instalado no acepta listas con filas vacías
  (verifícalo en el entorno; si falla, usa `spreadsheet.values_update` con
  `range=` explícito y reporta la variante usada).
- Alguna verificación falla dos veces tras intento razonable.

## Maintenance notes

- Si en el futuro se añade paginación o multi-hoja, este patrón de "leer →
  escribir con padding" sigue siendo válido por hoja.
- El costo adicional es una llamada `get_all_values` por publish; si la cuota
  de la API fuera un problema, se puede cachear el tamaño por hoja.
- Revisar en el PR: que `updated_rows` siga contando solo filas reales
  (sin padding).
