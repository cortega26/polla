# Plan 044: Deduplicate NEXT_DATA extraction, DEFAULT_UA, and the payload envelope

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8a5da7f..HEAD -- polla_app/sources/common.py polla_app/sources/kino.py polla_app/sources/prices.py polla_app/sources/pozos.py polla_app/stats.py tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED — the payload envelope is the money path; keep output dicts byte-identical
- **Depends on**: none (prefer after 039/040/042/043 — they also touch kino.py/prices.py/pozos.py; sequential editing avoids conflicts)
- **Category**: tech-debt
- **Planned at**: commit `8a5da7f`, 2026-08-15

## Why this matters

Three pieces of the sources layer are duplicated across modules, and two of
them have already drifted:

1. The `__NEXT_DATA__` block regex + JSON-parse error handling exist twice:
   `kino.py:52-72` (`_NEXT_DATA_RE` + `_extract_next_data`) and
   `prices.py:56-59,223-234` (inline search + parse). Same regex string,
   slightly different error messages. A layout change to the block must be
   fixed in two places.
2. `DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"` is defined
   **four times** (pozos.py:18, kino.py:35, prices.py:27, stats.py:31) — a UA
   change requires 4 coordinated edits, and the contact email will drift.
3. The payload envelope (`fuente`, `fetched_at`, `sha256`, `estimado`,
   `montos`, `user_agent`, `sorteo`, `fecha`) is hand-rolled **four times**:
   the canonical `build_pozo_payload` (common.py:21-30) plus three inline
   copies — `prices.py:166-172` (get_loto_prices), `prices.py:237-242`
   (get_kino_prices), `pozos.py:422-433` (get_pozo_polla, which also
   hardcodes `user_agent: "Scrapling/StealthyFetcher"` instead of using the
   metadata it fetched with). The "No valid pozo amounts found in source
   content from {url}" error is also duplicated (pozos.py:242-246, 414-418).

Every canonical-shape addition (e.g. plan 030's `game` field) currently must
be applied in 4 builders or it silently ships in only some outputs.

## Current state

`polla_app/sources/common.py:8-30`:

```python
def build_pozo_payload(
    *,
    metadata: FetchMetadata,
    montos: dict[str, int],
    sorteo: Any,
    fecha: Any,
    fuente: str | None = None,
) -> dict[str, Any]:
    return {
        "fuente": fuente or metadata.url,
        "fetched_at": metadata.fetched_at.isoformat(),
        "sha256": metadata.sha256,
        "estimado": True,
        "montos": montos,
        "user_agent": metadata.user_agent,
        "sorteo": sorteo,
        "fecha": fecha,
    }
```

`polla_app/sources/kino.py:52-72`:

```python
_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)

def _extract_next_data(html: str) -> dict[str, Any]:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        raise ParseError(
            "Kino pendón page did not contain __NEXT_DATA__ (site layout changed?)",
            context={"snippet": html[:200]},
        )
    try:
        return json.loads(match.group(1))  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise ParseError(
            "Kino pendón __NEXT_DATA__ is not valid JSON",
            original_error=exc,
        ) from exc
```

`polla_app/sources/prices.py:56-59`:

```python
_KINO_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)
```

and `prices.py:223-234` does the search + `json.loads` + `ParseError` inline
(see the `get_kino_prices` function).

`polla_app/sources/pozos.py:422-433` — get_pozo_polla returns a hand-built
dict with the same keys as `build_pozo_payload`, but `user_agent` is the
hardcoded string `"Scrapling/StealthyFetcher"`.

Tests to keep green: `tests/test_kino.py`, `tests/test_prices.py`,
`tests/test_pozo_polla.py`, `tests/test_stats.py`, `tests/test_contracts.py`,
and the e2e `test_verification_suite.py` (asserts raw payloads in
single-source runs).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests (targeted) | `pytest tests/test_kino.py tests/test_prices.py tests/test_pozo_polla.py tests/test_stats.py tests/test_contracts.py -q` | all pass |
| Tests (full) | `pytest -q` | all pass |
| Lint | `ruff check polla_app tests` | exit 0 |
| Typecheck | `mypy polla_app tests` | exit 0 |

## Scope

**In scope** (the only files you should modify):
- `polla_app/sources/common.py` — add `DEFAULT_UA` and `extract_next_data`
- `polla_app/sources/kino.py` — use shared `extract_next_data` and `DEFAULT_UA`
- `polla_app/sources/prices.py` — use shared `extract_next_data`, `DEFAULT_UA`, and `build_pozo_payload`
- `polla_app/sources/pozos.py` — use shared `DEFAULT_UA`; `get_pozo_polla` uses `build_pozo_payload`
- `polla_app/stats.py` — use shared `DEFAULT_UA`
- `tests/test_pozo_polla.py`, `tests/test_prices.py` — only if an assertion references a removed local name

**Out of scope** (do NOT touch, even though they look related):
- Changing any output dict key or value (byte-identical outputs required)
- The retry loop in `get_pozo_polla` (plan 045)
- Plan 042's trailing-dot tolerance and plan 040's `numbers.py` — different files
- The price-block parsing logic (`_extract_prices`) — only its envelope changes

## Git workflow

- Branch: `advisor/044-sources-dedupe`
- Commit message style: `refactor(sources): helpers compartidos NEXT_DATA/UA/envelope (sin cambio de salida)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add `DEFAULT_UA` and `extract_next_data` to `common.py`

Add to `polla_app/sources/common.py`:

```python
DEFAULT_UA = "PollaAltSourcesBot/1.0 (+contact@example.com)"

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)


