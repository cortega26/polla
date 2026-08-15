# Plan 005: Reintentar también HTTP 502/503/504 en `fetch_html` (no solo 429)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/net.py tests/test_hardening_net.py tests/test_phase2_hardening.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

El pipeline anuncia `--retries 3` pero solo reintenta HTTP 429 (rate limit),
timeouts y errores de conexión. Un 502/503/504 transitorio (proxy, CDN, deploy
de la fuente) hace fallar la fuente al primer intento, degradando la
confianza del run o abortándolo con `--fail-fast`. Estos códigos son
retryables por definición; reintentarlos con el backoff existente cuesta poco
y sube la disponibilidad del pipeline.

## Current state

- `polla_app/net.py` — `_request()` (líneas ~135-142):

```python
    def _request() -> requests.Response:
        _rate_limit_if_needed()
        response = session.get(url, headers=headers, timeout=timeout)
        if response.status_code == 429:
            raise requests.HTTPError("Too Many Requests", response=response)
        response.raise_for_status()
        return response
```

- El bucle de reintentos (líneas ~162-175) — la rama HTTPError:

```python
        except requests.HTTPError as err:
            # Only HTTP 429 is retryable; other status codes fail fast.
            attempts += 1
            status = getattr(err.response, "status_code", None)
            if attempts >= max_retries or status != 429:
                raise
```

- Tests existentes del backoff: `tests/test_phase2_hardening.py::test_fetch_html_exponential_backoff`
  (mockea 429) y `tests/test_hardening_net.py` (timeouts, connection errors,
  agotamiento). Deben seguir pasando.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest tests/test_hardening_net.py tests/test_phase2_hardening.py -q` | all pass |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/net.py` — constante de códigos retryables + condición del bucle
- `tests/test_hardening_net.py` — tests nuevos de 5xx

**Out of scope**:
- No cambiar el backoff ni el manejo de 429 (ya funciona).
- No reintentar 4xx (404, 401, 403 — no transitorios) ni 500 (puede indicar
  bug real de la fuente; ver Maintenance notes).
- `sources/*` — sin cambios.

## Git workflow

- Branch: `advisor/005-retry-5xx`
- Un commit: `fix(net): reintentar HTTP 502/503/504 con backoff`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Definir los códigos retryables

En `polla_app/net.py`, junto a `_RETRYABLE_EXC` (búsquedalo: está definido
justo antes de `fetch_html`, ~línea 86-89), añade una constante:

```python
# HTTP status codes worth retrying with backoff (transient server errors).
_RETRYABLE_STATUS = (429, 502, 503, 504)
```

### Step 2: Usarla en el bucle de reintentos

Reemplaza la condición del bloque HTTPError:

```python
            if attempts >= max_retries or status != 429:
                raise
```

por:

```python
            if attempts >= max_retries or status not in _RETRYABLE_STATUS:
                raise
```

Actualiza el comentario de la rama:

```python
        except requests.HTTPError as err:
            # Only transient status codes are retryable; the rest fail fast.
```

Ajusta el mensaje de log "429 received from %s" para que sea genérico, por
ejemplo `"%s received from %s (attempt %d/%d); backing off %.1fs"` con
`status` como primer argumento.

**Verify**: `python -m pytest tests/test_phase2_hardening.py -q` → el test de
backoff 429 sigue pasando.

### Step 3: Tests de 5xx

En `tests/test_hardening_net.py`, añade (patrón: `test_fetch_html_retries_on_timeout`,
que usa `_fail_once` y monkeypatchea `requests.Session`):

```python
def test_fetch_html_retries_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    error = requests.HTTPError("Service Unavailable")
    error.response = requests.Response()
    error.response.status_code = 503
    state: list[Any] = [error]

    def fail_once(*args: Any, **kwargs: Any) -> requests.Response:
        if state:
            state.pop(0)
            raise error
        response = requests.Response()
        response.status_code = 200
        response._content = b"<html>ok</html>"
        return response

    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type("S", (), {"get": fail_once})(),
    )
    monkeypatch.setenv("POLLA_BACKOFF_FACTOR", "0.001")
    metadata = fetch_html("https://example.test", "ua", timeout=5, retries=2)
    assert metadata.html == "<html>ok</html>"


def test_fetch_html_fails_fast_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("polla_app.net._robots_allowed", lambda *_, **__: True)
    error = requests.HTTPError("Not Found")
    error.response = requests.Response()
    error.response.status_code = 404

    def always_404(*args: Any, **kwargs: Any) -> requests.Response:
        raise error

    monkeypatch.setattr(
        "polla_app.net.requests.Session",
        lambda: type("S", (), {"get": always_404})(),
    )
    with pytest.raises(requests.HTTPError):
        fetch_html("https://example.test", "ua", timeout=5, retries=3)
```

Nota: `_fail_once` existente solo maneja excepciones sin `response`; los 5xx
se lanzan con `response`, por eso este test define su propio stub.

**Verify**: `python -m pytest tests/test_hardening_net.py -q` → todo pasa,
incluidos los 2 tests nuevos.

## Test plan

- 503 transitorio → reintenta y triunfa (test nuevo).
- 404 persistente → falla rápido sin reintentar (test nuevo, fija el límite).
- Regresión: 429 (test_phase2), timeout, connection error, agotamiento
  (test_hardening_net) siguen pasando.

## Done criteria

- [ ] `python -m pytest -q` exit 0
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app` exit 0
- [ ] `grep -n "status != 429" polla_app/net.py` sin coincidencias
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 005 actualizada

## STOP conditions

Detente y reporta si:

- El bucle de reintentos no coincide con el excerpt (drift).
- Alguna verificación falla dos veces tras intento razonable.
- Aparece un test existente que asume que 5xx falla al primer intento (no lo
  "arregles" cambiando su intención; reporta).

## Maintenance notes

- 500 quedó deliberadamente fuera: un 500 persistente suele indicar un bug
  real en la fuente y el backoff lo enmascararía. Si las fuentes empiezan a
  devolver 500 transitorios, añadirlo a `_RETRYABLE_STATUS` con tests.
- El mensaje de log genérico facilita distinguir 429 vs 5xx en `logs/run.jsonl`
  (el campo `status` queda en el mensaje).
