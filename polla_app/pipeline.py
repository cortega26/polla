"""Orchestration for próximo pozo aggregation (openloto + polla)."""

from __future__ import annotations

import inspect
import json
import logging
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .contracts import API_VERSION
from .notifiers import notify_quarantine, notify_slack
from .obs import metric, sanitize, set_correlation_id, span
from .sources import pozos as pozos_module

LOGGER = logging.getLogger(__name__)


# Source registry for dynamic orchestration
SOURCE_LOADERS: dict[str, Callable[..., tuple[dict[str, Any], ...]]] = {}


class LogStream(Protocol):
    """Protocol for structured log emission with lifecycle and correlation support."""

    def __call__(self, payload: dict[str, Any]) -> None: ...
    def close(self) -> None: ...
    def set_correlation_id(self, value: str) -> None: ...


def _normalize_sources(requested: Sequence[str]) -> list[str]:
    lowered = {item.lower() for item in requested}
    if "all" in lowered or "pozos" in lowered:
        return ["pozos"]

    normalised: list[str] = []
    for item in requested:
        key = item.lower()
        if key not in SOURCE_LOADERS:
            raise ValueError(f"Unsupported source '{item}'. Available: {', '.join(SOURCE_LOADERS)}")
        if key not in normalised:
            normalised.append(key)
    return normalised


# Backward-compat alias removed (deprecated)
# _normalise_sources = _normalize_sources


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


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


POZO_SOURCES = (
    ("openloto", pozos_module.get_pozo_openloto),
    ("polla", pozos_module.get_pozo_polla),
)


def _collect_pozos(
    include: bool,
    source_overrides: Mapping[str, str] | None = None,
    *,
    timeout: int = 20,
    retries: int = 3,
    only: str | None = None,
) -> tuple[dict[str, Any], ...]:
    if not include:
        return tuple()

    collected: list[dict[str, Any]] = []
    overrides = {k.lower(): v for k, v in (source_overrides or {}).items()}

    for name, fetcher in POZO_SOURCES:
        target_url = overrides.get(name)
        if target_url == "skip":
            continue

        if only and name != only:
            continue

        try:
            kw: dict[str, Any] = {}
            try:
                sig = inspect.signature(fetcher)
                params = sig.parameters
                has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                if "timeout" in params or has_var_kw:
                    kw["timeout"] = timeout
                if "retries" in params or has_var_kw:
                    kw["retries"] = retries
                if target_url and ("url" in params or has_var_kw):
                    kw["url"] = target_url
            except (ValueError, TypeError):
                if target_url:
                    kw["url"] = target_url
            payload = fetcher(**kw)
            if payload.get("montos"):
                payload["source_name"] = name
                collected.append(payload)
        except Exception as exc:
            LOGGER.warning("Pozo fetcher %s failed: %s", name, exc)

    return tuple(collected)


