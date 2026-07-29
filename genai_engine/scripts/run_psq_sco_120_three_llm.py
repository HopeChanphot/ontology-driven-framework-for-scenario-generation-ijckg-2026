"""Incremental runner for the PSQ-SCO 120-case, two-mode, three-LLM batch.

This script intentionally wraps the existing PSQSCOGenerationEngine instead of
changing the public CLI. It writes every generated result immediately so long
local Ollama runs can be monitored and resumed manually if needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generation_progress import ProgressTracker, run_with_heartbeat
from psq_sco_generation.cases import build_paper_120_cases, case_set_summary, export_case_manifest
from psq_sco_generation.engine import PSQSCOGenerationEngine
from psq_sco_generation.models import ENGINE_MODES, LIGHTWEIGHT_MODEL_PROFILES
from psq_sco_generation.ontology import DEFAULT_ONTOLOGY_PATH


DEFAULT_MODELS = ("qwen2_5_7b", "qwen3_8b", "mistral_7b")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _load_completed_keys(progress_path: Path) -> set[str]:
    completed: set[str] = set()
    if not progress_path.exists():
        return completed
    with progress_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            completed.add(row["result_key"])
    return completed


def _modes(mode_arg: str) -> List[str]:
    return list(ENGINE_MODES) if mode_arg == "both" else [mode_arg]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PSQ-SCO paper_120 cases with both generation modes and three local LLMs.")
    parser.add_argument("--ontology-path", type=Path, default=DEFAULT_ONTOLOGY_PATH)
    parser.add_argument("--output-root", type=Path, default=Path("output") / "psq_sco_120_three_llm_incremental")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Resume or continue inside an existing timestamped run directory, e.g. output/psq_sco_120_qwen2_5_7b/20260630_205124.",
    )
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS), choices=sorted(LIGHTWEIGHT_MODEL_PROFILES))
    parser.add_argument("--mode", choices=[*ENGINE_MODES, "both"], default="both")
    parser.add_argument("--retrieval-mode", default="ENGLISH_GLOBAL")
    parser.add_argument("--language-mode", choices=["en", "th"], default="en")
    parser.add_argument("--limit", type=int, default=0, help="0 means all 120 cases.")
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip result keys already listed in progress.jsonl.")
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress bar and heartbeat messages.")
    parser.add_argument("--progress-heartbeat-seconds", type=int, default=30, help="Seconds between long-call heartbeat messages.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started_at = datetime.now()
    if args.run_dir is not None:
        run_root = args.run_dir
        run_id = run_root.name
        args.resume = True
    else:
        run_id = started_at.strftime("%Y%m%d_%H%M%S")
        run_root = args.output_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    cases = build_paper_120_cases(retrieval_mode=args.retrieval_mode, language_mode=args.language_mode)
    if args.limit > 0:
        cases = cases[: args.limit]

    if not (run_root / "case_manifest.json").exists():
        export_case_manifest(cases, run_root / "case_manifest.json", run_root / "case_manifest.csv")
    progress_path = run_root / "progress.jsonl"
    completed = _load_completed_keys(progress_path) if args.resume else set()
    modes = _modes(args.mode)
    total_expected = len(cases) * len(modes) * len(args.models)

    summary_base: Dict[str, Any] = {
        "run_id": run_id,
        "engine": "psq_sco_generation_incremental_batch",
        "started_at": started_at.isoformat(),
        "output_root": str(run_root),
        "ontology_path": str(args.ontology_path),
        "case_set": "paper_120",
        "case_count": len(cases),
        "mode": args.mode,
        "modes": modes,
        "models": args.models,
        "dry_run": args.dry_run,
        "skip_rag": args.skip_rag,
        "total_expected_results": total_expected,
        "case_set_summary": case_set_summary(cases),
    }
    completed_count_at_start = _count_jsonl(progress_path)
    _write_json(run_root / "batch_status.json", {**summary_base, "completed_results": completed_count_at_start})

    engine = PSQSCOGenerationEngine(ontology_path=args.ontology_path, use_rag=not args.skip_rag)
    started_models: Dict[str, str] = {}
    progress = ProgressTracker(total_expected, label="psq_sco_120", enabled=not args.no_progress, current=completed_count_at_start)

    for model_key in args.models:
        started_models[model_key] = datetime.now().isoformat()
        for case in cases:
            seed = case.build_seed()
            for mode in modes:
                result_key = f"{model_key}|{case.case_id}|{mode}"
                if result_key in completed:
                    continue
                row: Dict[str, Any]
                try:
                    result = run_with_heartbeat(
                        result_key,
                        lambda seed=seed, case=case, mode=mode, model_key=model_key: engine.generate_one(
                            seed=seed,
                            channel=case.channel,
                            variant=case.variant,
                            mode=mode,  # type: ignore[arg-type]
                            llm_key=model_key,
                            dry_run=args.dry_run,
                        ),
                        enabled=not args.no_progress,
                        heartbeat_seconds=args.progress_heartbeat_seconds,
                    )
                    row = result.as_dict()
                    row["case"] = case.as_dict()
                    row["result_key"] = result_key
                    row["batch_run_id"] = run_id
                    row["batch_generated_at"] = datetime.now().isoformat()
                except Exception as exc:  # keep long runs moving and auditable
                    row = {
                        "result_key": result_key,
                        "batch_run_id": run_id,
                        "batch_generated_at": datetime.now().isoformat(),
                        "llm_key": model_key,
                        "mode": mode,
                        "case": case.as_dict(),
                        "error": type(exc).__name__,
                        "error_message": str(exc),
                        "used_live_llm": False,
                        "used_fallback": False,
                        "validation_passed": False,
                    }

                _append_jsonl(progress_path, {"result_key": result_key, "written_at": row["batch_generated_at"]})
                _append_jsonl(run_root / "scenarios_all.jsonl", row)
                _append_jsonl(run_root / model_key / "scenarios.jsonl", row)
                _append_jsonl(run_root / model_key / f"scenarios_{mode}.jsonl", row)

                completed_count = _count_jsonl(progress_path)
                status = {
                    **summary_base,
                    "updated_at": datetime.now().isoformat(),
                    "completed_results": completed_count,
                    "remaining_results": total_expected - completed_count,
                    "started_models": started_models,
                    "latest_result_key": result_key,
                    "latest_used_live_llm": row.get("used_live_llm"),
                    "latest_used_fallback": row.get("used_fallback"),
                    "latest_validation_passed": row.get("validation_passed"),
                }
                _write_json(run_root / "batch_status.json", status)
                print(json.dumps(status, ensure_ascii=False), flush=True)
                progress.increment(note=result_key)

    final_count = _count_jsonl(progress_path)
    _write_json(
        run_root / "batch_status.json",
        {
            **summary_base,
            "finished_at": datetime.now().isoformat(),
            "completed_results": final_count,
            "remaining_results": total_expected - final_count,
            "started_models": started_models,
            "complete": final_count >= total_expected,
        },
    )


if __name__ == "__main__":
    main()
