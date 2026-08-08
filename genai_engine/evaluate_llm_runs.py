"""
Aggregate telemetry for cross-LLM comparison.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
TELEMETRY_DIR = BASE_DIR / "telemetry"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _avg(values: List[float]) -> float:
    return round(mean(values), 4) if values else 0.0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare LLM generation telemetry")
    p.add_argument("--run-id", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    bundle_path = TELEMETRY_DIR / f"bundle_metrics_{args.run_id}.jsonl"
    scenario_path = TELEMETRY_DIR / f"scenario_metrics_{args.run_id}.jsonl"
    attempt_path = TELEMETRY_DIR / f"llm_attempts_{args.run_id}.jsonl"

    bundles = _read_jsonl(bundle_path)
    scenarios = _read_jsonl(scenario_path)
    attempts = _read_jsonl(attempt_path)

    by_llm: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "bundle_durations": [],
        "scenario_durations": [],
        "validation_issue_count": 0,
        "bundle_count": 0,
        "failed_bundle_count": 0,
        "scenario_count": 0,
        "scenario_fallback_count": 0,
        "schema_fallback_count": 0,
        "avg_quality_values": [],
        "attempt_count": 0,
        "attempt_failures": 0,
        "attempt_durations": [],
        "rag_counts": [],
        "parse_errors": 0,
        "http_errors": 0,
        "timeout_errors": 0,
    })

    for row in bundles:
        llm = row.get("llm_key", "unknown")
        agg = by_llm[llm]
        if row.get("status") == "failed":
            agg["failed_bundle_count"] += 1
            continue
        agg["bundle_count"] += 1
        agg["bundle_durations"].append(float(row.get("bundle_duration_seconds", 0.0)))
        agg["validation_issue_count"] += int(row.get("bundle_validation_issue_count", row.get("validation_issue_count", 0)))
        agg["scenario_fallback_count"] += int(row.get("scenario_fallback_count", 0))
        agg["schema_fallback_count"] += int(row.get("schema_fallback_count", 0))
        agg["avg_quality_values"].append(float(row.get("avg_quality_score", 0.0)))

    for row in scenarios:
        llm = row.get("llm_key", "unknown")
        agg = by_llm[llm]
        agg["scenario_count"] += 1
        agg["scenario_durations"].append(float(row.get("scenario_duration_seconds", 0.0)))
        agg["rag_counts"].append(float(row.get("rag_count", 0.0)))
        if row.get("used_llm_fallback"):
            agg["scenario_fallback_count"] += 1
        if row.get("used_schema_fallback"):
            agg["schema_fallback_count"] += 1

    for row in attempts:
        llm = row.get("llm_key", "unknown")
        agg = by_llm[llm]
        agg["attempt_count"] += 1
        agg["attempt_durations"].append(float(row.get("duration_seconds", 0.0)))
        if not row.get("success", False):
            agg["attempt_failures"] += 1
        err = str(row.get("error_type") or "")
        if err == "parse_error":
            agg["parse_errors"] += 1
        elif err == "http_error":
            agg["http_errors"] += 1
        elif err == "timeout":
            agg["timeout_errors"] += 1

    out_rows = []
    for llm, agg in sorted(by_llm.items()):
        out_rows.append({
            "llm_key": llm,
            "bundle_count": agg["bundle_count"],
            "failed_bundle_count": agg["failed_bundle_count"],
            "scenario_count": agg["scenario_count"],
            "avg_bundle_seconds": _avg(agg["bundle_durations"]),
            "avg_scenario_seconds": _avg(agg["scenario_durations"]),
            "avg_attempt_seconds": _avg(agg["attempt_durations"]),
            "avg_rag_examples": _avg(agg["rag_counts"]),
            "avg_quality_score": _avg(agg["avg_quality_values"]),
            "validation_issue_count": agg["validation_issue_count"],
            "scenario_fallback_count": agg["scenario_fallback_count"],
            "schema_fallback_count": agg["schema_fallback_count"],
            "attempt_count": agg["attempt_count"],
            "attempt_failures": agg["attempt_failures"],
            "parse_errors": agg["parse_errors"],
            "http_errors": agg["http_errors"],
            "timeout_errors": agg["timeout_errors"],
        })

    json_path = TELEMETRY_DIR / f"llm_comparison_{args.run_id}.json"
    csv_path = TELEMETRY_DIR / f"llm_comparison_{args.run_id}.csv"
    json_path.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        if out_rows:
            writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            writer.writeheader()
            writer.writerows(out_rows)
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
