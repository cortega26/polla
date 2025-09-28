# Versioning and Deprecation Policy

This project follows Semantic Versioning (SemVer) for the Python package version (`polla_app.__version__`).

- MAJOR (X.y.z): Backward‑incompatible changes
- MINOR (x.Y.z): Backward‑compatible features
- PATCH (x.y.Z): Backward‑compatible bug fixes

## API Version

Artifacts and results include an `api_version` field (currently `v1`). Changes within `v1` are additive and backward‑compatible. Removals or breaking changes require a new API version (e.g., `v2`).

## Deprecation

- Deprecated functions remain available for at least one MINOR version with a documented alias.
- Internal renames provide compatibility aliases (e.g., `_normalise_*` -> `_normalize_*`).

## Migration Guidance

- Prefer reading `api_version` in artifacts and handle unknown fields gracefully.
- Avoid strict schema validation that fails on additional fields; this project adds fields over time for observability.

