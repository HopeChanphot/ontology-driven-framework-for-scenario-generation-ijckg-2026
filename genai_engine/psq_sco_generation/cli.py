"""CLI for the separate PSQ-SCO scenario generation engine."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from config import AGE_GROUP_BY_CODE, CHANNELS, ORDERED_STAGE_IDS, RETRIEVAL_MODES, ROLES, VARIANTS, filter_seeds, iter_generation_seeds
from generation_progress import ProgressTracker, run_with_heartbeat

from .cases import build_all_1350_cases, build_paper_120_cases, case_set_summary, export_case_manifest, generation_capacity
from .engine import PSQSCOGenerationEngine
from .models import ENGINE_MODES, LIGHTWEIGHT_MODEL_PROFILES
from .ontology import DEFAULT_ONTOLOGY_PATH, PSQSCOOntology


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate PersonaShield Quest scenarios with prompt-only, prompt+RAG, ontology-packet, or ontology-text RAG modes."
    )
    parser.add_argument("--ontology-path", type=Path, default=DEFAULT_ONTOLOGY_PATH)
    parser.add_argument("--mode", choices=[*ENGINE_MODES, "both", "three_mode", "all_modes"], default="both")
    parser.add_argument("--role", choices=ROLES, default="HR")
    parser.add_argument("--stage", dest="stage_id", choices=ORDERED_STAGE_IDS, default="BEGINNER_INTRODUCTORY")
    parser.add_argument("--age-group", dest="age_group_code", choices=sorted(AGE_GROUP_BY_CODE), default="22_35")
    parser.add_argument("--channel", choices=CHANNELS, default="email")
    parser.add_argument("--variant", choices=VARIANTS, default="fake")
    parser.add_argument("--retrieval-mode", choices=RETRIEVAL_MODES, default="ENGLISH_GLOBAL")
    parser.add_argument("--language-mode", choices=["en", "th"], default="en")
    parser.add_argument("--llm", choices=sorted(LIGHTWEIGHT_MODEL_PROFILES), default="qwen2_5_7b")
    parser.add_argument("--limit", type=int, default=1, help="Maximum seeds to generate.")
    parser.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="Generate only this case ID. Can be repeated. Intended for recovery reruns of fallback/non-live rows.",
    )
    parser.add_argument(
        "--case-id-file",
        type=Path,
        default=None,
        help="Text file containing case IDs to generate, one per line. Blank lines and # comments are ignored.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("output") / "psq_sco_generation")
    parser.add_argument("--resume-dir", type=Path, default=None, help="Resume an existing run directory and skip completed live-LLM rows.")
    parser.add_argument(
        "--case-set",
        choices=["single", "paper_120", "all_1350"],
        default="single",
        help="Use one CLI-selected case, the frozen 120-case paper set, or the full 1,350-slot set.",
    )
    parser.add_argument("--export-case-plan-only", action="store_true", help="Export the selected case manifest and exit without generating scenarios.")
    parser.add_argument("--skip-rag", action="store_true", help="Disable RAG retrieval and use only prompt/ontology constraints.")
    parser.add_argument("--force-rag", action="store_true", help="Force rebuilding the existing Chroma RAG index before generation.")
    parser.add_argument("--n-rag-examples", type=int, default=2, help="Number of external project RAG examples to retrieve per scenario.")
    parser.add_argument("--ontology-text-doc-limit", type=int, default=5, help="Number of ontology text/Graph-CoT documents to add per ontology_text_rag scenario.")
    parser.add_argument("--llm-timeout", type=int, default=None, help="Override local LLM timeout seconds for each scenario.")
    parser.add_argument("--llm-max-tokens", type=int, default=None, help="Override maximum generated tokens per scenario.")
    parser.add_argument("--llm-num-ctx", type=int, default=None, help="Override Ollama context window for each scenario.")
    parser.add_argument("--llm-temperature", type=float, default=None, help="Override local LLM temperature.")
    parser.add_argument(
        "--llm-parse-retries",
        type=int,
        default=1,
        help="Retry local LLM generation this many times when the response is live but not parseable JSON.",
    )
    parser.add_argument(
        "--compact-generation-prompt",
        action="store_true",
        help="Use a shorter schema-preserving prompt for slow local models such as qwen3 on CPU.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build prompts and schema-safe fallback scenarios without calling Ollama.")
    parser.add_argument("--require-live-llm", action="store_true", help="Stop if a non-dry run falls back instead of receiving live LLM output.")
    parser.add_argument("--resume-accept-fallback", action="store_true", help="When resuming, treat fallback rows as complete. Not recommended for final evaluation.")
    parser.add_argument("--ontology-summary", action="store_true", help="Print ontology summary and exit.")
    parser.add_argument("--export-ontology-text-only", action="store_true", help="Export graph-to-text ontology RAG documents and exit.")
    parser.add_argument("--list-models", action="store_true", help="Print configured local lightweight model profiles and exit.")
    parser.add_argument("--capacity-summary", action="store_true", help="Print scenario-generation capacity formulas and exit.")
    parser.add_argument("--no-progress", action="store_true", help="Disable terminal progress bar and heartbeat messages.")
    parser.add_argument("--progress-heartbeat-seconds", type=int, default=30, help="Seconds between long-call heartbeat messages.")
    return parser.parse_args()


def _selected_case_ids(args: argparse.Namespace) -> set[str]:
    """Return case IDs requested for a selective generation/recovery run."""

    selected = {str(case_id).strip().lstrip("\ufeff") for case_id in args.case_id if str(case_id).strip()}
    if args.case_id_file:
        if not args.case_id_file.exists():
            raise SystemExit(f"Case ID file does not exist: {args.case_id_file}")
        for line in args.case_id_file.read_text(encoding="utf-8").splitlines():
            clean = line.strip().lstrip("\ufeff")
            if clean and not clean.startswith("#"):
                selected.add(clean)
    return selected


def _filter_case_rows_by_id(case_rows: List[Any], selected_case_ids: set[str]) -> List[Any]:
    """Filter generated case rows while preserving the paper-set order."""

    if not selected_case_ids:
        return case_rows
    filtered = [case for case in case_rows if case.case_id in selected_case_ids]
    missing = sorted(selected_case_ids - {case.case_id for case in filtered})
    if missing:
        raise SystemExit("Requested case IDs are not in the selected case set: " + ", ".join(missing))
    if not filtered:
        raise SystemExit("No case rows matched the requested case IDs.")
    return filtered


def _modes(mode_arg: str) -> List[str]:
    from .models import LEGACY_COMPARISON_MODES, THREE_WAY_COMPARISON_MODES

    if mode_arg == "both":
        return list(LEGACY_COMPARISON_MODES)
    if mode_arg == "three_mode":
        return list(THREE_WAY_COMPARISON_MODES)
    if mode_arg == "all_modes":
        return list(ENGINE_MODES)
    return [mode_arg]


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _row_key(row: Dict[str, Any]) -> str:
    case = row.get("case") or {}
    prompt_error = row.get("prompt_metadata", {}).get("generation_error") or {}
    case_id = case.get("case_id") or prompt_error.get("case_id")
    mode = row.get("mode") or prompt_error.get("mode")
    return f"{case_id}|{mode}" if case_id and mode else ""


def _is_complete_result(row: Dict[str, Any], *, dry_run: bool, accept_fallback: bool) -> bool:
    if not row.get("scenario"):
        return False
    prompt_metadata = row.get("prompt_metadata", {})
    if prompt_metadata.get("generation_error") or prompt_metadata.get("live_llm_error"):
        return False
    if dry_run:
        return True
    if row.get("used_live_llm"):
        return True
    return bool(accept_fallback and row.get("used_fallback"))


def main() -> None:
    args = parse_args()
    selected_modes = _modes(args.mode)
    selected_case_ids = _selected_case_ids(args)
    if args.list_models:
        print(json.dumps({k: v.as_dict() for k, v in LIGHTWEIGHT_MODEL_PROFILES.items()}, indent=2))
        return

    if args.capacity_summary:
        capacity = {
            "single_generation_mode": generation_capacity(model_count=1, mode_count=1, retrieval_mode_count=1),
            "both_modes_one_retrieval_mode_one_model": generation_capacity(model_count=1, mode_count=2, retrieval_mode_count=1),
            "three_modes_one_retrieval_mode_one_model": generation_capacity(model_count=1, mode_count=3, retrieval_mode_count=1),
            "all_modes_one_retrieval_mode_one_model": generation_capacity(model_count=1, mode_count=len(ENGINE_MODES), retrieval_mode_count=1),
            "both_modes_two_production_retrieval_modes_one_model": generation_capacity(model_count=1, mode_count=2, retrieval_mode_count=2),
            "both_modes_one_retrieval_mode_three_primary_models": generation_capacity(model_count=3, mode_count=2, retrieval_mode_count=1),
            "three_modes_one_retrieval_mode_three_primary_models": generation_capacity(model_count=3, mode_count=3, retrieval_mode_count=1),
            "notes": [
                "A complete game scenario slot space is 5 roles x 9 stages x 5 age groups x 3 channels x 2 variants = 1,350 per retrieval mode, model, and generation mode.",
                "--mode both preserves the legacy comparison: prompt_rag against ontology_prompt_rag.",
                "--mode three_mode compares prompt_only, prompt_rag, and ontology_text_rag on matched cases.",
                "The paper_120 case set defines 120 matched case definitions; with --mode three_mode it generates 360 outputs per model.",
            ],
        }
        print(json.dumps(capacity, ensure_ascii=False, indent=2))
        return

    if args.ontology_summary:
        print(json.dumps(PSQSCOOntology(args.ontology_path).summary(), ensure_ascii=False, indent=2))
        return

    if args.resume_dir:
        out_dir = args.resume_dir
        if not out_dir.exists():
            raise SystemExit(f"Resume directory does not exist: {out_dir}")
        run_id = out_dir.name
    else:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = args.out_dir / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
    case_manifest_json = out_dir / "case_manifest.json"
    case_manifest_csv = out_dir / "case_manifest.csv"

    if args.export_ontology_text_only:
        from .ontology_text import OntologyTextCorpus

        ontology = PSQSCOOntology(args.ontology_path)
        corpus = OntologyTextCorpus(ontology)
        ontology_text_path = out_dir / "ontology_text_corpus.jsonl"
        corpus.export_jsonl(ontology_text_path)
        summary = {
            "run_id": run_id,
            "engine": "psq_sco_generation",
            "task": "export_ontology_text_corpus",
            "output_files": {"ontology_text_corpus_jsonl": str(ontology_text_path)},
            "ontology_summary": ontology.summary(),
            "ontology_text_summary": corpus.summary(),
        }
        _write_json(out_dir / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    if args.case_set == "paper_120":
        cases = build_paper_120_cases(retrieval_mode=args.retrieval_mode, language_mode=args.language_mode)
        if selected_case_ids:
            cases = _filter_case_rows_by_id(cases, selected_case_ids)
        elif args.limit > 0:
            cases = cases[: args.limit]
        if not args.resume_dir or not case_manifest_json.exists():
            export_case_manifest(cases, case_manifest_json, case_manifest_csv, modes=selected_modes)
        case_rows = cases
    elif args.case_set == "all_1350":
        cases = build_all_1350_cases(retrieval_mode=args.retrieval_mode, language_mode=args.language_mode)
        if selected_case_ids:
            cases = _filter_case_rows_by_id(cases, selected_case_ids)
        elif args.limit > 0:
            cases = cases[: args.limit]
        if not args.resume_dir or not case_manifest_json.exists():
            export_case_manifest(cases, case_manifest_json, case_manifest_csv, modes=selected_modes)
        case_rows = cases
    else:
        seeds = iter_generation_seeds(retrieval_modes=[args.retrieval_mode])
        seeds = filter_seeds(
            seeds,
            role=args.role,
            stage_id=args.stage_id,
            age_group_code=args.age_group_code,
            retrieval_mode=args.retrieval_mode,
            language_mode=args.language_mode,
        )
        if args.limit > 0:
            seeds = seeds[: args.limit]
        if not seeds:
            raise SystemExit("No generation seeds matched the requested filters.")
        case_rows = []
        for index, seed in enumerate(seeds, start=1):
            # Single mode keeps backward-friendly CLI filtering but still exports a minimal case manifest.
            from .cases import PaperCase

            seed_dict = seed.to_dict()
            case_rows.append(
                PaperCase(
                    case_id=f"SINGLE-{index:03d}",
                    case_set_id="single_cli_selection",
                    group_id=f"SINGLE_{seed.role}_{args.channel}_{args.variant}",
                    group_index=index,
                    case_index=index,
                    role=seed.role,
                    channel=args.channel,
                    variant=args.variant,
                    difficulty_condition="cli_selected",
                    stage_id=seed.stage_id,
                    macro_stage=seed.macro_stage,
                    micro_stage=seed.micro_stage,
                    stage_index=seed.stage_index,
                    difficulty_band=seed.difficulty_band,
                    age_group_code=seed.age_group_code,
                    age_group_label=seed.age_group_label,
                    retrieval_mode=seed.retrieval_mode,
                    language_mode=seed.language_mode,
                    modes_to_compare=_modes(args.mode),
                    rationale="Single CLI-selected generation case.",
                )
            )
        if not args.resume_dir or not case_manifest_json.exists():
            export_case_manifest(case_rows, case_manifest_json, case_manifest_csv)

    if args.export_case_plan_only:
        summary = {
            "run_id": run_id,
            "case_set": args.case_set,
            "case_count": len(case_rows),
            "selected_modes": selected_modes,
            "selected_case_ids": sorted(selected_case_ids),
            "output_files": {"case_manifest_json": str(case_manifest_json), "case_manifest_csv": str(case_manifest_csv)},
            "case_set_summary": case_set_summary(case_rows, modes=selected_modes),
        }
        _write_json(out_dir / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    engine = PSQSCOGenerationEngine(ontology_path=args.ontology_path, use_rag=not args.skip_rag)

    if args.force_rag and not args.skip_rag:
        engine.rag.index_knowledge_base(force=True)

    scenarios_jsonl = out_dir / "scenarios.jsonl"
    per_mode_files = {mode: out_dir / f"scenarios_{mode}.jsonl" for mode in selected_modes}
    result_by_key: Dict[str, Dict[str, Any]] = {}
    if args.resume_dir:
        for row in _read_jsonl(scenarios_jsonl):
            key = _row_key(row)
            if key:
                result_by_key[key] = row
        if not result_by_key:
            for path in per_mode_files.values():
                for row in _read_jsonl(path):
                    key = _row_key(row)
                    if key:
                        result_by_key[key] = row
    else:
        for path in [scenarios_jsonl, *per_mode_files.values()]:
            path.write_text("", encoding="utf-8")
    total_expected = len(case_rows) * len(selected_modes)
    completed_keys = {
        key
        for key, row in result_by_key.items()
        if _is_complete_result(row, dry_run=args.dry_run, accept_fallback=args.resume_accept_fallback)
    }
    progress = ProgressTracker(total_expected, label="sco_generation", enabled=not args.no_progress, current=len(completed_keys))
    for case in case_rows:
        seed = case.build_seed()
        for mode in selected_modes:
            key = f"{case.case_id}|{mode}"
            if key in completed_keys:
                continue
            label = f"{args.llm} {case.case_id} {mode} {case.channel}/{case.variant}"
            try:
                result = run_with_heartbeat(
                    label,
                    lambda seed=seed, case=case, mode=mode: engine.generate_one(
                        seed=seed,
                        channel=case.channel,
                        variant=case.variant,
                        mode=mode,  # type: ignore[arg-type]
                        llm_key=args.llm,
                        dry_run=args.dry_run,
                        n_rag_examples=max(0, args.n_rag_examples),
                        ontology_text_limit=max(1, args.ontology_text_doc_limit),
                        llm_timeout=args.llm_timeout,
                        llm_max_tokens=args.llm_max_tokens,
                        llm_num_ctx=args.llm_num_ctx,
                        llm_temperature=args.llm_temperature,
                        compact_prompt=args.compact_generation_prompt,
                        llm_parse_retries=args.llm_parse_retries,
                    ),
                    enabled=not args.no_progress,
                    heartbeat_seconds=args.progress_heartbeat_seconds,
                )
                row = result.as_dict()
            except Exception as exc:
                row = {
                    "mode": mode,
                    "llm_key": args.llm,
                    "model": LIGHTWEIGHT_MODEL_PROFILES[args.llm].as_dict(),
                    "scenario": None,
                    "validation_passed": False,
                    "validation_issues": [f"Generation failed: {type(exc).__name__}: {str(exc)[:1000]}"],
                    "semantic_packet": None,
                    "rag_examples": [],
                    "prompt_metadata": {
                        "generation_error": {
                            "type": type(exc).__name__,
                            "message": str(exc)[:1000],
                            "case_id": case.case_id,
                            "mode": mode,
                            "llm": args.llm,
                        }
                    },
                    "used_live_llm": False,
                    "used_fallback": False,
                }
            row["case"] = case.as_dict()
            result_by_key[key] = row
            _append_jsonl(scenarios_jsonl, row)
            _append_jsonl(per_mode_files[mode], row)
            completed_now = sum(
                1
                for item in result_by_key.values()
                if _is_complete_result(item, dry_run=args.dry_run, accept_fallback=args.resume_accept_fallback)
            )
            _write_json(
                out_dir / "run_status.json",
                {
                    "run_id": run_id,
                    "updated_at": datetime.now().isoformat(),
                    "engine": "psq_sco_generation",
                    "case_set": args.case_set,
                    "llm": args.llm,
                    "mode": args.mode,
                    "selected_modes": selected_modes,
                    "selected_case_ids": sorted(selected_case_ids),
                    "completed_results": completed_now,
                    "attempted_or_recorded_results": len(result_by_key),
                    "total_expected_results": total_expected,
                    "remaining_results": total_expected - completed_now,
                    "resume_dir": str(out_dir) if args.resume_dir else None,
                    "require_live_llm": args.require_live_llm,
                    "n_rag_examples": args.n_rag_examples,
                    "ontology_text_doc_limit": args.ontology_text_doc_limit,
                    "llm_timeout": args.llm_timeout,
                    "llm_max_tokens": args.llm_max_tokens,
                    "llm_num_ctx": args.llm_num_ctx,
                    "llm_temperature": args.llm_temperature,
                    "llm_parse_retries": args.llm_parse_retries,
                    "compact_generation_prompt": args.compact_generation_prompt,
                    "latest_case_id": case.case_id,
                    "latest_mode": mode,
                    "latest_validation_passed": row.get("validation_passed"),
                    "latest_error": row.get("prompt_metadata", {}).get("generation_error"),
                    "output_files": {
                        "scenarios_jsonl": str(scenarios_jsonl),
                        **{f"scenarios_{m}_jsonl": str(p) for m, p in per_mode_files.items()},
                    },
                },
            )
            progress.increment(note=label)
            if args.require_live_llm and not args.dry_run and not row.get("used_live_llm"):
                raise SystemExit(
                    "Live LLM output was required, but this row used fallback or failed. "
                    f"Check Ollama and resume with --resume-dir {out_dir}"
                )

    results = []
    for case in case_rows:
        for mode in selected_modes:
            key = f"{case.case_id}|{mode}"
            if key in result_by_key:
                results.append(result_by_key[key])

    _write_jsonl(scenarios_jsonl, results)
    for mode in selected_modes:
        mode_path = per_mode_files[mode]
        _write_jsonl(mode_path, [result for result in results if result["mode"] == mode])

    summary = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
        "engine": "psq_sco_generation",
        "ontology_path": str(args.ontology_path),
        "mode": args.mode,
        "selected_modes": selected_modes,
        "selected_case_ids": sorted(selected_case_ids),
        "case_set": args.case_set,
        "llm": args.llm,
        "dry_run": args.dry_run,
        "skip_rag": args.skip_rag,
        "n_rag_examples": args.n_rag_examples,
        "ontology_text_doc_limit": args.ontology_text_doc_limit,
        "llm_timeout": args.llm_timeout,
        "llm_max_tokens": args.llm_max_tokens,
        "llm_num_ctx": args.llm_num_ctx,
        "llm_temperature": args.llm_temperature,
        "llm_parse_retries": args.llm_parse_retries,
        "compact_generation_prompt": args.compact_generation_prompt,
        "case_count": len(case_rows),
        "result_count": len(results),
        "validation_passed": sum(1 for r in results if r["validation_passed"]),
        "validation_failed": sum(1 for r in results if not r["validation_passed"]),
        "output_files": {
            "case_manifest_json": str(case_manifest_json),
            "case_manifest_csv": str(case_manifest_csv),
            "scenarios_jsonl": str(scenarios_jsonl),
            **{f"scenarios_{mode}_jsonl": str(path) for mode, path in per_mode_files.items()},
        },
        "case_set_summary": case_set_summary(case_rows, modes=selected_modes),
        "ontology_summary": engine.ontology.summary(),
        "ontology_text_summary": engine.ontology_text_corpus.summary(),
    }
    _write_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