def _merge_pozos(
    collected: Sequence[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, Any], list[dict[str, Any]]]:
    """Merge pozos from multiple sources using a consensus strategy.

    Returns:
        - resolved: final jackpot amounts
        - provenance: details for the records
        - mismatches: list of categories where sources disagreed
    """
    if not collected:
        return {}, {}, []

    # Map of category -> {value: [source_name, ...]}
    votes: dict[str, dict[int, list[str]]] = {}

    for entry in collected:
        src_id = entry.get("source_name", entry.get("fuente", "unknown"))
        for cat, val in entry.get("montos", {}).items():
            if str(cat).lower().startswith("total"):
                continue
            v = int(val)
            votes.setdefault(cat, {}).setdefault(v, []).append(src_id)

    resolved: dict[str, int] = {}
    mismatches: list[dict[str, Any]] = []

    for cat, values in votes.items():
        # Sort by number of votes descending
        consensus = sorted(values.items(), key=lambda x: len(x[1]), reverse=True)
        winner_val, winners = consensus[0]

        # Find sources that are missing this category entirely
        responding_sources = {s for s_list in values.values() for s in s_list}
        missing_sources = [
            entry.get("source_name", "unknown")
            for entry in collected
            if entry.get("source_name", entry.get("fuente")) not in responding_sources
        ]

        if len(consensus) > 1:
            # Disagreement: calculate max relative deviation against winner
            max_dev = 0.0
            if winner_val > 0:
                for v in values.keys():
                    dev = abs(v - winner_val) / winner_val
                    max_dev = max(max_dev, dev)

            mismatches.append(
                {
                    "categoria": cat,
                    "consensus": {str(winner_val): winners},
                    "disagreeing": {str(v): s for v, s in consensus[1:]},
                    "max_deviation": round(max_dev, 4),
                    "missing_sources": missing_sources,
                }
            )
        elif missing_sources:
            # Consensus reached but some sources were missing the category
            mismatches.append(
                {
                    "categoria": cat,
                    "consensus": {str(winner_val): winners},
                    "disagreeing": {},
                    "missing_sources": missing_sources,
                }
            )
        resolved[cat] = winner_val

    # Provenance tracking
    provenance: dict[str, Any] = {}
    alternatives: list[dict[str, Any]] = []
    for idx, entry in enumerate(collected):
        descriptor = {
            "fuente": entry.get("fuente"),
            "fetched_at": entry.get("fetched_at"),
            "sha256": entry.get("sha256"),
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

    return resolved, provenance, mismatches


class _JSONLogStream:
    """Internal implementation of the LogStream protocol for JSONL files."""

    def __init__(self, log_path: Path) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = log_path.open("a", encoding="utf-8")
        self.correlation_id: str | None = None

    def __call__(self, payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        if self.correlation_id and "correlation_id" not in payload:
            payload["correlation_id"] = self.correlation_id
        payload = sanitize(payload)
        self.handle.write(json.dumps(payload, ensure_ascii=False))
        self.handle.write("\n")
        self.handle.flush()

    def set_correlation_id(self, value: str) -> None:
        self.correlation_id = value

    def close(self) -> None:
        self.handle.close()


def _init_log_stream(log_path: Path) -> LogStream:
    return _JSONLogStream(log_path)


def _compute_unchanged(
    previous_records: list[dict[str, Any]],
    *,
    sorteo: Any,
    fecha: Any,
    current_record: Mapping[str, Any],
) -> bool:
    """Return True if previous state contains same sorteo/fecha and identical content/amounts."""
    curr_prov = current_record.get("provenance", {}).get("pozos", {})
    curr_sha = curr_prov.get("primary", {}).get("sha256")

    for prev in previous_records:
        if prev.get("sorteo") == sorteo and prev.get("fecha") == fecha:
            # Try content-hash deduplication first (PROV-01)
            prev_prov = prev.get("provenance", {}).get("pozos", {})
            prev_sha = prev_prov.get("primary", {}).get("sha256")
            if curr_sha and prev_sha and curr_sha == prev_sha:
                LOGGER.debug("Provenance SHA-256 match for sorteo %s", sorteo)
                return True

            # Fallback to amount-based comparison for robustness
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
    confidence: str,
    decision_status: str,
    decision_reason: str,
    mismatches: list[dict[str, Any]],
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
            "confidence": confidence,
            "total_categories": len(merged_pozos),
            "mismatched_categories": len([m for m in mismatches if m.get("disagreeing")]),
            "reason": decision_reason,
        },
        "mismatches": mismatches,
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
    publish_reason: str,
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
        "publish_reason": publish_reason,
    }