def extract_next_data(html: str, *, context: str) -> dict[str, Any]:
    """Extract and parse the __NEXT_DATA__ JSON block from a Next.js page.

    ``context`` names the source in the error messages (e.g. "Kino pendón"
    or "Kino hub"). Raises ParseError on missing block or invalid JSON.
    """
```

Implementation: transcribe the bodies from kino.py:52-72, but parameterize
the two error messages with `context`:
- missing block: `f"{context} page did not contain __NEXT_DATA__ (site layout changed?)"`
- invalid JSON: `f"{context} __NEXT_DATA__ is not valid JSON"`

Add the required imports (`re`, `json`, `ParseError`) to common.py (it
currently imports only `typing` and `FetchMetadata`).

**Verify**: `python -c "from polla_app.sources.common import DEFAULT_UA, extract_next_data; print(DEFAULT_UA)"` → the UA string; `ruff check polla_app tests` exit 0.

### Step 2: Migrate kino.py

- Replace `_POZO_FIELDS`-unrelated local `_NEXT_DATA_RE` + `_extract_next_data`
  with `from .common import DEFAULT_UA, extract_next_data as _extract_next_data` (keep the local alias so the call site at kino.py:125 is untouched) — but note plan 039 may have already moved `_POZO_FIELDS` to categories.py; if so, keep the import aliases consistent with whatever 039 left.
- Replace the local `DEFAULT_UA = ...` line with the import.
- Update `_extract_next_data`'s callers to pass `context="Kino pendón"` — but if you kept the alias `_extract_next_data`, the call at kino.py:125 is `_extract_next_data(metadata.html)` — it now needs `context=`. Update that one call site.
- Remove the now-unused `import json` and `re` if nothing else in kino.py uses them (check: kino.py uses `re` only for `_NEXT_DATA_RE`? — verify with grep before removing).

**Verify**: `pytest tests/test_kino.py -q` → all pass; `grep -n "NEXT_DATA" polla_app/sources/kino.py` → only the import alias and the call site.

### Step 3: Migrate prices.py

- Replace `_KINO_NEXT_DATA_RE` + the inline parse in `get_kino_prices`
  (prices.py:223-234) with `extract_next_data(metadata.html, context="Kino hub")`.
- Replace `DEFAULT_UA = ...` with the import.
- Make `get_loto_prices` and `get_kino_prices` build their return via
  `build_pozo_payload` **only if the shape matches exactly**. Check: the
  price payloads have extra keys (`precios`, `cumulative`, `sorteo`, `fecha`)
  beyond the envelope. So do NOT force them through `build_pozo_payload` —
  instead, keep their dicts but replace only the four shared envelope fields
  with values computed identically. The real fix is in `get_pozo_polla`
  (Step 4). For prices.py the actionable dedup is the NEXT_DATA import and
  UA; leave the envelope as-is and note why in the report (its shape differs).

**Verify**: `pytest tests/test_prices.py -q` → all pass; `grep -n "DEFAULT_UA\|NEXT_DATA" polla_app/sources/prices.py` → only imports/call sites.

### Step 4: Route `get_pozo_polla` through `build_pozo_payload`

In `polla_app/sources/pozos.py:422-433`, replace the hand-built return with:

```python
    return build_pozo_payload(
        metadata=metadata_envelope,
        montos=amounts,
        sorteo=sorteo,
        fecha=fecha,
        fuente=url,
    )
