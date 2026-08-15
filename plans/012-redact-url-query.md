# Plan 012: Redactar query params sensibles en URLs antes de loguear (sanitize)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat cb5d5ea..HEAD -- polla_app/obs.py tests/test_phase3_hardening.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security (investigate-then-fix)
- **Planned at**: commit `cb5d5ea`, 2026-08-14

## Why this matters

`obs.sanitize` trata las claves `fuente`/`source`/`url` como **seguras** y no
las redacta. Una URL con credenciales en el query string (firma, API key,
token — por ejemplo un `ALT_SOURCE_URLS` apuntando a un endpoint firmado)
llegaría íntegra a `logs/run.jsonl`. Hoy las URLs de fuentes son estáticas y
públicas, por lo que el riesgo es bajo — este plan primero **investiga** si
alguna URL manejada puede contener tokens, y luego implementa la redacción de
query params sensibles (sin romper las URLs normales que sí deben loguearse
para debugging).

## Current state

- `polla_app/obs.py` — `_should_redact_key` (líneas 31-42):

```python
def _should_redact_key(key: str) -> bool:
    key_l = key.lower()
    if key_l in {"fuente", "source", "url"}:  # URLs are safe in this context
        return False

    sensitive_tokens = ("password", "secret", "token", "credential", "apikey", "api_key")
    if any(tok in key_l for tok in sensitive_tokens):
        return True
    ...
```

- `sanitize` (líneas 44-64): recorre dicts/listas; para strings no-redactados
  devuelve el valor tal cual (no hay tratamiento especial de URLs).
- Consumidores de URLs en logs: `net.py` loguea `url` en warnings de fetch y
  backoff; `pipeline.py` loguea `fuente` en `pozos_enriched` y provenance;
  `exceptions.py` incluye `context` con URLs.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests     | `python -m pytest tests/test_phase3_hardening.py tests/test_errors.py -q` | all pass |
| Lint      | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app`         | success |
| Full gate | `make ready`             | all hooks pass |

## Scope

**In scope**:
- `polla_app/obs.py` — `sanitize`/helper de redacción de query params
- `tests/test_phase3_hardening.py` — tests de la redacción de URLs

**Out of scope**:
- Cambiar las claves logueadas por `net.py`/`pipeline.py` (la redacción es
  central en `sanitize`; nada más necesita cambiar).
- Redactar el host/path de las URLs (solo query params y fragmento).

## Git workflow

- Branch: `advisor/012-redact-url-query`
- Un commit: `fix(obs): redactar query params sensibles en URLs antes de loguear`.
- NO push/PR salvo instrucción.

## Steps

### Step 1: Investigar (antes de tocar nada)

Busca si alguna URL que llega a los logs puede contener tokens:

- `grep -rn "ALT_SOURCE_URLS" polla_app/ .github/` → el mecanismo de override
  (solo se documenta; los valores vienen de env del operador).
- `grep -rn "url=" polla_app/` → las URLs construidas en el código son
  estáticas (`OPENLOTO_URL`, `POLLA_URL`, `PENDON_URL`, `KINO_HUB_URL` —
  esta última ya contiene `session=undefined&...` en el query string, sin
  secretos pero con parámetros internos).

Registra el resultado en el mensaje del commit (p. ej. "no se encontraron
URLs con tokens en el código; el fix es defensivo"). Si encuentras una URL
con token real en el código o en `.github/`, detente y reporta (no la
redactes tú: es un hallazgo de seguridad).

**Verify**: `grep -rn "KINO_HUB_URL" polla_app/sources/prices.py` → confirma la
URL con query params (session=undefined...).

### Step 2: Implementar la redacción de query params

En `polla_app/obs.py`, añade un helper y úsalo en `sanitize`:

```python
_SENSITIVE_QUERY_PARAMS = ("token", "key", "apikey", "api_key", "sig", "signature", "credential", "password", "secret", "auth", "session", "access_token")

