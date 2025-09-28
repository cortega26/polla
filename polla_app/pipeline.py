"""Orchestration for próximo pozo aggregation (resultadoslotochile + openloto)."""

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
from .sources import pozos as pozos_module

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SourceResult:
    """Result of parsing a single source."""

    name: str
    url: str
    metadata: FetchMetadata
    record: dict[str, Any]


SourceLoader = Callable[[str, int], SourceResult]


# No article loaders are configured; we operate in pozos-only mode.
SOURCE_LOADERS: dict[str, SourceLoader] = {}


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
        overrides = {k.lower(): v for k, v in (source_overrides or {}).items()}

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
                    prev_pozos = {k: int(v) for k, v in (prev.get("pozos_proximo", {}) or {}).items()}
                    curr_pozos = {k: int(v) for k, v in (record.get("pozos_proximo", {}) or {}).items()}
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
                "sources": {
                    "pozos": {"url": record["fuente"], "premios": 0}
                },
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
                    "reason": ("sorteo_fecha_and_amounts_unchanged" if unchanged else "updated_or_new_amounts"),
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

        results: list[SourceResult] = []
        failures: list[dict[str, Any]] = []

        for source_name in requested_sources:
            loader = SOURCE_LOADERS[source_name]

            # Build candidate URL list for this source
            candidate_urls: list[str] = []
            override = overrides.get(source_name)
            if override:
                candidate_urls.append(override)
            elif source_name == "24h":
                # Try several recent posts; we will attempt them in order until one parses successfully
                candidate_urls.extend(source_24h.list_24h_result_urls(limit=5, timeout=timeout))

            if not candidate_urls:
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

            loaded = False
            for url in candidate_urls:
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
                        # Log individual prize rows per category for this source
                        try:
                            log_event(
                                {
                                    "event": "premios_parsed",
                                    "source": source_name,
                                    "url": url,
                                    "sorteo": result.record.get("sorteo"),
                                    "categories": _category_map(result.record),
                                }
                            )
                        except Exception as exc:  # pragma: no cover - logging guard
                            LOGGER.debug("Failed to emit premios_parsed log: %s", exc)
                        results.append(result)
                        loaded = True
                        break
                if loaded:
                    break

            if not loaded:
                failures.append(
                    {
                        "source": source_name,
                        "url": candidate_urls[0] if candidate_urls else None,
                        "error": "All candidate URLs failed",
                    }
                )
                if fail_fast:
                    raise RuntimeError(f"Failed to load any URL for source '{source_name}'")

        if not results:
            # Produce quarantine summary and report instead of crashing the job
            _write_json(
                comparison_report_path,
                {
                    "run": {
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "sources": requested_sources,
                        "timeout": timeout,
                        "retries": retries,
                        "fail_fast": fail_fast,
                    },
                    "last_draw": {"sorteo": None, "fecha": None},
                    "decision": {
                        "status": "quarantine",
                        "reason": "No valid sources collected",
                        "total_categories": 0,
                        "mismatched_categories": 0,
                    },
                    "prizes_changed": False,
                    "mismatches": [],
                    "sources": {},
                    "failures": failures
                    or [
                        {"source": s, "url": None, "error": "No candidate URLs"}
                        for s in requested_sources
                    ],
                },
            )

            # Create empty normalized/state files and summary to keep downstream steps alive
            _write_jsonl(normalized_path, [])
            _write_jsonl(state_path, [])
            summary_payload = {
                "run_id": str(uuid.uuid4()),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "decision": {"status": "quarantine"},
                "prizes_changed": False,
                "normalized_path": str(normalized_path),
                "comparison_report": str(comparison_report_path),
                "raw_dir": str(raw_dir),
                "state_path": str(state_path),
                "publish": False,
            }
            _write_json(summary_path, summary_payload)
            log_event(
                {
                    "event": "pipeline_complete",
                    "run_id": summary_payload["run_id"],
                    "decision": "quarantine",
                    "mismatch_ratio": 0.0,
                    "prizes_changed": False,
                }
            )
            return summary_payload

        for result in results:
            _save_raw_outputs(raw_dir, result)

        category_views = {item.name: _category_map(item.record) for item in results}
        consensus_rows, mismatches, mismatch_ratio = _build_consensus(category_views)

        if not consensus_rows:
            raise RuntimeError("No prize categories available after parsing all sources")

        # Emit the consensus prize rows and mismatch stats to the structured log
        log_event(
            {
                "event": "premios_consensus",
                "rows": consensus_rows,
                "mismatches": mismatches,
                "mismatch_ratio": mismatch_ratio,
            }
        )

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
                    # Emit detailed jackpot categories to the structured log
                    log_event(
                        {
                            "event": "pozos_enriched",
                            "primary": pozos_prov.get("primary"),
                            "alternatives": pozos_prov.get("alternatives", []),
                            "categories": merged_pozos,
                        }
                    )

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

        final_summary: dict[str, Any] = {
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

        _write_json(summary_path, final_summary)

        log_event(
            {
                "event": "pipeline_complete",
                "run_id": run_id,
                "decision": decision_payload["status"],
                "mismatch_ratio": mismatch_ratio,
                "prizes_changed": prizes_changed,
            }
        )

        return final_summary
    finally:
        closer = getattr(log_event, "close", None)
        if callable(closer):  # pragma: no branch - trivial guard
            closer()


__all__ = ["run_pipeline", "SOURCE_LOADERS", "SourceResult"]