def _run_ingestion_for_sources(
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
    mismatch_threshold: float,
    force_publish: bool,
    log_event: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    with span("ingestion_orchestration", log_event, attrs={"sources": requested_sources}):
        collected: list[dict[str, Any]] = []
        for name in requested_sources:
            loader = SOURCE_LOADERS.get(name)
            if not loader:
                # This should be caught by _normalize_sources but safety guard
                LOGGER.error("Source %s requested but not in registry", name)
                continue
            collected.extend(loader(True, source_overrides or {}, timeout=timeout, retries=retries))

    if not collected:
        raise RuntimeError(f"No sources returned data for {requested_sources}")

    merged_pozos, pozos_prov, mismatches = _merge_pozos(collected)
    mismatch_ratio = (
        len([m for m in mismatches if m.get("disagreeing")]) / len(merged_pozos)
        if merged_pozos
        else 0.0
    )
    max_deviation = max((m.get("max_deviation", 0.0) for m in mismatches), default=0.0)
    primary = collected[0]

    # Calculate confidence scoring (FEAT-01)
    expected_sources_count = 0
    for name in requested_sources:
        if name == "pozos":
            expected_sources_count += len(POZO_SOURCES)
        else:
            expected_sources_count += 1

    if len(collected) < expected_sources_count or mismatch_ratio > 0:
        confidence = "degraded"
    elif len(collected) == 1:
        confidence = "single_source"
    else:
        confidence = "full"

    sorteo = primary.get("sorteo")
    fecha = primary.get("fecha")

    record: dict[str, Any] = {
        "sorteo": sorteo,
        "fecha": fecha,
        "fuente": pozos_prov.get("primary", {}).get("fuente"),
        "confidence": confidence,
        "premios": [],
        "pozos_proximo": merged_pozos,
        "provenance": {"pozos": pozos_prov},
    }

    # Write raw JSON artifacts (one per source)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for entry in collected:
        # Compatibility: if it's the only source, use its name for the test
        if len(requested_sources) == 1:
            src_name = requested_sources[0]
        else:
            from urllib.parse import urlparse

            src_name = urlparse(entry.get("fuente", "")).netloc.replace(".", "_") or "source"
        _write_json(raw_dir / f"{src_name}.json", entry)

    previous_records = _load_previous_state(state_path)
    unchanged = _compute_unchanged(
        previous_records, sorteo=sorteo, fecha=fecha, current_record=record
    )

    _write_jsonl(normalized_path, [record])
    _write_jsonl(state_path, [record])

    if unchanged:
        decision_status = "skip"
        publish_flag = False
        publish_reason = "sorteo_fecha_and_amounts_unchanged"
    elif mismatch_ratio > mismatch_threshold or max_deviation > 0.10:
        decision_status = "quarantine"
        publish_flag = False
        if max_deviation > 0.10:
            publish_reason = f"max_deviation_{max_deviation:.2f}_exceeds_threshold_0.10"
        else:
            publish_reason = (
                f"mismatch_ratio_{mismatch_ratio:.2f}_exceeds_threshold_{mismatch_threshold}"
            )
    else:
        decision_status = "publish"
        publish_flag = True
        publish_reason = "updated_or_new_amounts"
    if force_publish and unchanged:
        decision_status = "publish_forced"
        publish_flag = True
        publish_reason = "force_publish_requested"

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
        confidence=confidence,
        decision_status=decision_status,
        decision_reason=publish_reason,
        mismatches=mismatches,
    )
    report_payload["api_version"] = API_VERSION
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
        publish_reason=publish_reason,
    )
    summary_payload["api_version"] = API_VERSION

    log_event(
        {
            "event": "pozos_enriched",
            "sources": requested_sources,
            "source_mode": (
                f"{requested_sources[0]}_only" if len(requested_sources) == 1 else "multi"
            ),
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
            "mismatch_ratio": mismatch_ratio,
            "prizes_changed": not unchanged,
            "reason": publish_reason,
        }
    )
    metric(
        "pipeline_run",
        log_event,
        kind="counter",
        value=1,
        tags={"decision": decision_status, "publish": publish_flag},
    )
    _write_json(summary_path, summary_payload)
    if decision_status == "quarantine":
        notify_quarantine(summary_payload, mismatches)
    else:
        notify_slack(summary_payload)
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
    log_event.set_correlation_id(run_id)
    set_correlation_id(run_id)
    log_event({"event": "pipeline_start", "run_id": run_id, "sources": sources})

    try:
        requested_sources = _normalize_sources(sources)

        return _run_ingestion_for_sources(
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
            mismatch_threshold=mismatch_threshold,
            force_publish=force_publish,
            log_event=log_event,
        )
    finally:
        closer = getattr(log_event, "close", None)
        if callable(closer):  # pragma: no branch - trivial guard
            closer()


# Populate source loaders for dynamic dispatch
SOURCE_LOADERS.update(
    {
        "pozos": _collect_pozos,
        "openloto": lambda *a, **k: _collect_pozos(*a, **k, only="openloto"),
        "polla": lambda *a, **k: _collect_pozos(*a, **k, only="polla"),
    }
)

__all__ = ["run_pipeline"]
