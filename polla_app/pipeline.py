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
    source_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    overrides = {k.lower(): v for k, v in (source_overrides or {}).items()}
    openloto_url = overrides.get("openloto")
    payload = (
        pozos_module.get_pozo_openloto(url=openloto_url)
        if openloto_url
        else pozos_module.get_pozo_openloto()
    )
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


def _collect_pozos(
    include: bool, *, source_overrides: Mapping[str, str] | None = None
) -> tuple[dict[str, Any], ...]:
    if not include:
        return tuple()

    collected: list[dict[str, Any]] = []
    # Prefer resultadoslotochile.com as primary; openloto as fallback
    overrides = {k.lower(): v for k, v in (source_overrides or {}).items()}
    res_url = overrides.get("resultadoslotochile")
    open_url = overrides.get("openloto")
    for name, fetcher in (
        ("resultadoslotochile", pozos_module.get_pozo_resultadosloto),
        ("openloto", pozos_module.get_pozo_openloto),
    ):
        try:
            if name == "resultadoslotochile" and res_url:
                payload = fetcher(url=res_url)
            elif name == "openloto" and open_url:
                payload = fetcher(url=open_url)
            else:
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


def _compute_unchanged(
    previous_records: list[dict[str, Any]],
    *,
    sorteo: Any,
    fecha: Any,
    current_record: Mapping[str, Any],
) -> bool:
    """Return True if previous state contains same sorteo/fecha and identical amounts."""
    for prev in previous_records:
        if prev.get("sorteo") == sorteo and prev.get("fecha") == fecha:
            prev_pozos = {k: int(v) for k, v in (prev.get("pozos_proximo", {}) or {}).items()}
            curr_pozos = {
                k: int(v) for k, v in (current_record.get("pozos_proximo", {}) or {}).items()
            }
            if prev_pozos == curr_pozos:
                return True
            break
    return False


def _build_report_payload(
    *,
    run_id: str,
    generated_at: str,
    requested_sources: Sequence[str],
    timeout: int,
    retries: int,
    fail_fast: bool,
    sorteo: Any,
    fecha: Any,
    merged_pozos: Mapping[str, Any],
    record_source: Any,
    decision_status: str,
) -> dict[str, Any]:
    return {
        "run": {
            "id": run_id,
            "generated_at": generated_at,
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
        "prizes_changed": decision_status != "skip",
        "mismatches": [],
        "sources": {"pozos": {"url": record_source, "premios": 0}},
        "failures": [],
    }


def _build_summary_payload(
    *,
    run_id: str,
    generated_at: str,
    decision: Mapping[str, Any],
    normalized_path: Path,
    comparison_report_path: Path,
    raw_dir: Path,
    state_path: Path,
    publish_flag: bool,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "decision": dict(decision),
        "prizes_changed": bool(decision.get("status") != "skip"),
        "normalized_path": str(normalized_path),
        "comparison_report": str(comparison_report_path),
        "raw_dir": str(raw_dir),
        "state_path": str(state_path),
        "publish": publish_flag,
    }


def _handle_pozos_only(
    *,
    run_id: str,
    requested_sources: list[str],
    source_overrides: Mapping[str, str] | None,
    raw_dir: Path,
    normalized_path: Path,
    comparison_report_path: Path,
    summary_path: Path,
    state_path: Path,
    retries: int,
    timeout: int,
    fail_fast: bool,
    force_publish: bool,
    log_event: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    collected = _collect_pozos(include=True, source_overrides=source_overrides)
    if not collected:
        raise RuntimeError("No pozo sources returned data")

    merged_pozos, pozos_prov = _merge_pozos(collected)
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

    previous_records = _load_previous_state(state_path)
    unchanged = _compute_unchanged(
        previous_records, sorteo=sorteo, fecha=fecha, current_record=record
    )

    _write_jsonl(normalized_path, [record])
    _write_jsonl(state_path, [record])

    decision_status = "skip" if unchanged else "publish"
    publish_flag = not unchanged
    if force_publish and unchanged:
        decision_status = "publish_forced"
        publish_flag = True

    generated_at = datetime.now(timezone.utc).isoformat()
    report_payload = _build_report_payload(
        run_id=run_id,
        generated_at=generated_at,
        requested_sources=requested_sources,
        timeout=timeout,
        retries=retries,
        fail_fast=fail_fast,
        sorteo=sorteo,
        fecha=fecha,
        merged_pozos=merged_pozos,
        record_source=record["fuente"],
        decision_status=decision_status,
    )
    _write_json(comparison_report_path, report_payload)

    summary_payload = _build_summary_payload(
        run_id=run_id,
        generated_at=generated_at,
        decision=report_payload["decision"],
        normalized_path=normalized_path,
        comparison_report_path=comparison_report_path,
        raw_dir=raw_dir,
        state_path=state_path,
        publish_flag=publish_flag,
    )

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
                "sorteo_fecha_and_amounts_unchanged" if unchanged else "updated_or_new_amounts"
            ),
        }
    )
    _write_json(summary_path, summary_payload)
    return summary_payload


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

        # Pozos-only fast path
        if requested_sources == ["pozos"]:
            return _handle_pozos_only(
                run_id=run_id,
                requested_sources=requested_sources,
                source_overrides=source_overrides,
                raw_dir=raw_dir,
                normalized_path=normalized_path,
                comparison_report_path=comparison_report_path,
                summary_path=summary_path,
                state_path=state_path,
                retries=retries,
                timeout=timeout,
                fail_fast=fail_fast,
                force_publish=force_publish,
                log_event=log_event,
            )

        if requested_sources == ["openloto"]:
            return _run_openloto_only(
                raw_dir=raw_dir,
                normalized_path=normalized_path,
                comparison_report_path=comparison_report_path,
                summary_path=summary_path,
                state_path=state_path,
                log_event=log_event,
                source_overrides=source_overrides,
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
