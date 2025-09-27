"""End-to-end orchestration for the alternative-source ingestion workflow."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from .net import FetchMetadata, fetch_html
from .sources import _24h as source_24h
from .sources import pozos as pozos_module
from .sources import t13 as source_t13

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SourceResult:
    """Result of parsing a single source."""

    name: str
    url: str
    metadata: FetchMetadata
    record: dict[str, Any]


SourceLoader = Callable[[str, int], SourceResult]


def _load_t13(url: str, timeout: int) -> SourceResult:
    metadata = fetch_html(url, ua=source_t13.DEFAULT_UA, timeout=timeout)
    record = source_t13.parse_draw_from_metadata(metadata, source="t13")
    if not record.get("premios"):
        raise RuntimeError(f"No se encontraron premios en {url}")
    return SourceResult(name="t13", url=url, metadata=metadata, record=record)


def _load_24h(url: str, timeout: int) -> SourceResult:
    metadata = fetch_html(url, ua=source_24h.DEFAULT_UA, timeout=timeout)
    record = source_t13.parse_draw_from_metadata(metadata, source="24horas")
    if not record.get("premios"):
        LOGGER.debug("Retrying %s with T13 user-agent after empty premio list", url)
        metadata = fetch_html(url, ua=source_t13.DEFAULT_UA, timeout=timeout)
        record = source_t13.parse_draw_from_metadata(metadata, source="24horas")
    if not record.get("premios"):
        raise RuntimeError(f"No se encontraron premios en {url}")
    return SourceResult(name="24h", url=url, metadata=metadata, record=record)


SOURCE_LOADERS: dict[str, SourceLoader] = {
    "t13": _load_t13,
    "24h": _load_24h,
}


def _normalise_sources(requested: Sequence[str]) -> list[str]:
    if "all" in {item.lower() for item in requested}:
        return sorted(SOURCE_LOADERS.keys())
    normalised: list[str] = []
    for item in requested:
        key = item.lower()
        if key not in SOURCE_LOADERS:
            raise ValueError(f"Unsupported source '{item}'. Available: {', '.join(SOURCE_LOADERS)}")
        if key not in normalised:
            normalised.append(key)
    return normalised


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _save_raw_outputs(raw_dir: Path, result: SourceResult) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    html_path = raw_dir / f"{result.name}.html"
    html_path.write_text(result.metadata.html, encoding="utf-8")
    json_path = raw_dir / f"{result.name}.json"
    json_path.write_text(json.dumps(result.record, ensure_ascii=False, indent=2), encoding="utf-8")


def _category_map(record: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for item in record.get("premios", []) or []:
        categoria = item.get("categoria")
        if categoria:
            mapping[categoria] = {
                "premio_clp": item.get("premio_clp", 0),
                "ganadores": item.get("ganadores", 0),
            }
    return mapping


def _build_consensus(
    records: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float]:
    categories: set[str] = set()
    for data in records.values():
        categories.update(data.keys())

    mismatches: list[dict[str, Any]] = []
    consensus_rows: list[dict[str, Any]] = []

    for categoria in sorted(categories):
        values: dict[str, tuple[int, int]] = {}
        for source_name, source_rows in records.items():
            if categoria in source_rows:
                row = source_rows[categoria]
                values[source_name] = (int(row.get("premio_clp", 0)), int(row.get("ganadores", 0)))

        if not values:
            continue

        counter = Counter(values.values())
        majority_value, count = counter.most_common(1)[0]
        consensus_rows.append(
            {
                "categoria": categoria,
                "premio_clp": majority_value[0],
                "ganadores": majority_value[1],
            }
        )

        disagreeing = {
            source: {"premio_clp": val[0], "ganadores": val[1]}
            for source, val in values.items()
            if val != majority_value
        }
        missing_sources = [src for src in records if src not in values]

        if disagreeing or missing_sources:
            mismatches.append(
                {
                    "categoria": categoria,
                    "consensus": {
                        "premio_clp": majority_value[0],
                        "ganadores": majority_value[1],
                        "support": count,
                    },
                    "disagreeing": disagreeing,
                    "missing_sources": missing_sources,
                }
            )

    mismatch_ratio = 0.0
    if consensus_rows:
        mismatch_ratio = len(mismatches) / len(consensus_rows)

    return consensus_rows, mismatches, mismatch_ratio


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


def _compare_with_previous(current: dict[str, Any], previous: Iterable[dict[str, Any]]) -> bool:
    """Return True if prizes changed compared to the last known record."""

    current_sorteo = current.get("sorteo")
    if current_sorteo is None:
        return True

    def _normalise_prizes(record: Mapping[str, Any]) -> list[tuple[str, int, int]]:
        rows = [
            (
                item.get("categoria", ""),
                int(item.get("premio_clp", 0)),
                int(item.get("ganadores", 0)),
            )
            for item in record.get("premios", []) or []
        ]
        return sorted(rows)

    for candidate in previous:
        if candidate.get("sorteo") != current_sorteo:
            continue
        if _normalise_prizes(candidate) == _normalise_prizes(current):
            return False
    return True


def _collect_pozos(include: bool) -> tuple[dict[str, Any], ...]:
    if not include:
        return tuple()

    collected: list[dict[str, Any]] = []
    for fetcher in (pozos_module.get_pozo_openloto, pozos_module.get_pozo_resultadosloto):
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
            merged.setdefault(categoria, int(monto))
        descriptor = {
            "fuente": entry.get("fuente"),
            "fetched_at": entry.get("fetched_at"),
            "user_agent": entry.get("user_agent"),
            "estimado": entry.get("estimado", True),
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
) -> dict[str, Any]:
    """Run the ingestion + validation pipeline and emit artefacts."""

    log_event = _init_log_stream(log_path)
    run_id = str(uuid.uuid4())
    log_event({"event": "pipeline_start", "run_id": run_id, "sources": sources})

    try:
        requested_sources = _normalise_sources(sources)
        overrides = {k.lower(): v for k, v in (source_overrides or {}).items()}

        results: list[SourceResult] = []
        failures: list[dict[str, Any]] = []

        for source_name in requested_sources:
            loader = SOURCE_LOADERS[source_name]
            url = overrides.get(source_name)
            if not url and source_name == "24h":
                discovered = source_24h.list_24h_result_urls(limit=1, timeout=timeout)
                if discovered:
                    url = discovered[0]
            if not url:
                message = f"No URL configured for source '{source_name}'"
                log_event(
                    {
                        "event": "source_missing_url",
                        "source": source_name,
                        "message": message,
                    }
                )
                if fail_fast:
                    raise RuntimeError(message)
                failures.append(
                    {
                        "source": source_name,
                        "url": None,
                        "error": "Source skipped: missing URL",
                    }
                )
                continue

            attempt = 0
            while True:
                try:
                    result = loader(url, timeout)
                except Exception as exc:  # pragma: no cover - retry logic
                    attempt += 1
                    log_event(
                        {
                            "event": "source_error",
                            "source": source_name,
                            "url": url,
                            "attempt": attempt,
                            "message": str(exc),
                        }
                    )
                    if attempt >= retries:
                        failures.append({"source": source_name, "url": url, "error": str(exc)})
                        if fail_fast:
                            raise
                        break
                    time.sleep(min(2 * attempt, 10))
                    continue
                else:
                    log_event(
                        {
                            "event": "source_success",
                            "source": source_name,
                            "url": url,
                            "sorteo": result.record.get("sorteo"),
                            "premio_rows": len(result.record.get("premios", []) or []),
                        }
                    )
                    results.append(result)
                    break

        if not results:
            raise RuntimeError("No valid sources were collected; aborting run")

        for result in results:
            _save_raw_outputs(raw_dir, result)

        category_views = {item.name: _category_map(item.record) for item in results}
        consensus_rows, mismatches, mismatch_ratio = _build_consensus(category_views)

        if not consensus_rows:
            raise RuntimeError("No prize categories available after parsing all sources")

        last_draw = {
            "sorteo": max((res.record.get("sorteo") or 0) for res in results),
            "fecha": None,
        }
        fecha_values = [
            res.record.get("fecha") for res in results if res.record.get("fecha") is not None
        ]
        fechas: list[str] = [str(value) for value in fecha_values if value is not None]
        if fechas:
            last_draw["fecha"] = max(fechas)

        selected_source = results[0]
        consensus_record: dict[str, Any] = {
            "sorteo": last_draw["sorteo"],
            "fecha": last_draw["fecha"],
            "fuente": selected_source.url,
            "premios": consensus_rows,
            "provenance": {
                "run_id": run_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": [
                    {
                        "source": item.name,
                        "url": item.url,
                        "html_sha256": item.metadata.sha256,
                        "fetched_at": item.metadata.fetched_at.isoformat(),
                        "user_agent": item.metadata.user_agent,
                    }
                    for item in results
                ],
            },
        }

        if include_pozos:
            collected = _collect_pozos(include=True)
            if collected:
                merged_pozos, pozos_prov = _merge_pozos(collected)
                if merged_pozos:
                    consensus_record["pozos_proximo"] = merged_pozos
                    consensus_record["provenance"]["pozos"] = pozos_prov

        previous_records = _load_previous_state(state_path)
        prizes_changed = _compare_with_previous(consensus_record, previous_records)

        _write_jsonl(normalized_path, [consensus_record])
        _write_json(summary_path, {"status": "pending"})  # overwritten below

        state_path.parent.mkdir(parents=True, exist_ok=True)
        _write_jsonl(state_path, [consensus_record])

        total_categories = len(consensus_rows)
        mismatch_count = len(mismatches)

        if mismatch_count == 0:
            decision: dict[str, Any] = {
                "status": "publish",
                "reason": "No mismatches detected",
            }
        elif mismatch_ratio <= mismatch_threshold:
            decision = {
                "status": "publish_with_warnings",
                "reason": "Minor mismatches tolerated",
                "mismatch_ratio": mismatch_ratio,
            }
        else:
            decision = {
                "status": "quarantine",
                "reason": "Mismatch ratio exceeds threshold",
                "mismatch_ratio": mismatch_ratio,
            }

        report_payload: dict[str, Any] = {
            "run": {
                "id": run_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": requested_sources,
                "timeout": timeout,
                "retries": retries,
                "fail_fast": fail_fast,
            },
            "last_draw": last_draw,
            "decision": {
                **decision,
                "total_categories": total_categories,
                "mismatched_categories": mismatch_count,
            },
            "prizes_changed": prizes_changed,
            "mismatches": mismatches,
            "sources": {
                item.name: {
                    "url": item.url,
                    "sorteo": item.record.get("sorteo"),
                    "fecha": item.record.get("fecha"),
                    "premios": len(item.record.get("premios", []) or []),
                }
                for item in results
            },
            "failures": failures,
        }

        _write_json(comparison_report_path, report_payload)

        decision_payload = cast(dict[str, Any], report_payload["decision"])

        summary_payload: dict[str, Any] = {
            "run_id": run_id,
            "generated_at": report_payload["run"]["generated_at"],
            "decision": decision_payload,
            "prizes_changed": prizes_changed,
            "normalized_path": str(normalized_path),
            "comparison_report": str(comparison_report_path),
            "raw_dir": str(raw_dir),
            "state_path": str(state_path),
            "publish": str(decision_payload.get("status", "")).startswith("publish"),
        }

        _write_json(summary_path, summary_payload)

        log_event(
            {
                "event": "pipeline_complete",
                "run_id": run_id,
                "decision": summary_payload["decision"]["status"],
                "mismatch_ratio": mismatch_ratio,
                "prizes_changed": prizes_changed,
            }
        )

        return summary_payload
    finally:
        closer = getattr(log_event, "close", None)
        if callable(closer):  # pragma: no branch - trivial guard
            closer()


__all__ = ["run_pipeline", "SOURCE_LOADERS", "SourceResult"]
