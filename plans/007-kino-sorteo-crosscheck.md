# Plan 007: Validar que el sorteo del hub de precios Kino coincida con el del pendón

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/pipeline.py polla_app/sources/prices.py tests/test_pipeline.py tests/test_prices.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: 001 (ambos tocan `pipeline.py`; ejecutar 001 primero evita
  conflictos de edición en el mismo archivo)
- **Category**: bug
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

Los precios de Kino se scrapean del hub (`kino.loteria.cl`, primer sorteo de
`initialSorteos`) y los pozos del pendón (`pendon-kino.loteria.cl`). Ambos
pertenecen al mismo sorteo en condiciones normales, pero si el hub sirve una
caché vieja (sorteo anterior) los precios se adjuntan al record del sorteo
actual sin ninguna advertencia — el dashboard mostraría apuestas del sorteo
equivocado como si fueran las actuales. Un chequeo de coherencia de `sorteo`
es barato y convierte ese fallo silencioso en un warning observable.

## Current state

- `polla_app/pipeline.py` — bloque de precios Kino en
  `_run_ingestion_for_sources` (líneas ~540-547):

```python
        if "kino" in requested_sources:
            try:
                kino_prices = prices_module.get_kino_prices(timeout=timeout, retries=retries)
                record.setdefault("precios", {}).update(kino_prices["precios"])
                log_event({"event": "prices_fetched", "game": "kino"})
            except Exception as exc:  # noqa: BLE001 - prices are auxiliary per run
                LOGGER.warning("Could not fetch live Kino prices: %s", exc)
                log_event({"event": "prices_failed", "game": "kino", "error": type(exc).__name__})
```

- `polla_app/sources/prices.py` — `get_kino_prices()` devuelve
  `{"precios": {...}, "sorteo": <int>, "fecha": "...", ...}` (líneas ~245-270).
  El sorteo del pendón está en el payload del fetcher de pozos:
  `payload["sorteo"]` de `get_pozo_kino()` (`polla_app/sources/kino.py`, el
  campo `"sorteo"` del dict de retorno).

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest tests/test_pipeline.py tests/test_prices.py -q` | all pass |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/pipeline.py` — bloque de precios Kino
- `tests/test_pipeline.py` — test del desajuste de sorteo

**Out of scope**:
- `polla_app/sources/prices.py` — no cambia (el sorteo ya viaja en el payload).
- El comportamiento de `get_pozo_kino` / el pendón.

## Git workflow

- Branch: `advisor/007-kino-sorteo-crosscheck`
- Un commit: `fix(pipeline): validar sorteo del hub de precios Kino contra el pendón`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Añadir el chequeo de sorteo

En `polla_app/pipeline.py`, dentro del bloque `if "kino" in requested_sources:`,
después de obtener `kino_prices`, busca el sorteo del pendón en los payloads ya
recolectados y solo adjunta los precios si coinciden:

```python
        if "kino" in requested_sources:
            try:
                kino_prices = prices_module.get_kino_prices(timeout=timeout, retries=retries)
                kino_payload = next(
                    (entry for entry in collected if entry.get("source_name") == "kino"),
                    None,
                )
                pendon_sorteo = kino_payload.get("sorteo") if kino_payload else None
                if pendon_sorteo and kino_prices.get("sorteo") != pendon_sorteo:
                    LOGGER.warning(
                        "Kino price hub sorteo %s does not match pendón sorteo %s; "
                        "prices skipped for this run",
                        kino_prices.get("sorteo"),
                        pendon_sorteo,
                    )
                    log_event(
                        {
                            "event": "prices_failed",
                            "game": "kino",
                            "error": "sorteo_mismatch",
                            "hub_sorteo": kino_prices.get("sorteo"),
                            "pendon_sorteo": pendon_sorteo,
                        }
                    )
                else:
                    record.setdefault("precios", {}).update(kino_prices["precios"])
                    log_event({"event": "prices_fetched", "game": "kino"})
            except Exception as exc:  # noqa: BLE001 - prices are auxiliary per run
                LOGGER.warning("Could not fetch live Kino prices: %s", exc)
                log_event({"event": "prices_failed", "game": "kino", "error": type(exc).__name__})
```