def _redact_url_query(value: str) -> str:
    """Redact sensitive query/fragment params from a URL (host/path kept)."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return value
        query = parse_qsl(parts.query, keep_blank_values=True)
        redacted = [(k, "<redacted>" if k.lower() in _SENSITIVE_QUERY_PARAMS else v) for k, v in query]
        fragment = parts.fragment
        if fragment:
            frag_parts = parse_qsl(fragment, keep_blank_values=True)
            frag_redacted = [(k, "<redacted>" if k.lower() in _SENSITIVE_QUERY_PARAMS else v) for k, v in frag_parts]
            fragment = urlencode(frag_redacted)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(redacted), fragment))
    except Exception:
        return value
```

En `sanitize`, la rama de valores string actual:

```python
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for k, v in obj.items():
            if _should_redact_key(str(k)):
                ...
            else:
                result[k] = sanitize(v)
        return result
```

El cambio: en el `else`, cuando `v` sea un `str` que parezca URL (empieza con
`http://` o `https://`), aplicar `_redact_url_query`:

```python
            else:
                if isinstance(v, str) and v.startswith(("http://", "https://")):
                    result[k] = _redact_url_query(v)
                else:
                    result[k] = sanitize(v)
```

Nota: `_SENSITIVE_QUERY_PARAMS` incluye `session` porque la URL del hub de
Kino (`KINO_HUB_URL`) lleva `session=undefined` — sin valor sensible, pero
consistente. No redactes el host/path: los logs de fetch necesitan la URL
completa para debugging (requisito del repo: "URLs are safe in this context").

**Verify**: `python -m pytest tests/test_phase3_hardening.py -q` → los tests de
redacción existentes siguen pasando (no romper `_should_redact_key`).

### Step 3: Tests

En `tests/test_phase3_hardening.py`, añade:

```python
def test_sanitize_redacts_sensitive_url_query_params() -> None:
    from polla_app.obs import sanitize

    payload = {
        "fuente": "https://api.example.test/feed?token=abc123&game=loto",
        "url": "https://www.openloto.cl/pozo-del-loto.html",
    }
    cleaned = sanitize(payload)
    assert cleaned["fuente"] == "https://api.example.test/feed?token=<redacted>&game=loto"
    assert cleaned["url"] == "https://www.openloto.cl/pozo-del-loto.html"


def test_sanitize_keeps_plain_urls_and_non_urls() -> None:
    from polla_app.obs import sanitize

    cleaned = sanitize({"url": "https://www.openloto.cl/pozo-del-loto.html", "nombre": "Loto Clásico"})
    assert cleaned["url"].startswith("https://www.openloto.cl")
    assert cleaned["nombre"] == "Loto Clásico"
```

**Verify**: `python -m pytest tests/test_phase3_hardening.py -q` → todo pasa.

### Step 4: Regresión global

**Verify**: `python -m pytest -q` → todo pasa; `make ready` → todos los hooks pasan.

## Test plan

- URL con `token=` en query → valor redactado, resto intacto.
- URL plana (openloto) → intacta.
- No-URL (nombre de categoría) → intacta.
- Regresión: `test_contextual_redaction_logic` y `test_redaction_false_positives`
  existentes.

## Done criteria

- [ ] `python -m pytest -q` exit 0
- [ ] `grep -n "_redact_url_query" polla_app/obs.py` → presente y usado en `sanitize`
- [ ] `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app` exit 0
- [ ] Solo archivos del Scope modificados (`git status`)
- [ ] `plans/README.md` fila 012 actualizada

## STOP conditions

Detente y reporta si:

- Encuentras una URL con token real en el código o workflows (reporta `file:line`
  y el tipo de token, sin el valor; no la arregles tú).
- `sanitize` se usa en un camino caliente donde `urlsplit` por URL degrade
  performance (no medido — si lo ves, reporta).
- Alguna verificación falla dos veces tras intento razonable.

## Maintenance notes

- Cualquier nueva URL con query params pasa automáticamente por esta
  redacción; si un día una fuente usa un parámetro sensible con otro nombre,
  añadirlo a `_SENSITIVE_QUERY_PARAMS`.
- `KINO_HUB_URL` queda con `session=<redacted>` en los logs — esperado.