```

where `metadata_envelope` is a `FetchMetadata`-shaped object carrying the
fields get_pozo_polla actually has. **Problem**: `build_pozo_payload` needs
a `FetchMetadata` (has `url`, `fetched_at`, `sha256`, `user_agent`), but
get_pozo_polla built its own `fetched_at`/`sha256` and a hardcoded UA.
Check `polla_app/net.py` `FetchMetadata`'s definition (fields and whether it
is a NamedTuple/dataclass). Two options:

- (a) Construct a `FetchMetadata` instance from the local `fetched_at`/
  `sha256` and `user_agent="Scrapling/StealthyFetcher"` and `url`, then call
  `build_pozo_payload`. **This changes the hardcoded UA from
  "Scrapling/StealthyFetcher" to...** — NO: build_pozo_payload uses
  `metadata.user_agent`, so passing a metadata with
  `user_agent="Scrapling/StealthyFetcher"` keeps the output **identical**.
- (b) Add an optional `user_agent` override to `build_pozo_payload`.

Prefer (a): output stays byte-identical. If `FetchMetadata` is not
constructible directly (immutable with required fields that get_pozo_polla
can't provide), use `types.SimpleNamespace` with the four attributes — but
only if the type annotation accepts it (check `build_pozo_payload`'s
parameter type; it's `metadata: FetchMetadata` — SimpleNamespace may fail
mypy; then option (b) is cleaner). Decide by reading FetchMetadata first;
report which you used.

**Verify**: `pytest tests/test_pozo_polla.py -q` → all pass with **no test
changes** (outputs unchanged, including `user_agent`); confirm with a manual
assert: `grep -n "Scrapling/StealthyFetcher" polla_app/sources/pozos.py` →
still present (as the metadata UA value).

### Step 5: Migrate stats.py DEFAULT_UA

Replace `stats.py:31` `DEFAULT_UA = ...` with the import from common.py.

**Verify**: `pytest tests/test_stats.py -q` → all pass.

## Test plan

- No new tests required if outputs are byte-identical (existing suites are
  the lock). If you had to change a value (you should not), that is a STOP
  condition.
- `pytest tests/test_kino.py tests/test_prices.py tests/test_pozo_polla.py tests/test_stats.py tests/test_contracts.py -q` all pass, then full suite.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `grep -rn "DEFAULT_UA =" polla_app/` → only `sources/common.py` defines it
- [ ] `grep -rn "NEXT_DATA_RE" polla_app/` → only `sources/common.py` defines the regex
- [ ] `grep -rn "user_agent.*Scrapling/StealthyFetcher\|Scrapling/StealthyFetcher" polla_app/sources/pozos.py` → still present (output preserved)
- [ ] `pytest -q`, `ruff check polla_app tests`, `black --check polla_app tests`, `mypy polla_app tests` all exit 0
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

Stop and report back (do not improvise) if:

- Any test asserts an output value that would change (the envelope refactor must be output-identical; if a test fails on a value, report — do not change the value).
- `FetchMetadata` can't be constructed or wrapped for option (a) — report; use option (b) only if mypy stays clean.
- Plan 039/040 have already moved things in these files (registry imports, numbers module) — adapt imports to what exists and note it.
- `import json`/`re` removal in kino.py breaks something — leave them and note it.

## Maintenance notes

- After this plan, a canonical-shape addition (e.g. `game` field from plan 030) is a one-file edit in `common.py`.
- The prices.py envelope intentionally differs (extra `precios`/`cumulative` keys) — documented in the report; a future plan could generalize `build_pozo_payload` to accept extras.
- The Kino `__NEXT_DATA__` extractor is now shared; the future LOTO-results parser (GAMES.md recommendation) should use `extract_next_data` too.