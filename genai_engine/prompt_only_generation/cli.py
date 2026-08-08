"""CLI for the prompt-only/default-template scenario generation engine."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from config import AGE_GROUP_BY_CODE, CHANNELS, ORDERED_STAGE_IDS, RETRIEVAL_MODES, ROLES, VARIANTS, filter_seeds, iter_generation_seeds
from generation_progress import ProgressTracker, run_with_heartbeat

from .cases import build_all_1350_cases, build_paper_120_cases, case_set_summary, export_case_manifest
from .engine import PromptOnlyGenerationEngine
from .models import LIGHTWEIGHT_MODEL_PROFILES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate PersonaShield Quest scenarios with prompt engineering and default templates only."
    )
    parser.add_argument("--role", choices=ROLES, default="HR")
    parser.add_argument("--stage", dest="stage_id", choices=ORDERED_STAGE_IDS, default="BEGINNER_INTRODUCTORY")
    parser.add_argument("--age-group", dest="age_group_code", choices=sorted(AGE_GROUP_BY_CODE), default="22_35")
    parser.add_argument("--channel", choices=CHANNELS, default="email")
    parser.add_argument("--variant", choices=VARIANTS, default="fake")
    parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODES, default="ENGLISH_GLOBAL")
    parser.add_argument("--language-mode", choices=["en", "th"], default="en")
    parser.add_argument("--llm", choices=sorted(LIGHTWEIGHT_MODEL_PROFILES), default="qwen2_5_7b")
    parser.add_argument("--case-set", choices=["single", "paper_120", "all_1350"], default="single")
    parser.add_argument("--limit", type=int, default=1, help="Maximum seed slots to generate. Use 0 for all selected slots.")
    parser.add_argument("--out-dir", type=Path, default=Path("output") / "prompt_only_generation")
    parser.add_argument("--dry-run", action="store_true", help="Use only the deterministic default template; do not call Ollama.")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress bar and heartbeat messages.")
    parser.add_argument("--progress-heartbeat-seconds", type=int, default=30, help="Seconds between long-call heartbeat messages.")
    return parser.parse_args()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _selected_seeds(args: argparse.Namespace) -> List[Any]:
    seeds = iter_generation_seeds(retrieval_modes=[args.retrieval_mode])
    if args.case_set == "single":
        seeds = filter_seeds(
            seeds,
            role=args.role,
            stage_id=args.stage_id,
            age_group_code=args.age_group_code,
            retrieval_mode=args.retrieval_mode,
            language_mode=args.language_mode,
        )
    else:
        seeds = [seed for seed in seeds if seed.retrieval_mode == args.retrieval_mode and seed.language_mode == args.language_mode]
    if args.limit > 0:
        seeds = seeds[: args.limit]
    return seeds


def main() -> None:
    args = parse_args()
    if args.list_models:
        print(json.dumps({key: profile.as_dict() for key, profile in LIGHTWEIGHT_MODEL_PROFILES.items()}, indent=2))
        return

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = PromptOnlyGenerationEngine()

    results = []
    case_summary: Dict[str, Any] | None = None
    output_files: Dict[str, str] = {}
    scenarios_path = out_dir / "scenarios_prompt_only.jsonl"
    scenarios_path.write_text("", encoding="utf-8")

    if args.case_set in {"paper_120", "all_1350"}:
        if args.case_set == "paper_120":
            cases = build_paper_120_cases(retrieval_mode=args.retrieval_mode, language_mode=args.language_mode)
        else:
            cases = build_all_1350_cases(retrieval_mode=args.retrieval_mode, language_mode=args.language_mode)
        if args.limit > 0:
            cases = cases[: args.limit]
        export_case_manifest(cases, out_dir / "case_manifest.json", out_dir / "case_manifest.csv")
        case_summary = case_set_summary(cases)
        output_files["case_manifest_json"] = str(out_dir / "case_manifest.json")
        output_files["case_manifest_csv"] = str(out_dir / "case_manifest.csv")
        progress = ProgressTracker(len(cases), label="prompt_only", enabled=not args.no_progress)
        for case in cases:
            label = f"{args.llm} {case.case_id} prompt_only {case.channel}/{case.variant}"
            try:
                result = run_with_heartbeat(
                    label,
                    lambda case=case: engine.generate_one(
                        seed=case.build_seed(),
                        channel=case.channel,
                        variant=case.variant,
                        llm_key=args.llm,
                        dry_run=args.dry_run,
                    ),
                    enabled=not args.no_progress,
                    heartbeat_seconds=args.progress_heartbeat_seconds,
                )
                row = result.as_dict()
            except Exception as exc:
                row = {
                    "mode": "prompt_only",
                    "llm_key": args.llm,
                    "model": LIGHTWEIGHT_MODEL_PROFILES[args.llm].as_dict(),
                    "scenario": None,
                    "validation_passed": False,
                    "validation_issues": [f"Generation failed: {type(exc).__name__}: {str(exc)[:1000]}"],
                    "prompt_metadata": {
                        "generation_error": {
                            "type": type(exc).__name__,
                            "message": str(exc)[:1000],
                            "case_id": case.case_id,
                            "llm": args.llm,
                        }
                    },
                    "used_live_llm": False,
                    "used_fallback": False,
                }
            row["case"] = case.as_dict()
            results.append(row)
            _append_jsonl(scenarios_path, row)
            _write_json(
                out_dir / "run_status.json",
                {
                    "run_id": run_id,
                    "updated_at": datetime.now().isoformat(),
                    "engine": "prompt_only_generation",
                    "case_set": args.case_set,
                    "llm": args.llm,
                    "completed_results": len(results),
                    "total_expected_results": len(cases),
                    "remaining_results": len(cases) - len(results),
                    "latest_case_id": case.case_id,
                    "latest_validation_passed": row.get("validation_passed"),
                    "latest_error": row.get("prompt_metadata", {}).get("generation_error"),
                    "output_files": {"scenarios_jsonl": str(scenarios_path)},
                },
            )
            progress.increment(note=label)
        seed_count = len(cases)
    else:
        seeds = _selected_seeds(args)
        if not seeds:
            raise SystemExit("No generation seeds matched the requested filters.")
        channel_variant_pairs = [(args.channel, args.variant)] if args.case_set == "single" else [(channel, variant) for channel in CHANNELS for variant in VARIANTS]
        progress = ProgressTracker(len(seeds) * len(channel_variant_pairs), label="prompt_only", enabled=not args.no_progress)
        for seed in seeds:
            for channel, variant in channel_variant_pairs:
                label = f"{args.llm} {seed.persona_path_id} prompt_only {channel}/{variant}"
                try:
                    result = run_with_heartbeat(
                        label,
                        lambda seed=seed, channel=channel, variant=variant: engine.generate_one(
                            seed=seed,
                            channel=channel,
                            variant=variant,
                            llm_key=args.llm,
                            dry_run=args.dry_run,
                        ),
                        enabled=not args.no_progress,
                        heartbeat_seconds=args.progress_heartbeat_seconds,
                    )
                    row = result.as_dict()
                except Exception as exc:
                    row = {
                        "mode": "prompt_only",
                        "llm_key": args.llm,
                        "model": LIGHTWEIGHT_MODEL_PROFILES[args.llm].as_dict(),
                        "scenario": None,
                        "validation_passed": False,
                        "validation_issues": [f"Generation failed: {type(exc).__name__}: {str(exc)[:1000]}"],
                        "prompt_metadata": {
                            "generation_error": {
                                "type": type(exc).__name__,
                                "message": str(exc)[:1000],
                                "seed": getattr(seed, "persona_path_id", "unknown"),
                                "channel": channel,
                                "variant": variant,
                                "llm": args.llm,
                            }
                        },
                        "used_live_llm": False,
                        "used_fallback": False,
                    }
                row["seed"] = seed.to_dict() if hasattr(seed, "to_dict") else dict(seed)
                results.append(row)
                _append_jsonl(scenarios_path, row)
                _write_json(
                    out_dir / "run_status.json",
                    {
                        "run_id": run_id,
                        "updated_at": datetime.now().isoformat(),
                        "engine": "prompt_only_generation",
                        "case_set": args.case_set,
                        "llm": args.llm,
                        "completed_results": len(results),
                        "total_expected_results": len(seeds) * len(channel_variant_pairs),
                        "remaining_results": (len(seeds) * len(channel_variant_pairs)) - len(results),
                        "latest_seed": row.get("seed", {}).get("persona_path_id"),
                        "latest_channel": channel,
                        "latest_variant": variant,
                        "latest_validation_passed": row.get("validation_passed"),
                        "output_files": {"scenarios_jsonl": str(scenarios_path)},
                    },
                )
                progress.increment(note=label)
        seed_count = len(seeds)

    _write_jsonl(scenarios_path, results)
    output_files["scenarios_jsonl"] = str(scenarios_path)
    summary = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
        "engine": "prompt_only_generation",
        "engine_version": PromptOnlyGenerationEngine.engine_version,
        "case_set": args.case_set,
        "llm": args.llm,
        "dry_run": args.dry_run,
        "rag_used": False,
        "ontology_used": False,
        "seed_count": seed_count,
        "result_count": len(results),
        "validation_passed": sum(1 for row in results if row["validation_passed"]),
        "validation_failed": sum(1 for row in results if not row["validation_passed"]),
        "case_set_summary": case_summary,
        "output_files": output_files,
    }
    _write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
