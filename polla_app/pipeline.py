"""Orchestration for próximo pozo aggregation (resultadoslotochile + openloto)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sources import pozos as pozos_module

LOGGER = logging.getLogger(__name__)


# No article loaders are configured; we operate in pozos-only mode.
SOURCE_LOADERS: dict[str, Any] = {}


def _normalise_sources(requested: Sequence[str]) -> list[str]:
    lowered = {item.lower() for item in requested}
    # Pozos-only modes
    if "pozos" in lowered:
        return ["pozos"]
    if "openloto" in lowered:
        return ["openloto"]
    if "all" in lowered:
        return sorted(SOURCE_LOADERS.keys())
    normalised: list[str] = []
    for item in requested:
        key = item.lower()
        if key not in SOURCE_LOADERS:
            raise ValueError(
                f"Unsupported source '{item}'. Available: openloto, {', '.join(SOURCE_LOADERS)}"
            )
        if key not in normalised:
            normalised.append(key)
    return normalised


def _run_openloto_only(
    *,
    raw_dir: Path,
    normalized_path: Path,
    comparison_report_path: Path,
    summary_path: Path,
    state_path: Path,
    log_event: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    payload = pozos_module.get_pozo_openloto()
    amounts = payload.get("montos", {})
    if not amounts:
        raise RuntimeError("OpenLoto returned no amounts")

    record: dict[str, Any] = {
        "sorteo": None,
        "fecha": None,
        "fuente": payload.get("fuente"),
        "premios": [],
        "pozos_proximo": amounts,
        "provenance": {
            "pozos": {
                "primary": {
                    "fuente": payload.get("fuente"),
                    "fetched_at": payload.get("fetched_at"),
                    "user_agent": payload.get("user_agent"),
                    "estimado": True,
                }
            }
        },
    }

    # Write raw JSON
    raw_dir.mkdir(parents=True, exist_ok=True)
    _write_json(raw_dir / "openloto.json", payload)

    # Normalized/state
    _write_jsonl(normalized_path, [record])
    _write_jsonl(state_path, [record])

    run_info: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": ["openloto"],
        "timeout": None,
        "retries": None,
        "fail_fast": None,
    }
    report = {
        "run": run_info,
        "last_draw": {"sorteo": None, "fecha": None},
        "decision": {
            "status": "publish",
            "total_categories": len(amounts),
            "mismatched_categories": 0,
        },
        "prizes_changed": True,
        "mismatches": [],
        "sources": {
            "openloto": {
                "url": payload.get("fuente"),
                "premios": 0,
            }
        },
        "failures": [],
    }
    _write_json(comparison_report_path, report)

    openloto_summary: dict[str, Any] = {
        "run_id": str(uuid.uuid4()),
        "generated_at": run_info["generated_at"],
        "decision": report["decision"],
        "prizes_changed": True,
        "normalized_path": str(normalized_path),
        "comparison_report": str(comparison_report_path),
        "raw_dir": str(raw_dir),
        "state_path": str(state_path),
        "publish": True,
    }
    _write_json(summary_path, openloto_summary)
    # Emit detailed jackpot categories to the structured log
    log_event(
        {
            "event": "pozos_enriched",
            "source_mode": "openloto_only",
            "primary": {
                "fuente": payload.get("fuente"),
                "fetched_at": payload.get("fetched_at"),
                "user_agent": payload.get("user_agent"),
                "estimado": True,
            },
            "categories": amounts,
        }
    )
    log_event(
        {
            "event": "pipeline_complete",
            "run_id": openloto_summary["run_id"],
            "decision": "publish",
            "mismatch_ratio": 0.0,
            "prizes_changed": True,
        }
    )
    return openloto_summary


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


# Legacy article-source helpers removed in pozos-only build


def _load_previous_state(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    previous: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                previous.append(json.loads(line))
            except json.JSONDecodeError:
                LOGGER.warning("Invalid JSON line in %s; ignoring", path)
    return previous


## article-source comparison helper removed


def _collect_pozos(include: bool) -> tuple[dict[str, Any], ...]:
    if not include:
        return tuple()

    collected: list[dict[str, Any]] = []
    # Prefer resultadoslotochile.com as primary; openloto as fallback
    for fetcher in (pozos_module.get_pozo_resultadosloto, pozos_module.get_pozo_openloto):
        try:
            payload = fetcher()
        except Exception as exc:  # pragma: no cover - network/runtime guard
            LOGGER.warning("Pozo fetcher %s failed: %s", fetcher.__name__, exc)
            continue
        if payload.get("montos"):
            collected.append(payload)
    return tuple(collected)


def _merge_pozos(collected: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    merged: dict[str, int] = {}
    provenance: dict[str, Any] = {}
    alternatives: list[dict[str, Any]] = []
    for idx, entry in enumerate(collected):
        for categoria, monto in entry.get("montos", {}).items():
            if str(categoria).lower().startswith("total"):
                continue
            merged.setdefault(categoria, int(monto))
        descriptor = {
            "fuente": entry.get("fuente"),
            "fetched_at": entry.get("fetched_at"),
            "user_agent": entry.get("user_agent"),
            "estimado": entry.get("estimado", True),
            "sorteo": entry.get("sorteo"),
            "fecha": entry.get("fecha"),
        }
        if idx == 0:
            provenance["primary"] = descriptor
        else:
            alternatives.append(descriptor)
    if alternatives:
        provenance["alternatives"] = alternatives
    return merged, provenance


def _init_log_stream(log_path: Path) -> Callable[[dict[str, Any]], None]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("a", encoding="utf-8")

    def _emit(payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")
        handle.flush()

    def _close() -> None:
        handle.close()

    _emit.close = _close  # type: ignore[attr-defined]
    return _emit


def run_pipeline(
    *,
    sources: Sequence[str],
    source_overrides: Mapping[str, str] | None,
    raw_dir: Path,
    normalized_path: Path,
    comparison_report_path: Path,
    summary_path: Path,
    state_path: Path,
    log_path: Path,
    retries: int,
    timeout: int,
    fail_fast: bool,
    mismatch_threshold: float,
    include_pozos: bool,
    force_publish: bool = False,
) -> dict[str, Any]:
    """Run the ingestion + validation pipeline and emit artefacts."""

    log_event = _init_log_stream(log_path)
    run_id = str(uuid.uuid4())
    log_event({"event": "pipeline_start", "run_id": run_id, "sources": sources})

    try:
        requested_sources = _normalise_sources(sources)

        # Pozos-only fast paths
        if requested_sources == ["pozos"]:
            # Fetch from resultadoslotochile (primary) + openloto (fallback), compare to previous state
            collected = _collect_pozos(include=True)
            if not collected:
                raise RuntimeError("No pozo sources returned data")

            merged_pozos, pozos_prov = _merge_pozos(collected)
            # Determine sorteo/fecha from primary if available
            primary = collected[0]
            sorteo = primary.get("sorteo")
            fecha = primary.get("fecha")

            record: dict[str, Any] = {
                "sorteo": sorteo,
                "fecha": fecha,
                "fuente": pozos_prov.get("primary", {}).get("fuente"),
                "premios": [],
                "pozos_proximo": merged_pozos,
                "provenance": {"pozos": pozos_prov},
            }

            # Compare with previous state (use sorteo+fecha AND amounts to detect changes)
            previous_records = _load_previous_state(state_path)
            unchanged = False
            for prev in previous_records:
                if prev.get("sorteo") == sorteo and prev.get("fecha") == fecha:
                    prev_pozos = {
                        k: int(v) for k, v in (prev.get("pozos_proximo", {}) or {}).items()
                    }
                    curr_pozos = {
                        k: int(v) for k, v in (record.get("pozos_proximo", {}) or {}).items()
                    }
                    if prev_pozos == curr_pozos:
                        unchanged = True
                    break

            # Write artifacts
            _write_jsonl(normalized_path, [record])
            _write_jsonl(state_path, [record])

            decision_status = "skip" if unchanged else "publish"
            publish_flag = not unchanged
            if force_publish and unchanged:
                decision_status = "publish_forced"
                publish_flag = True
            report_payload: dict[str, Any] = {
                "run": {
                    "id": run_id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "sources": requested_sources,
                    "timeout": timeout,
                    "retries": retries,
                    "fail_fast": fail_fast,
                },
                "last_draw": {"sorteo": sorteo, "fecha": fecha},
                "decision": {
                    "status": decision_status,
                    "total_categories": len(merged_pozos),
                    "mismatched_categories": 0,
                },
                "prizes_changed": not unchanged,
                "mismatches": [],
                "sources": {"pozos": {"url": record["fuente"], "premios": 0}},
                "failures": [],
            }
            _write_json(comparison_report_path, report_payload)

            summary_payload: dict[str, Any] = {
                "run_id": run_id,
                "generated_at": report_payload["run"]["generated_at"],
                "decision": report_payload["decision"],
                "prizes_changed": not unchanged,
                "normalized_path": str(normalized_path),
                "comparison_report": str(comparison_report_path),
                "raw_dir": str(raw_dir),
                "state_path": str(state_path),
                "publish": publish_flag,
            }

            # Log enriched pozos
            log_event(
                {
                    "event": "pozos_enriched",
                    "source_mode": "pozos_only",
                    "primary": pozos_prov.get("primary"),
                    "alternatives": pozos_prov.get("alternatives", []),
                    "categories": merged_pozos,
                }
            )
            log_event(
                {
                    "event": "pipeline_complete",
                    "run_id": run_id,
                    "decision": decision_status,
                    "mismatch_ratio": 0.0,
                    "prizes_changed": not unchanged,
                    "reason": (
                        "sorteo_fecha_and_amounts_unchanged"
                        if unchanged
                        else "updated_or_new_amounts"
                    ),
                }
            )
            _write_json(summary_path, summary_payload)
            return summary_payload

        if requested_sources == ["openloto"]:
            return _run_openloto_only(
                raw_dir=raw_dir,
                normalized_path=normalized_path,
                comparison_report_path=comparison_report_path,
                summary_path=summary_path,
                state_path=state_path,
                log_event=log_event,
            )

        # Any other requested sources are not supported in this pozos-only build.
        raise ValueError(
            f"Unsupported sources {requested_sources}. Only 'pozos' or 'openloto' are supported."
        )
    finally:
        closer = getattr(log_event, "close", None)
        if callable(closer):  # pragma: no branch - trivial guard
            closer()


__all__ = ["run_pipeline"]
