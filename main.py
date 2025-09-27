from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Any

from polla_app.sources.h24 import list_24h_result_urls, parse_24h_draw
from polla_app.sources.t13 import parse_t13_draw
from polla_app.sources.pozos import get_pozo_openloto, get_pozo_resultadosloto


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False))
        f.write("\n")


def run_pipeline(
    sources: list[str],
    retries: int,
    timeout: int,
    fail_fast: bool,
    raw_dir: Path,
    normalized: Path,
    comparison_report: Path,
    summary: Path,
    state_file: Path,
    log_file: Path,
    mismatch_threshold: float,
) -> dict[str, Any]:
    ts = datetime.now(timezone.utc).isoformat()
    used_sources: list[str] = []

    raw_dir.mkdir(parents=True, exist_ok=True)

    # Collect records from explicit URLs in sources
    records: list[tuple[str, dict[str, Any], str]] = []  # (source_tag, record, url)
    for s in sources:
        if not (s.startswith("http://") or s.startswith("https://")):
            continue
        try:
            if "24horas.cl" in s and "/site/tag/port/" in s:
                used_sources.append("24horas-index")
                urls = list_24h_result_urls(s)
                _dump(raw_dir / "24h_index_urls.json", urls)
                if urls:
                    rec = parse_24h_draw(urls[0])
                    records.append(("24horas", rec, urls[0]))
            elif "24horas.cl" in s:
                used_sources.append("24horas-article")
                rec = parse_24h_draw(s)
                records.append(("24horas", rec, s))
            elif "t13.cl" in s:
                used_sources.append("t13-article")
                rec = parse_t13_draw(s)
                records.append(("t13", rec, s))
        except Exception as e:
            if fail_fast:
                raise
            name = "err_explicit_source.json"
            _dump(raw_dir / name, {"error": str(e), "source": s})

    # If none provided explicitly, fall back to 24h index latest
    if not records:
        latest_url = None
        try:
            used_sources.append("24horas-index")
            urls = list_24h_result_urls()
            _dump(raw_dir / "24h_index_urls.json", urls)
            latest_url = urls[0] if urls else None
        except Exception as e:
            if fail_fast:
                raise
            _dump(raw_dir / "errors_24h_index.json", {"error": str(e)})
        if latest_url:
            try:
                used_sources.append("24horas-article")
                rec = parse_24h_draw(latest_url)
                records.append(("24horas", rec, latest_url))
            except Exception as e:
                if fail_fast:
                    raise
                _dump(raw_dir / "errors_24h_article.json", {"error": str(e), "url": latest_url})

    # Fetch pozos from aggregators (best-effort)
    pozos_open = {}
    pozos_res = {}
    if any("openloto" in s for s in sources) or "all" in sources:
        used_sources.append("openloto")
        try:
            pozos_open = get_pozo_openloto()
            _dump(raw_dir / "pozos_openloto.json", pozos_open)
        except Exception as e:
            if fail_fast:
                raise
            _dump(raw_dir / "errors_openloto.json", {"error": str(e)})
    if any("resultadosloto" in s for s in sources) or "all" in sources:
        used_sources.append("resultadoslotochile")
        try:
            pozos_res = get_pozo_resultadosloto()
            _dump(raw_dir / "pozos_resultadosloto.json", pozos_res)
        except Exception as e:
            if fail_fast:
                raise
            _dump(raw_dir / "errors_resultadosloto.json", {"error": str(e)})

    # Choose a primary record (first one)
    record: dict[str, Any] | None = records[0][1] if records else None

    if not record:
        raise RuntimeError("No valid sources were collected; aborting run")

    # Attach pozos if any
    pozos_combined = {}
    pozos_combined.update(pozos_open)
    for k, v in pozos_res.items():
        if k not in pozos_combined:
            pozos_combined[k] = v
    if pozos_combined:
        record["pozos_proximo"] = pozos_combined

    # Persist normalized JSONL
    _append_jsonl(Path(normalized), record)

    # Very simple comparison report (placeholder)
    # Build comparison report across records (if >1)
    comparison: dict[str, Any] = {
        "source_urls": used_sources,
        "pozos_openloto_keys": sorted(list(pozos_open.keys())),
        "pozos_resultadosloto_keys": sorted(list(pozos_res.keys())),
        "mismatch_threshold": mismatch_threshold,
    }

    mismatch = False
    details: list[dict[str, Any]] = []
    if len(records) >= 2:
        # Compare first two records by category
        tag_a, rec_a, url_a = records[0]
        tag_b, rec_b, url_b = records[1]

        def map_p(remios: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
            out: dict[str, dict[str, int]] = {}
            for p in remios or []:
                cat = re.sub(r"\s+", " ", str(p.get("categoria", "")).strip())
                out[cat] = {
                    "premio_clp": int(p.get("premio_clp") or 0),
                    "ganadores": int(p.get("ganadores") or 0),
                }
            return out

        a = map_p(rec_a.get("premios", []))
        b = map_p(rec_b.get("premios", []))
        common = sorted(set(a.keys()) & set(b.keys()))
        mismatches = 0
        for cat in common:
            if a[cat] != b[cat]:
                mismatches += 1
                details.append({"categoria": cat, "a": a[cat], "b": b[cat]})
        ratio = (mismatches / max(1, len(common))) if common else 0.0
        mismatch = mismatches > 0 and ratio >= mismatch_threshold
        comparison.update(
            {
                "compared_sources": [url_a, url_b],
                "categories_compared": len(common),
                "mismatches": mismatches,
                "mismatch_ratio": ratio,
                "details": details,
                "mismatch": mismatch,
            }
        )
    else:
        comparison["mismatch"] = False
    _dump(Path(comparison_report), comparison)

    # State/logs
    _append_jsonl(Path(state_file), {"ts": ts, "used_sources": used_sources})
    _append_jsonl(Path(log_file), {"ts": ts, "msg": "run ok", "sources": used_sources})

    # Summary
    summary_payload = {
        "ts": ts,
        "used_sources": used_sources,
        "latest_url": latest_url,
        "premios_count": len(record.get("premios", [])),
        "has_pozos": bool(pozos_combined),
    }
    _dump(Path(summary), summary_payload)
    return summary_payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="all")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--no-fail-fast", action="store_true")
    ap.add_argument("--raw-dir", default="artifacts/raw")
    ap.add_argument("--normalized", default="artifacts/normalized.jsonl")
    ap.add_argument("--comparison-report", default="artifacts/comparison_report.json")
    ap.add_argument("--summary", default="artifacts/run_summary.json")
    ap.add_argument("--state-file", default="pipeline_state/last_run.jsonl")
    ap.add_argument("--log-file", default="logs/run.jsonl")
    ap.add_argument("--mismatch-threshold", type=float, default=0.2)
    args = ap.parse_args()

    # Support env var override for sources list
    alt_env = os.getenv("ALT_SOURCE_URLS", "").strip()
    # We accept either keywords (all, 24horas, openloto, resultadosloto) or URLs from env.
    if args.sources == "all" and alt_env:
        sources = [s.strip() for s in re_split(alt_env) if s.strip()]
    else:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    run_pipeline(
        sources=sources,
        retries=args.retries,
        timeout=args.timeout,
        fail_fast=not args.no_fail_fast,
        raw_dir=Path(args.raw_dir),
        normalized=Path(args.normalized),
        comparison_report=Path(args.comparison_report),
        summary=Path(args.summary),
        state_file=Path(args.state_file),
        log_file=Path(args.log_file),
        mismatch_threshold=args.mismatch_threshold,
    )


def re_split(s: str) -> list[str]:
    # split on comma or newline
    return [p for chunk in s.split("\n") for p in chunk.split(",")]


if __name__ == "__main__":
    main()