Notas:
- Si el pendón no reporta sorteo (`pendon_sorteo` falsy), se adjuntan los
  precios (no hay nada contra qué validar) — comportamiento actual.
- `collected` contiene los payloads con `source_name` fijado por
  `_collect_kino` (verifica con `grep -n "source_name" polla_app/pipeline.py`;
  los payloads de `_collect_pozos`/`_collect_kino` lo fijan al añadirlos).

**Verify**: `python -m pytest tests/test_pipeline.py -q` → los tests de kino
existentes siguen pasando.

### Step 2: Test del desajuste

En `tests/test_pipeline.py`, añade un test que monkeypatchee
`prices_module.get_kino_prices` (busca cómo el archivo importa el módulo:
`from polla_app import pipeline as pipeline_mod`) para devolver un sorteo
distinto al del pendón y verifique que el record NO lleva precios y que se
emite el evento `prices_failed`:

```python
def test_kino_prices_skipped_on_sorteo_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polla_app import pipeline as pipeline_mod

    def stub_kino(**_: object) -> dict[str, object]:
        return {"precios": {"Kino": {"delta_clp": 1000, "acumulado_clp": 1000}}, "sorteo": 9999}

    kino_payload = {
        "fuente": "https://pendon-kino.loteria.cl/pendonkino",
        "montos": {"Kino": 8_370_000_000},
        "sorteo": 3266,
        "fecha": "2026-08-14",
    }
    monkeypatch.setattr(pipeline_mod, "KINO_SOURCES", (("kino", lambda **_: kino_payload),))
    monkeypatch.setattr(pipeline_mod.prices_module, "get_kino_prices", stub_kino)

    run_pipeline(
        sources=["kino"],
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
        include_prices=True,
    )

    record = json.loads(
        (tmp_path / "normalized.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert "precios" not in record
    log_lines = [
        json.loads(line)
        for line in (tmp_path / "run.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(
        line.get("event") == "prices_failed" and line.get("error") == "sorteo_mismatch"
        for line in log_lines
    )
```

Patrón de imports: `tests/test_pipeline.py` ya usa `json`, `tmp_path`,
`monkeypatch` y `pipeline_mod` en tests como
`test_pipeline_unsupported_source_raises_error`.

**Verify**: `python -m pytest tests/test_pipeline.py -q` → todo pasa, incluido
el test nuevo.

### Step 3: Verificación global

**Verify**: `python -m pytest -q` → todo pasa; `make ready` → todos los hooks pasan.

## Test plan

- Caso nuevo: hub con sorteo distinto al pendón → precios omitidos + evento
  `prices_failed` con `error=sorteo_mismatch`.
- Regresión: run kino normal (sorteos iguales) adjunta precios — cubierto por
  el test existente de pipeline kino si lo hay; si no, el test del paso 2 con
  `sorteo: 3266` igual al pendón cubre el camino feliz.

## Done criteria

- [ ] `python -m pytest -q` exit 0
- [ ] `grep -n "sorteo_mismatch" polla_app/pipeline.py` → presente
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app` exit 0
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 007 actualizada

## STOP conditions

Detente y reporta si:

- El bloque de precios Kino no coincide con el excerpt (drift, p. ej. por el
  plan 001).
- Los payloads de `collected` no tienen `source_name == "kino"` (verifícalo
  con un `print` temporal en un test; no cambies `_collect_kino`).
- Alguna verificación falla dos veces tras intento razonable.

## Maintenance notes

- Si el hub y el pendón se desincronizan con frecuencia, considera comparar
  también `fecha` además de `sorteo` (mismo sitio del chequeo).
- El evento `prices_failed` con `error=sorteo_mismatch` ya viaja a
  `logs/run.jsonl`; se puede alertar en el futuro desde el health check.
