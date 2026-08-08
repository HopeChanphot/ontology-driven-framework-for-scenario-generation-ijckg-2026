"""Merge live-LLM recovery rows back into a paper-120 scenario set.

The script preserves the original frozen files and writes a new recovered
scenario set. Original live rows are kept; fallback/non-live rows are replaced
only when a matching live row exists in the recovery output root.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Paper120Condition:
    model: str
    method: str
    scenario_file: Path


FINAL_CONDITIONS = (
    Paper120Condition("qwen2_5_7b", "prompt_only", PROJECT_ROOT / "output/prompt_only_paper_120_qwen2_5_7b/20260701_220647/scenarios_prompt_only.jsonl"),
    Paper120Condition("qwen3_8b", "prompt_only", PROJECT_ROOT / "output/prompt_only_120_qwen3_8b/20260701_235448/scenarios_prompt_only.jsonl"),
    Paper120Condition("mistral_7b", "prompt_only", PROJECT_ROOT / "output/prompt_only_120_mistral_7b/20260703_013152/scenarios_prompt_only.jsonl"),
    Paper120Condition("qwen2_5_7b", "prompt_rag", PROJECT_ROOT / "output/psq_sco_120_qwen2_5_7b/20260630_205124/qwen2_5_7b/scenarios_prompt_rag.jsonl"),
    Paper120Condition("qwen3_8b", "prompt_rag", PROJECT_ROOT / "output/psq_sco_120_prompt_rag_qwen3_8b/20260702_025346/scenarios.jsonl"),
    Paper120Condition("mistral_7b", "prompt_rag", PROJECT_ROOT / "output/psq_sco_120_prompt_rag_mistral_7b_fixed/20260703_134043/scenarios.jsonl"),
    Paper120Condition("qwen2_5_7b", "ontology_prompt_rag", PROJECT_ROOT / "output/psq_sco_120_qwen2_5_7b/20260630_205124/qwen2_5_7b/scenarios_ontology_prompt_rag.jsonl"),
    Paper120Condition("qwen3_8b", "ontology_prompt_rag", PROJECT_ROOT / "output/psq_sco_120_ontology_prompt_rag_qwen3_8b/20260702_184521/scenarios.jsonl"),
    Paper120Condition("mistral_7b", "ontology_prompt_rag", PROJECT_ROOT / "output/psq_sco_120_ontology_prompt_rag_mistral_7b/20260704_000204/scenarios.jsonl"),
    Paper120Condition("qwen2_5_7b", "ontology_text_rag", PROJECT_ROOT / "output/psq_sco_120_ontology_text_rag_chroma_qwen2_5_7b_light/20260708_211811/scenarios_ontology_text_rag.jsonl"),
    Paper120Condition("qwen3_8b", "ontology_text_rag", PROJECT_ROOT / "output/psq_sco_120_ontology_text_rag_chroma_qwen3_8b_compact/20260709_141125/scenarios_ontology_text_rag.jsonl"),
    Paper120Condition("mistral_7b", "ontology_text_rag", PROJECT_ROOT / "output/psq_sco_120_ontology_text_rag_chroma_mistral_7b_compact/20260710_012836/scenarios_ontology_text_rag.jsonl"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge live recovery outputs into a new paper-120 scenario set.")
    parser.add_argument("--recovery-root", type=Path, default=PROJECT_ROOT / "output" / "paper120_live_llm_recovery_runs")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "output" / "paper120_live_recovered_final")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir / run_id
    scenario_out = out_dir / "generated_scenarios"
    scenario_out.mkdir(parents=True, exist_ok=True)

    recovery_rows = _load_recovery_rows(args.recovery_root)
    manifest_rows: List[Dict[str, Any]] = []
    replacement_rows: List[Dict[str, Any]] = []
    remaining_rows: List[Dict[str, Any]] = []

    for condition in FINAL_CONDITIONS:
        original_rows = list(_read_jsonl(condition.scenario_file))
        recovered_rows: List[Dict[str, Any]] = []
        replacements = 0
        original_live_kept = 0
        for row in original_rows:
            case_id = _case_id(row)
            key = (condition.model, condition.method, case_id)
            replacement = recovery_rows.get(key)
            if replacement and _is_live(replacement):
                recovered_rows.append(replacement)
                replacements += 1
                replacement_rows.append(
                    {
                        "model": condition.model,
                        "method": condition.method,
                        "case_id": case_id,
                        "replacement_source": replacement.get("_recovery_source_file", ""),
                    }
                )
            else:
                recovered_rows.append(row)
                if _is_live(row):
                    original_live_kept += 1
                else:
                    remaining_rows.append(
                        {
                            "model": condition.model,
                            "method": condition.method,
                            "case_id": case_id,
                            "used_live_llm": bool(row.get("used_live_llm")),
                            "used_fallback": bool(row.get("used_fallback")),
                            "validation_passed": bool(row.get("validation_passed")),
                            "original_source": str(condition.scenario_file),
                        }
                    )
        output_file = scenario_out / f"{condition.model}__{condition.method}__paper_120_live_recovered.jsonl"
        _write_jsonl(output_file, recovered_rows)
        live_count = sum(1 for row in recovered_rows if _is_live(row))
        fallback_count = sum(1 for row in recovered_rows if row.get("used_fallback"))
        manifest_rows.append(
            {
                "model": condition.model,
                "method": condition.method,
                "output_file": str(output_file),
                "row_count": len(recovered_rows),
                "live_rows": live_count,
                "fallback_rows": fallback_count,
                "original_live_rows_kept": original_live_kept,
                "recovery_replacements": replacements,
                "remaining_non_live_rows": len(recovered_rows) - live_count,
            }
        )

    _write_csv(out_dir / "paper120_live_recovered_manifest.csv", manifest_rows)
    _write_csv(out_dir / "recovered_replacements.csv", replacement_rows)
    _write_csv(out_dir / "remaining_non_live_cases.csv", remaining_rows)
    summary = {
        "created_at": datetime.now().isoformat(),
        "recovery_root": str(args.recovery_root),
        "generated_scenarios_dir": str(scenario_out),
        "total_rows": sum(int(row["row_count"]) for row in manifest_rows),
        "live_rows": sum(int(row["live_rows"]) for row in manifest_rows),
        "remaining_non_live_rows": sum(int(row["remaining_non_live_rows"]) for row in manifest_rows),
        "recovery_replacements": len(replacement_rows),
        "output_files": {
            "manifest_csv": str(out_dir / "paper120_live_recovered_manifest.csv"),
            "recovered_replacements_csv": str(out_dir / "recovered_replacements.csv"),
            "remaining_non_live_cases_csv": str(out_dir / "remaining_non_live_cases.csv"),
        },
    }
    (out_dir / "merge_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _load_recovery_rows(recovery_root: Path) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    rows: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    if not recovery_root.exists():
        return rows
    for path in sorted(recovery_root.rglob("scenarios*.jsonl")):
        for row in _read_jsonl(path):
            model = str(row.get("llm_key") or row.get("model", {}).get("key") or "")
            method = str(row.get("mode") or "")
            case_id = _case_id(row)
            if not model or not method or not case_id:
                continue
            row["_recovery_source_file"] = str(path)
            key = (model, method, case_id)
            if key not in rows or (_is_live(row) and not _is_live(rows[key])):
                rows[key] = row
    return rows


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            clean = dict(row)
            clean.pop("_recovery_source_file", None)
            handle.write(json.dumps(clean, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _case_id(row: Dict[str, Any]) -> str:
    case = row.get("case") if isinstance(row.get("case"), dict) else {}
    return str(case.get("case_id") or "")


def _is_live(row: Dict[str, Any]) -> bool:
    return bool(row.get("used_live_llm")) and bool(row.get("scenario"))


if __name__ == "__main__":
    main()
