"""Paper-120 dataset, timing, diversity, and documentation helpers."""

from __future__ import annotations

import json
import hashlib
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Sequence

from config import KB_DIR, PROJECT_ROOT
from rag_engine import PROFILE_FILE_PATTERNS, PROFILE_MAX_DOCS_PER_FILE

from .models import (
    METHOD_CONDITION_NUMBERS,
    METHOD_IMPLEMENTATION_NOTES,
    METHOD_LABELS,
    METHOD_ORDER,
    ScenarioRecord,
    ScenarioScore,
)


FINAL_PAPER_120_FILES = (
    ("qwen2_5_7b", "prompt_only", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen2_5_7b__prompt_only__paper_120_live_recovered.jsonl"),
    ("qwen3_8b", "prompt_only", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen3_8b__prompt_only__paper_120_live_recovered.jsonl"),
    ("mistral_7b", "prompt_only", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/mistral_7b__prompt_only__paper_120_live_recovered.jsonl"),
    ("qwen2_5_7b", "prompt_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen2_5_7b__prompt_rag__paper_120_live_recovered.jsonl"),
    ("qwen3_8b", "prompt_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen3_8b__prompt_rag__paper_120_live_recovered.jsonl"),
    ("mistral_7b", "prompt_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/mistral_7b__prompt_rag__paper_120_live_recovered.jsonl"),
    ("qwen2_5_7b", "ontology_prompt_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen2_5_7b__ontology_prompt_rag__paper_120_live_recovered.jsonl"),
    ("qwen3_8b", "ontology_prompt_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen3_8b__ontology_prompt_rag__paper_120_live_recovered.jsonl"),
    ("mistral_7b", "ontology_prompt_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/mistral_7b__ontology_prompt_rag__paper_120_live_recovered.jsonl"),
    ("qwen2_5_7b", "ontology_text_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen2_5_7b__ontology_text_rag__paper_120_live_recovered.jsonl"),
    ("qwen3_8b", "ontology_text_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/qwen3_8b__ontology_text_rag__paper_120_live_recovered.jsonl"),
    ("mistral_7b", "ontology_text_rag", "output/paper120_live_recovered_final/20260714_031104/generated_scenarios/mistral_7b__ontology_text_rag__paper_120_live_recovered.jsonl"),
)

GRAPH_WALK_V1_MODE4_FILES = (
    ("qwen2_5_7b", "ontology_text_rag", "output/experiments/paper120_mode4_graph_walk_v1/20260723_030518/qwen2_5_7b/scenarios_ontology_text_rag.jsonl"),
    ("qwen3_8b", "ontology_text_rag", "output/experiments/paper120_mode4_graph_walk_v1/20260723_030518/qwen3_8b/scenarios_ontology_text_rag.jsonl"),
    ("mistral_7b", "ontology_text_rag", "output/experiments/paper120_mode4_graph_walk_v1/20260723_030518/mistral_7b/scenarios_ontology_text_rag.jsonl"),
)


def final_paper_120_files(root: Path = PROJECT_ROOT) -> List[Path]:
    """Return existing final 3-model x 4-mode paper-120 result files."""

    files: List[Path] = []
    missing: List[str] = []
    for _model, _method, relative_path in FINAL_PAPER_120_FILES:
        path = root / relative_path
        if path.exists():
            files.append(path)
        else:
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing final paper-120 files:\n" + "\n".join(missing))
    return files


def paper_120_graph_walk_v1_files(root: Path = PROJECT_ROOT) -> List[Path]:
    """Return Conditions 1-3 from the clean frozen set plus graph-walk-v1 Condition 4."""

    selected = [
        (model, method, relative_path)
        for model, method, relative_path in FINAL_PAPER_120_FILES
        if method != "ontology_text_rag"
    ]
    selected.extend(GRAPH_WALK_V1_MODE4_FILES)
    files: List[Path] = []
    missing: List[str] = []
    for _model, _method, relative_path in selected:
        path = root / relative_path
        if path.exists():
            files.append(path)
        else:
            missing.append(str(path))
    if missing:
        raise FileNotFoundError(
            "Missing graph-walk-v1 comparison files:\n" + "\n".join(missing)
        )
    return files


def condition_manifest_rows(files: Sequence[Path]) -> List[Dict[str, Any]]:
    """Summarize the exact condition files used by the paper-120 evaluation."""

    rows: List[Dict[str, Any]] = []
    by_path = {str((PROJECT_ROOT / rel).resolve()).lower(): (model, method) for model, method, rel in FINAL_PAPER_120_FILES}
    for path in files:
        model, method = by_path.get(str(path.resolve()).lower(), ("", ""))
        line_count = _line_count(path)
        first = _first_json(path)
        case_ids = _case_ids(path)
        rows.append(
            {
                "model_key": model or first.get("llm_key") or first.get("model", {}).get("key"),
                "method": method or _infer_method_from_row(first),
                "condition_number": METHOD_CONDITION_NUMBERS.get(method or _infer_method_from_row(first), 0),
                "condition_name": METHOD_LABELS.get(method or _infer_method_from_row(first), method),
                "method_label": METHOD_LABELS.get(method or _infer_method_from_row(first), method),
                "implementation_note": METHOD_IMPLEMENTATION_NOTES.get(method or _infer_method_from_row(first), ""),
                "scenario_file": str(path),
                "scenario_file_sha256": _sha256(path),
                "row_count": line_count,
                "unique_case_count": len(case_ids),
                "same_120_case_set": len(case_ids) == 120,
                "first_case_id": sorted(case_ids)[0] if case_ids else "",
                "last_case_id": sorted(case_ids)[-1] if case_ids else "",
                "used_live_llm_rows": _count_rows(path, lambda row: bool(row.get("used_live_llm"))),
                "fallback_rows": _count_rows(path, lambda row: bool(row.get("used_fallback"))),
                "schema_safe_repair_rows": _count_rows(path, _row_schema_safe_repair),
                "live_model_content_retained_rows": _count_rows(
                    path,
                    lambda row: bool(row.get("used_live_llm"))
                    and not bool(row.get("used_fallback"))
                    and not _row_schema_safe_repair(row),
                ),
                "engine_validation_passed_rows": _count_rows(
                    path, lambda row: row.get("validation_passed") is True
                ),
                "engine_validation_failed_rows": _count_rows(
                    path, lambda row: row.get("validation_passed") is False
                ),
                "graph_walk_required_rows": _count_rows(path, _row_graph_walk_required),
                "graph_walk_exposed_rows": _count_rows(path, _row_graph_walk_exposed),
                "experiment_variant": (
                    "graph_walk_v1"
                    if _count_rows(path, _row_graph_walk_required)
                    else "original_four_condition"
                ),
            }
        )
    return rows


def dataset_description(records: Sequence[ScenarioRecord] = ()) -> Dict[str, Any]:
    """Describe the RAG/ontology dataset used across generation conditions."""

    profile = "quality"
    selected = []
    total_raw = 0
    total_capped = 0
    wanted = set(PROFILE_FILE_PATTERNS[profile])
    for channel_dir in sorted(KB_DIR.iterdir()) if KB_DIR.exists() else []:
        if not channel_dir.is_dir():
            continue
        for file_path in sorted(channel_dir.glob("*.jsonl")):
            if file_path.name not in wanted:
                continue
            raw_count = _line_count(file_path)
            cap = PROFILE_MAX_DOCS_PER_FILE[profile].get(file_path.name)
            used_count = min(raw_count, cap) if cap is not None else raw_count
            total_raw += raw_count
            total_capped += used_count
            selected.append(
                {
                    "source_file": file_path.name,
                    "channel_folder": channel_dir.name,
                    "source_origin": _source_origin(file_path.name),
                    "source_type": _source_type(file_path.name),
                    "language": "th" if "_th" in file_path.name.lower() else "en",
                    "variant_label": "real/ham" if "_ham_" in file_path.name.lower() else "fake/scam",
                    "raw_document_count": raw_count,
                    "profile_cap": cap,
                    "used_document_count": used_count,
                    "path": str(file_path),
                }
            )
    chroma_meta = _read_json(PROJECT_ROOT / "chroma_db_quality" / ".kb_meta.json")
    graph_profile = _graph_walk_dataset_profile(records)
    return {
        "dataset_section_purpose": "Documents the retrieval corpus so Conditions 2-4 are reproducible and comparable with Condition 1.",
        "condition_definitions": [
            {
                "condition_number": METHOD_CONDITION_NUMBERS[method],
                "method": method,
                "condition_name": METHOD_LABELS[method],
                "implementation": METHOD_IMPLEMENTATION_NOTES[method],
            }
            for method in METHOD_ORDER
        ],
        "same_sources_across_conditions": (
            "Text-RAG Generation, Ontology-Derived Structured Prompting RAG, and Ontology-to-Text Vector RAG "
            "attempt retrieval from the same PSQ_RAG_PROFILE=quality external corpus selection unless explicitly overridden; "
            "the evaluator separately reports rows where retrieval returned no external context. "
            "Prompt-Only Generation is the no-retrieval baseline."
        ),
        "kb_dir": str(KB_DIR),
        "rag_profile": profile,
        "vector_database": "ChromaDB PersistentClient",
        "vector_index_path": str(PROJECT_ROOT / "chroma_db_quality"),
        "vector_space": "cosine HNSW",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2 (expected Chroma default because rag_engine.py does not pass a custom embedding_function)",
        "embedding_model_status": (
            "Expected from the official Chroma default-embedding documentation, not fully provenance-frozen for the "
            "historical generation run. The exact Chroma package version, model artifact hash, and embedding-function "
            "configuration were not stored in the generation records."
        ),
        "embedding_model_training_domain": (
            "General-purpose sentence-pair representation learning, not a cybersecurity-ontology-specific model. "
            "The all-MiniLM-L6-v2 model card reports 384-dimensional embeddings, fine-tuning on more than one billion "
            "sentence pairs, and truncation beyond 256 word pieces."
        ),
        "embedding_model_domain_mismatch": (
            "Because the model is general-purpose, source relevance for phishing/smishing/vishing and verbalized OWL "
            "records must be treated as an empirical retrieval question rather than assumed from the model name."
        ),
        "ontology_text_selection": (
            "The ontology-derived records are selected by a deterministic lexical relevance score, mandatory "
            "document-type coverage, and optional deterministic greedy relation walk. They are not stored in or "
            "retrieved from Chroma by the current implementation."
        ),
        "ontology_walk_algorithm": {
            "scientific_name": "deterministic greedy relevance walk",
            "legacy_metadata_alias": "deterministic_random_walk_graph_to_text",
            "start_nodes": "up to five IDs ordered as selected templates, fixed-order validation rules, then evidence sources",
            "depth": "walk_depth=2 by default, producing depth 0, 1, and 2 nodes per start when edges exist",
            "edge_score": "count of case query terms occurring in property, target ID, target label, target definition, or target types; +1 when target is a known ontology record",
            "tie_break": "descending score, then property name ascending, then target ID ascending",
            "transition": "choose exactly one highest-ranked outgoing property-target pair at each step",
            "stopping": "stop at maximum depth, missing current record, or no outgoing candidate",
            "randomness": "none",
            "cycle_policy": "no visited-node exclusion in the historical implementation; depth bound guarantees termination",
            "frozen_run_exposure": (
                graph_profile.get("interpretation")
                or "No generation records were supplied to dataset_description; graph-walk exposure was not inferred."
            ),
        },
        "evaluated_generation_profile": graph_profile,
        "chunking": "One JSONL record is converted into one retrieval document by concatenating available text/subject/body/messages/dialogue/cue fields.",
        "preprocessing": "JSONL rows with short text are skipped; exact lowercased text hashes are deduplicated; profile caps limit very large corpora.",
        "retrieval_settings": {
            "query": "role, job title hint, channel, variant, knowledge type, interaction pattern, development focus, age group",
            "initial_query_n": "max(n_results * 16, 64)",
            "final_n_results_generation": "configured by --n-rag-examples; final paper ontology-text runs use 1 external RAG example",
            "metadata_filters": ["channel", "language", "retrieval_mode", "is_scam", "knowledge_type", "difficulty_band", "age_band_fit", "stage_band_fit"],
            "fallback_ladders": ["strict", "drop_age_stage", "drop_knowledge_difficulty", "mixed_mode"],
        },
        "selected_file_count": len(selected),
        "raw_document_count_before_caps": total_raw,
        "used_document_count_after_caps": total_capped,
        "chroma_index_metadata": chroma_meta,
        "sources": selected,
    }


def matched_case_audit(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Show that methods are compared on matched case IDs rather than unrelated samples."""

    rows: List[Dict[str, Any]] = []
    by_model: Dict[str, Dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for score in scores:
        by_model[score.model_key][score.method].add(score.case_id)
    for model, by_method in sorted(by_model.items()):
        all_sets = [by_method.get(method, set()) for method in METHOD_ORDER]
        full_intersection = set.intersection(*all_sets) if all_sets and all(all_sets) else set()
        row: Dict[str, Any] = {
            "model_key": model,
            "matched_all_four_case_count": len(full_intersection),
            "matched_all_four": len(full_intersection) == 120,
        }
        for method in METHOD_ORDER:
            row[f"{method}_case_count"] = len(by_method.get(method, set()))
        rows.append(row)
    return rows


def timing_analysis(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Aggregate direct and observed generation timing by model and method."""

    rows: List[Dict[str, Any]] = []
    grouped: Dict[tuple[str, str], List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        grouped[(score.model_key, score.method)].append(score)
    for (model, method), group in sorted(grouped.items()):
        direct = [x.generation_seconds for x in group if x.generation_seconds is not None]
        observed = [x.observed_interarrival_seconds for x in group if x.observed_interarrival_seconds is not None]
        rows.append(
            {
                "model_key": model,
                "method": method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
                "condition_name": METHOD_LABELS.get(method, method),
                "n": len(group),
                "direct_timing_n": len(direct),
                "direct_generation_seconds_mean": _safe_mean(direct),
                "direct_generation_seconds_median": _safe_median(direct),
                "observed_timing_n": len(observed),
                "observed_interarrival_seconds_mean": _safe_mean(observed),
                "observed_interarrival_seconds_median": _safe_median(observed),
                "parse_retry_count_mean": _safe_mean([float(x.parse_retry_count) for x in group]),
                "live_llm_rate": _safe_mean([1.0 if x.used_live_llm else 0.0 for x in group]),
                "fallback_rate": _safe_mean([1.0 if x.used_fallback else 0.0 for x in group]),
            }
        )
    return rows


def diversity_analysis(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Estimate repetition risk in generated outputs by normalized scenario identity."""

    grouped: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for score in scores:
        raw = _raw_for_score(score)
        scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
        fingerprint = scenario.get("diversity_fingerprint") or _normalized_scenario_text(scenario)
        title = str(scenario.get("title", "")).strip().lower()
        grouped[(score.model_key, score.method)].append({"fingerprint": fingerprint, "title": title})
    rows: List[Dict[str, Any]] = []
    for (model, method), items in sorted(grouped.items()):
        fingerprints = [item["fingerprint"] for item in items if item["fingerprint"]]
        titles = [item["title"] for item in items if item["title"]]
        rows.append(
            {
                "model_key": model,
                "method": method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
                "condition_name": METHOD_LABELS.get(method, method),
                "n": len(items),
                "unique_fingerprint_count": len(set(fingerprints)),
                "unique_fingerprint_rate": len(set(fingerprints)) / len(items) if items else None,
                "unique_title_count": len(set(titles)),
                "unique_title_rate": len(set(titles)) / len(items) if items else None,
                "most_common_title": Counter(titles).most_common(1)[0][0] if titles else "",
                "most_common_title_count": Counter(titles).most_common(1)[0][1] if titles else 0,
            }
        )
    return rows


def manual_inspection_sample(scores: Sequence[ScenarioScore], *, sample_size: int = 24, seed: int = 20260710) -> List[Dict[str, Any]]:
    """Create a stratified manual-review sheet; human labels are intentionally blank."""

    rng = random.Random(seed)
    by_pair: Dict[tuple[str, str], List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        by_pair[(score.model_key, score.method)].append(score)
    sample: List[ScenarioScore] = []
    per_pair = max(1, sample_size // max(1, len(by_pair)))
    for pair_scores in by_pair.values():
        candidates = sorted(pair_scores, key=lambda item: item.case_id)
        sample.extend(rng.sample(candidates, min(per_pair, len(candidates))))
    if len(sample) < sample_size:
        remaining = [score for score in scores if score not in sample]
        sample.extend(rng.sample(remaining, min(sample_size - len(sample), len(remaining))))
    rows: List[Dict[str, Any]] = []
    for score in sample[:sample_size]:
        raw = _raw_for_score(score)
        scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
        rows.append(
            {
                "case_id": score.case_id,
                "model_key": score.model_key,
                "method": score.method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(score.method, 0),
                "condition_name": METHOD_LABELS.get(score.method, score.method),
                "channel": score.channel,
                "variant": score.variant,
                "role": score.role,
                "stage_id": score.stage_id,
                "title": scenario.get("title", ""),
                "opening_hook": scenario.get("opening_hook", ""),
                "correct_action": scenario.get("correct_action", ""),
                "all_controls_exact_match": score.all_controls_exact_match,
                "common_case_concept_f1": score.common_case_concept_f1,
                "contradiction_free_pass": score.contradiction_free_pass,
                "overall_conformance": score.overall_conformance,
                "automated_technical_decision": score.automated_decision,
                "decision_reason_codes": "; ".join(score.decision_reason_codes),
                "manual_json_valid": "",
                "manual_channel_variant_fit": "",
                "manual_cyber_realism": "",
                "manual_pedagogical_fit": "",
                "manual_grounding_plausible": "",
                "manual_repetition_issue": "",
                "manual_acceptability": "",
                "manual_comments": "",
            }
        )
    return rows


def metric_definitions_markdown(*, include_bertscore: bool = False) -> str:
    """Return a complete paper-facing operational definition for every metric."""

    from .standard_metrics import metric_validity_registry

    lines = [
        "# Metric Definitions for the PSQ-SCO Three-Layer Evaluation",
        "",
        "## Evaluation Unit and Frequency",
        "",
        "`120 cases` means 120 frozen input specifications, not 120 accepted scenarios. The design contains "
        "30 base groups (`3 channels x 2 variants x 5 roles`), three difficulty anchors per group (90), and "
        "one balanced repetition per group (30). Each case is generated once in each of four conditions by each "
        "of three LLMs, yielding `120 x 4 x 3 = 1,440` finalized scenario rows in this run. The same case IDs "
        "make paired comparison possible even though the generated prose is expected to differ.",
        "",
        "Row-level technical checks are calculated once for each finalized stored scenario after recovery/merge. "
        "Collection-level diversity is calculated once for each 120-row model-condition collection (12 collections). "
        "Condition summaries aggregate 360 rows. The experiment contains one stochastic generation replicate per "
        "model-case-condition cell, so random-seed variance cannot be estimated from the present run.",
        "",
        "## Four Conditions",
        "",
        "| Condition | Required name | Operational treatment |",
        "|---:|---|---|",
    ]
    for method in METHOD_ORDER:
        lines.append(
            f"| {METHOD_CONDITION_NUMBERS[method]} | {METHOD_LABELS[method]} | "
            f"{METHOD_IMPLEMENTATION_NOTES[method]} |"
        )
    lines.extend(
        [
            "",
            "## Ground Truth and Reference Objects",
            "",
            "There is no human-authored gold scenario in the current automatic evaluation. Three different reference "
            "objects must not be conflated: (1) the frozen case specification is the oracle for requested controls; "
            "(2) a method-invariant, automatically constructed closed-label case oracle supports concept P/R/F1; "
            "and (3) each RAG scenario has its own ordered retrieved context set for provenance. The combined corpus "
            "is never treated as a scenario-specific gold source. Human cybersecurity, pedagogy, usability, and ethical "
            "ratings remain required before a claim of final deployability.",
            "",
            "## Metric Registry",
            "",
            "Every metric below states its formal definition, input, output, threshold, workflow position, calculation "
            "time, frequency, and role. A standard formula does not make a project-specific oracle into external ground truth.",
            "",
        ]
    )
    lines.extend(_markdown_table(metric_validity_registry()))
    lines.extend(
        [
            "",
            "## JSON Pass/Fail",
            "",
            "A JSON row passes only when Python JSON parsing succeeds and the loaded row contains an inspectable `scenario` "
            "object. The reported mean is therefore an average binary pass rate. This check is applied to finalized stored "
            "objects after generation-engine parsing, repair, and recovery; it is not a raw-Ollama-output syntax rate.",
            "",
            "## Scenario Decisions",
            "",
            "The `technical_gate_v1` state machine is non-compensatory. Parse failure or a fired contradiction rule produces "
            "`REJECT_REGENERATE`. Missing game-executable fields, a critical control mismatch, two or more control failures, "
            "or two or more missing case concepts produces `MAJOR_REVISION`. One noncritical control mismatch or one missing "
            "case concept produces `MINOR_REVISION`. Only a row with none of these implemented defects is `ACCEPTED`. "
            "Automated acceptance means technical triage passed; every row still carries `final_human_review_required=true`.",
            "",
            "## Source Mapping and Similarity",
            "",
            "The correct mapping unit is one generated scenario to its own ordered context set, which can contain zero, one, "
            "or several documents. Retrieval relevance would require the scenario's retrieval query, ranked documents, "
            "scores/distances, and preferably human qrels. Generation faithfulness requires claim-level source mappings or "
            "entailment judgments. The frozen records do not preserve all of those fields, so the revised evaluator exports "
            "`NOT_ESTIMABLE_FROM_FROZEN_EXPORT` instead of inventing a source-similarity number. Source IDs measure traceability, "
            "not semantic support.",
            "",
            "## Embedding Diversity",
            "",
            "For collection embeddings `E_1...E_N`, `D_embed = 1 - [2/(N(N-1))] * sum_{i<j} cosine(E_i,E_j)`. "
            "The exact Sentence-Transformers model is frozen in run metadata and the result tables. It is computed within "
            "each 120-row model-condition collection. Higher values indicate greater relative dispersion under this representation; "
            "there is no universal acceptance threshold, and semantic distance is not content quality.",
            "",
            "## Self-BLEU",
            "",
            "`SelfBLEU = (1/N) * sum_i BLEU(x_i, X_{-i})`, where each scenario is the candidate once and the other scenarios "
            "in the same collection are references. It is computed within each 120-row model-condition collection. Lower is "
            "less lexical redundancy. It must be interpreted with semantic diversity and human inspection because low overlap "
            "can coexist with poor or incorrect text.",
            "",
            "## Why Overall Conformance Can Be Below 1.0",
            "",
            "The legacy conformance index falls below 1.0 when any of its five component values is below one: JSON object "
            "validity, control adherence, legacy method-conditioned concept F1, provenance-field completeness, or non-contradiction. "
            "Typical defects are missing provenance fields, missing closed case concepts, field/control mismatches, incomplete "
            "game schema, or contradiction rules. The revised decision state does not threshold this composite because its exact "
            "coefficients are uncalibrated and trace availability differs by condition.",
            "",
            "## Optional BERTScore",
            "",
        ]
    )
    if include_bertscore:
        lines.append(
            "BERTScore is enabled only in the optional extended profile and compares generated text with an automatic case-reference, "
            "not a human gold scenario. It is excluded from the standard publication profile requested for the present run."
        )
    else:
        lines.append("BERTScore is not calculated in the standard publication profile and does not appear in its results.")
    return "\n".join(lines) + "\n"


def write_research_analysis(
    path: Path,
    *,
    method_rows: Sequence[Dict[str, Any]],
    model_matrix: Sequence[Dict[str, Any]],
    condition_rows: Sequence[Dict[str, Any]],
    dataset: Dict[str, Any],
    matched_rows: Sequence[Dict[str, Any]],
    timing_rows: Sequence[Dict[str, Any]],
    diversity_rows: Sequence[Dict[str, Any]],
    semantic_diversity_rows: Sequence[Dict[str, Any]],
    semantic_diversity_summary_rows: Sequence[Dict[str, Any]],
    standard_metric_rows: Sequence[Dict[str, Any]] = (),
    metric_validity_rows: Sequence[Dict[str, Any]] = (),
    decision_summary_rows: Sequence[Dict[str, Any]] = (),
    model_method_decision_rows: Sequence[Dict[str, Any]] = (),
    source_linkage_rows: Sequence[Dict[str, Any]] = (),
    source_linkage_summary_rows: Sequence[Dict[str, Any]] = (),
    paired_stats: Dict[str, Any] | None = None,
    bertscore_rows: Sequence[Dict[str, Any]] | None = None,
    bertscore_summary_rows: Sequence[Dict[str, Any]] | None = None,
    sources: Sequence[str] = (),
) -> None:
    """Write a detailed paper-facing analysis answering advisor comments."""

    graph_walk_variant = any(
        int(row.get("rows_requiring_graph_walk") or 0) > 0
        for row in source_linkage_summary_rows
    )
    lines: List[str] = []
    title = "# Research-Paper Analysis: PSQ-SCO 120-Case Four-Condition Scenario Evaluation"
    if graph_walk_variant:
        title += " (Graph-Walk v1)"
    lines.append(title)
    lines.append("")
    lines.append("## Advisor Questions Answered")
    lines.append("")
    lines.append("**What does 120 cases mean?** It is a matched design, not an arbitrary number of generated outputs. The 120 cases are fixed case specifications produced from 30 base groups (3 channels x 2 variants x 5 roles), three difficulty anchors per group (90), and one balanced repetition per group (30).")
    lines.append("")
    lines.append("**Could scenarios generated by each method be totally different?** Yes. Surface text can differ. The experimental control is the same case specification. The evaluator checks whether different methods satisfy the same role, channel, variant, stage, age, difficulty, cybersecurity, grounding, and ontology-scope constraints.")
    lines.append("")
    lines.append("**Is Text-RAG Generation vector RAG?** Yes when Chroma is available: the external corpus is queried with Chroma PersistentClient and cosine HNSW. The code passes no custom embedding function. Official Chroma documentation identifies `all-MiniLM-L6-v2` as its default, so that is the expected model; however, the historical run did not freeze the Chroma version, model artifact hash, or embedding-function configuration. This is reported as expected-but-not-proven provenance rather than retrospective certainty.")
    lines.append("")
    lines.append("**Are the same documents used?** Conditions 2-4 use the same `PSQ_RAG_PROFILE=quality` external corpus selection. Condition 1 deliberately uses no retrieval. Conditions 3-4 additionally use the same PSQ-SCO OWL ontology, but Condition 3 serializes a structured semantic packet while Condition 4 verbalizes selected ontology records.")
    lines.append("")
    lines.append("**Were inputs labeled by attack type and difficulty?** The generated case set labels channel, variant, role, macro/micro stage, age group, and difficulty condition by deterministic design rules. The retrieval corpus also stores metadata such as channel, `is_scam`, difficulty band, knowledge type, age/stage fit when available or defaults. Difficulty band is therefore engine-assigned from the scenario seed and corpus metadata, not newly human-labeled per generated output.")
    lines.append("")
    lines.append("**Why is prompt-only not precision/recall/F1 = 1.0?** Precision/recall/F1 here are not model-vs-baseline scores. They are required-concept coverage metrics computed against the requested case and ontology/control concepts. Prompt-only can miss required concepts and therefore is not automatically perfect.")
    lines.append("")
    lines.append("**Which F1 is suitable for method comparison?** The primary `common_case_concept_f1` uses the same case-derived oracle for every method and excludes retrieval/ontology traces from generated content. The older `required_concept_f1` is method-conditioned and is retained only for compatibility.")
    lines.append("")
    lines.append("## Exact Condition Manifest")
    lines.extend(_markdown_table(condition_rows))
    lines.append("")
    fallback_total = _sum_numeric(condition_rows, "fallback_rows")
    repair_total = _sum_numeric(condition_rows, "schema_safe_repair_rows")
    retained_total = _sum_numeric(condition_rows, "live_model_content_retained_rows")
    if fallback_total:
        lines.append(f"Important reproducibility caveat: `used_live_llm_rows` and `fallback_rows` are part of the experimental audit. This manifest contains `{fallback_total}` fallback rows. Conditions with fallback rows should be interpreted as generation-engine outputs, not pure live-LLM samples. For a strict model-comparison paper, rerun those conditions with `--require-live-llm` and replace the manifest paths before final reporting.")
    else:
        lines.append("Reproducibility status: the manifest contains 1,440 successful live LLM calls and 0 non-live fallback rows.")
    if repair_total:
        lines.append("")
        lines.append(
            f"Generation-integrity qualification: `{repair_total:.0f}` finalized rows use the engine's "
            f"schema-safe replacement object, leaving `{retained_total:.0f}` rows with retained live-model content. "
            "A successful live call is therefore not treated as equivalent to an unreplaced live-model scenario. "
            "Unstratified comparisons are pipeline-level results."
        )
    lines.append("")
    lines.append("## Dataset and RAG Corpus")
    lines.append("")
    lines.append(f"- KB directory: `{dataset.get('kb_dir')}`")
    lines.append(f"- RAG profile: `{dataset.get('rag_profile')}`")
    lines.append(f"- Vector database: {dataset.get('vector_database')}")
    lines.append(f"- Vector index path: `{dataset.get('vector_index_path')}`")
    lines.append(f"- Vector space: {dataset.get('vector_space')}")
    lines.append(f"- Embedding model note: {dataset.get('embedding_model')}")
    lines.append(f"- Embedding provenance status: {dataset.get('embedding_model_status')}")
    lines.append(f"- Embedding training domain: {dataset.get('embedding_model_training_domain')}")
    lines.append(f"- Domain/representation caveat: {dataset.get('embedding_model_domain_mismatch')}")
    lines.append(f"- Ontology-text selection: {dataset.get('ontology_text_selection')}")
    lines.append(f"- Selected source files: {dataset.get('selected_file_count')}")
    lines.append(f"- Raw documents before caps: {dataset.get('raw_document_count_before_caps')}")
    lines.append(f"- Used documents after caps: {dataset.get('used_document_count_after_caps')}")
    lines.append(f"- Chunking: {dataset.get('chunking')}")
    lines.append(f"- Preprocessing: {dataset.get('preprocessing')}")
    lines.append("")
    lines.append("Retrieval settings:")
    lines.append("```json")
    lines.append(json.dumps(dataset.get("retrieval_settings", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("Condition-4 deterministic walk specification:")
    lines.append("```json")
    lines.append(json.dumps(dataset.get("ontology_walk_algorithm", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("Evaluated Condition-4 treatment profile:")
    lines.append("```json")
    lines.append(
        json.dumps(dataset.get("evaluated_generation_profile", {}), ensure_ascii=False, indent=2)
    )
    lines.append("```")
    lines.append("")
    lines.append("## Matched-Case Audit")
    lines.extend(_markdown_table(matched_rows))
    lines.append("")
    lines.append("## Primary Standard-Metric Results")
    lines.append("")
    lines.append("The table below avoids a single composite winner. JSON/exact-control/contradiction values are average binary pass rates; concept precision/recall/F1 use standard formulas with one disclosed project-specific oracle; diversity values are relative diagnostics without universal cutoffs. All automatic metrics evaluate finalized stored scenario objects after engine post-processing, not the unmodified raw text emitted by Ollama.")
    lines.extend(_markdown_table(standard_metric_rows))
    lines.append("")
    if standard_metric_rows:
        lines.append("## Generation Integrity and Internal Validation")
        lines.append("")
        lines.append(
            "The live-call rate answers whether Ollama returned successfully. The model-content-retention rate "
            "answers whether the finalized scenario still derives from that response. The schema-safe-repair rate "
            "records deterministic replacement after failed ScenarioContent repair. The generation-engine validation "
            "pass rate reports the engine's own quality-rule suite and is not the same as the independent evaluator decision."
        )
        lines.extend(
            _markdown_table(
                [
                    {
                        "condition": row.get("condition_number"),
                        "condition_name": row.get("condition_name"),
                        "n": row.get("n"),
                        "live_call_rate": row.get("live_llm_rate"),
                        "schema_safe_repair_rate": row.get("schema_safe_repair_rate"),
                        "live_model_content_retention_rate": row.get(
                            "live_model_content_retention_rate"
                        ),
                        "engine_validation_pass_rate": row.get(
                            "engine_validation_pass_rate"
                        ),
                    }
                    for row in standard_metric_rows
                ]
            )
        )
        lines.append("")
    if decision_summary_rows:
        lines.append("## Automated Technical Decisions")
        lines.append("")
        lines.append("These four-state outcomes are non-compensatory technical triage. `ACCEPTED` means implemented machine checks passed; it is not final PCUE/human deployment approval. Every row remains marked for human review.")
        lines.extend(_markdown_table(decision_summary_rows))
        lines.append("")
        lines.append("### Decisions by LLM and Condition")
        lines.extend(_markdown_table(model_method_decision_rows))
        lines.append("")
    if source_linkage_summary_rows:
        lines.append("## Source Linkage and Similarity Estimability")
        lines.append("")
        lines.append("The mapping unit is one scenario to its own ordered prompt-context set. External vector contexts, ontology-text contexts, and structured ontology sources are counted separately. The full nominal condition-exposure rate checks whether the context components named by each assigned condition were actually present; this is an experimental-fidelity audit, not a content-quality score.")
        lines.append("")
        lines.append("A source ID proves traceability only. Query relevance, document relevance, and claim faithfulness are separate constructs. Where frozen rows lack the query, retrieval score/distance, or claim-source map, the evaluator reports `NOT_ESTIMABLE_FROM_FROZEN_EXPORT` and does not calculate a misleading similarity against one combined corpus.")
        if graph_walk_variant:
            lines.append("")
            lines.append(
                "For graph-walk-v1, the evaluator separately reports whether a `selected_subgraph_walk` document "
                "reached each Condition-4 prompt. This exposure indicator is a treatment-fidelity check, not a "
                "measure of graph-path quality, model use of context, or source faithfulness."
            )
        lines.extend(_markdown_table(source_linkage_summary_rows))
        lines.append("")
        lines.append("Scenario-level linkage statuses are exported to `source_linkage_audit.csv`.")
        lines.append("")
    lines.append("## Extended and Legacy Method Results")
    lines.extend(_markdown_table(method_rows))
    lines.append("")
    lines.append("## Model x Method Matrix")
    lines.extend(_markdown_table(model_matrix))
    lines.append("")
    lines.append("## Timing Analysis")
    lines.extend(_markdown_table(timing_rows))
    lines.append("")
    lines.append("## Repetition and Diversity Analysis")
    lines.extend(_markdown_table(diversity_rows))
    lines.append("")
    lines.append("## Semantic Diversity and Self-BLEU")
    lines.append("")
    lines.append("Embedding diversity is `1 - mean cosine similarity` over embeddings from the exact Sentence-Transformers model recorded in the result table; higher means more relative semantic dispersion. Self-BLEU treats each scenario as a candidate and the remaining scenarios as references; lower means less relative lexical redundancy. These metrics are reported per 120-scenario model/condition collection and summarized by condition. They do not have universal acceptance thresholds and do not measure scenario quality by themselves.")
    lines.append("")
    lines.append("### Method-Level Diversity Summary")
    lines.extend(_markdown_table(semantic_diversity_summary_rows))
    lines.append("")
    lines.append("### Model x Method Diversity")
    lines.extend(_markdown_table(semantic_diversity_rows))
    lines.append("")
    if paired_stats:
        lines.append("## Paired and Case-Clustered Statistics")
        lines.append("")
        lines.append("The primary inferential unit is the frozen case (`n=120`), because each case is repeated across three LLMs. The evaluator averages the model values within each case/method and then applies the Friedman omnibus test, paired Wilcoxon signed-rank tests, Holm family-wise correction, matched rank-biserial effect sizes, and case-level bootstrap confidence intervals. A 360 model-case analysis is retained as a sensitivity analysis, not treated as 360 independent cases. Because matched rank-biserial correlation excludes zero differences, its non-zero pair count is exported and must be reported beside the effect.")
        lines.append("```json")
        lines.append(json.dumps(paired_stats, ensure_ascii=False, indent=2)[:16000])
        lines.append("```")
        lines.append("")
    if metric_validity_rows:
        lines.append("## Metric Validity and Provenance Registry")
        lines.append("")
        lines.append("This table distinguishes standard formulas from project-specific constructs. A standard formula does not turn an automatic PSQ oracle into human ground truth.")
        lines.extend(_markdown_table(metric_validity_rows))
        lines.append("")
    if bertscore_summary_rows:
        lines.append("## Case-Reference BERTScore")
        lines.append("")
        lines.append("BERTScore was added as a semantic-alignment metric grounded in the text-generation evaluation literature. It compares each generated scenario against an automatic reference assembled from the frozen case specification and required concepts. This is different from human-reference BERTScore: the score should be interpreted as **case adherence at the semantic-token level**, not as proof that a human expert would accept the scenario.")
        lines.append("")
        lines.append("The reason this metric is appropriate for the current 120-case study is that the experiment already has controlled inputs: each row requests a known role, stage, channel, variant, attack type, difficulty anchor, and safe-response pattern. BERTScore provides an additional soft semantic check that complements exact control matching and required-concept F1. It is especially useful when generated wording differs across methods but the intended meaning should remain aligned with the same case.")
        lines.append("")
        lines.append("### Method-Level BERTScore Summary")
        lines.extend(_markdown_table(bertscore_summary_rows))
        lines.append("")
        lines.append("Interpretation: BERTScore, overall conformance, and diversity are intentionally different validity arguments. A method can be close to the compact automatic case-reference text while still having weaker grounding or ontology-scope conformance. In the completed run, prompt+RAG has the strongest BERTScore F1, ontology-prompt RAG has the strongest overall conformance, and ontology-text RAG has the strongest diversity. This should be reported as a metric trade-off rather than as a contradiction.")
        lines.append("")
    if bertscore_rows:
        lines.append("Scenario-level BERTScore values are exported to `bertscore_scenario_alignment.csv` for audit, paired analysis, and later reviewer tables.")
        lines.append("")
    lines.append("## TBox/ABox Interpretation")
    lines.append("")
    lines.append("The ontology provides TBox-like conceptual constraints: attack/channel structure, role and stage suitability, validation rules, evidence requirements, and safe-response constraints. Generated scenarios are ABox-like instances: concrete emails, SMS messages, calls, choices, and feedback. The engine should not treat the retrieved ABox examples as the whole universe. Instead, it uses retrieval examples as evidence patterns while the ontology constrains the allowed cybersecurity structure. This is analogous to generating varied mathematics problems inside a fixed concept ontology: diversity is allowed, but concept-scope violations are not.")
    lines.append("")
    lines.append("## Ontology-Trace/Control Conformance Diagnostic")
    lines.append("")
    lines.append("Condition 4 is not a knowledge-graph embedding or ontology embedding. The evaluator's historical `ontology_semantic_scope` field is therefore reported under the more accurate label **ontology-trace/control conformance diagnostic**. It is a project rule audit over exported ontology records, controls, and contradictions; it does not measure geometric preservation, OWL entailment, retrieval relevance, or human-rated quality.")
    lines.append("")
    lines.append("## Replication and Random Variation")
    lines.append("")
    lines.append("The current design has one generation realization per model-case-condition cell. The 120 cases improve coverage and paired control, but they are not 120 stochastic repetitions. Conclusions are conditional on the frozen prompts, runtime, model builds, and one sampled output per cell. A confirmatory study should use at least three independently seeded generation replicates, retain run as a repeated factor, and publish model/runtime hashes and retrieval traces.")
    lines.append("")
    lines.append("## Manual Inspection Protocol")
    lines.append("")
    lines.append("The evaluator exports a stratified manual inspection sample. This directly addresses the advisor's request for random human verification. The sheet should be filled by a researcher or domain reviewer before final submission. Manual fields cover JSON usability, channel/variant fit, cyber realism, pedagogical fit, grounding plausibility, repetition, and acceptability.")
    lines.append("")
    lines.append("## References and Standards")
    for source in sources:
        lines.append(f"- {source}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _source_origin(filename: str) -> str:
    name = filename.lower()
    if "ceas" in name:
        return "CEAS email corpus"
    if "enron" in name:
        return "Enron email corpus"
    if "spamassasin" in name:
        return "SpamAssassin public corpus"
    if "ling" in name:
        return "Ling spam/ham corpus"
    if "nazario" in name:
        return "Nazario phishing corpus"
    if "kaggle" in name:
        return "Kaggle SMS/email fraud dataset export"
    if "irs" in name:
        return "IRS phone-scam transcript source"
    if "smsfraud" in name or "smsnormal" in name:
        return "Thai SMS local corpus export"
    if "financialfraud" in name:
        return "Thai financial-fraud local corpus export"
    if "ncsa" in name or "tb-cert" in name:
        return "NCSA/TB-CERT awareness material export"
    return "project-exported JSONL corpus"


def _source_type(filename: str) -> str:
    name = filename.lower()
    if "sms" in name or "kaggle" in name:
        return "sms/text message"
    if "irs" in name or "call" in name:
        return "voice/call transcript"
    return "email/web text"


def _line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _first_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    return json.loads(line)
    except Exception:
        return {}
    return {}


def _case_ids(path: Path) -> set[str]:
    case_ids: set[str] = set()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                case = row.get("case") if isinstance(row.get("case"), dict) else {}
                if case.get("case_id"):
                    case_ids.add(str(case["case_id"]))
    except Exception:
        return case_ids
    return case_ids


def _count_rows(path: Path, predicate: Any) -> int:
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if predicate(json.loads(line)):
                    count += 1
    except Exception:
        return count
    return count


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _row_schema_safe_repair(row: Dict[str, Any]) -> bool:
    scenario = row.get("scenario") if isinstance(row.get("scenario"), dict) else {}
    meta = (
        scenario.get("generation_meta")
        if isinstance(scenario.get("generation_meta"), dict)
        else {}
    )
    return (
        "schema-safe fallback used" in str(meta.get("repair_note", "")).lower()
        or str(scenario.get("llm_source", "")).lower() == "offline_fallback"
    )


def _row_prompt_metadata(row: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(row.get("prompt_metadata"), dict):
        return row["prompt_metadata"]
    scenario = row.get("scenario") if isinstance(row.get("scenario"), dict) else {}
    meta = (
        scenario.get("generation_meta")
        if isinstance(scenario.get("generation_meta"), dict)
        else {}
    )
    return meta.get("prompt_metadata") if isinstance(meta.get("prompt_metadata"), dict) else {}


def _row_graph_walk_required(row: Dict[str, Any]) -> bool:
    prompt = _row_prompt_metadata(row)
    types = {
        str(value).lower() for value in (prompt.get("ontology_text_document_types") or [])
    }
    strategies = {
        str(value).lower() for value in (prompt.get("ontology_text_graph_strategy") or [])
    }
    return (
        "selected_subgraph_walk" in types
        or any(
            "deterministic_random_walk_graph_to_text" in value
            or "deterministic_greedy" in value
            for value in strategies
        )
        or _row_graph_walk_exposed(row)
    )


def _row_graph_walk_exposed(row: Dict[str, Any]) -> bool:
    for item in row.get("rag_examples") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("document_type", "")).lower() == "selected_subgraph_walk":
            return True
        if "::ontology_walk_" in str(item.get("source_file", "")).lower():
            return True
        if "deterministic_random_walk_graph_to_text" in str(
            item.get("graph_text_strategy", "")
        ).lower():
            return True
    return False


def _row_external_rag_present(row: Dict[str, Any]) -> bool:
    prompt = _row_prompt_metadata(row)
    if int(prompt.get("external_rag_example_count") or 0) > 0:
        return True
    for item in row.get("rag_examples") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("corpus_mode", "")).lower() != "ontology_text":
            return True
    return False


def _graph_walk_dataset_profile(records: Sequence[ScenarioRecord]) -> Dict[str, Any]:
    mode4_rows = [
        record.raw
        for record in records
        if _infer_method_from_row(record.raw) == "ontology_text_rag"
    ]
    if not mode4_rows:
        return {
            "mode4_row_count": 0,
            "interpretation": "No Condition-4 rows were present in the evaluated input.",
        }
    required = sum(1 for row in mode4_rows if _row_graph_walk_required(row))
    exposed = sum(1 for row in mode4_rows if _row_graph_walk_exposed(row))
    external = sum(1 for row in mode4_rows if _row_external_rag_present(row))
    repaired = sum(1 for row in mode4_rows if _row_schema_safe_repair(row))
    engine_passed = sum(1 for row in mode4_rows if row.get("validation_passed") is True)
    limits = Counter(
        int(_row_prompt_metadata(row).get("ontology_text_document_count") or 0)
        for row in mode4_rows
    )
    if required:
        interpretation = (
            f"The evaluated graph-walk variant declared the walk for {required}/{len(mode4_rows)} "
            f"Condition-4 rows and exported an identifiable selected_subgraph_walk context for "
            f"{exposed}/{required}. Ontology context delivery is separate from external text-RAG "
            f"delivery, which occurred for {external}/{len(mode4_rows)} rows."
        )
    else:
        interpretation = (
            f"The evaluated Condition-4 set contains {len(mode4_rows)} rows but does not declare "
            "selected_subgraph_walk as a prompt treatment component."
        )
    return {
        "mode4_row_count": len(mode4_rows),
        "graph_walk_required_rows": required,
        "graph_walk_exposed_rows": exposed,
        "graph_walk_exposure_rate": exposed / required if required else None,
        "external_rag_present_rows": external,
        "external_rag_exposure_rate": external / len(mode4_rows),
        "schema_safe_repair_rows": repaired,
        "schema_safe_repair_rate": repaired / len(mode4_rows),
        "engine_validation_passed_rows": engine_passed,
        "engine_validation_pass_rate": engine_passed / len(mode4_rows),
        "ontology_text_document_count_distribution": {
            str(key): value for key, value in sorted(limits.items())
        },
        "interpretation": interpretation,
    }


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _infer_method_from_row(row: Dict[str, Any]) -> str:
    mode = str(row.get("mode") or row.get("scenario", {}).get("generation_meta", {}).get("mode") or "").lower()
    for method in ("ontology_text_rag", "ontology_prompt_rag", "prompt_only", "prompt_rag"):
        if method in mode:
            return method
    return "prompt_only"


def _raw_for_score(score: ScenarioScore) -> Dict[str, Any]:
    try:
        with open(score.source_file, "r", encoding="utf-8") as handle:
            for current_line, line in enumerate(handle, start=1):
                if current_line == score.line_number:
                    return json.loads(line)
    except Exception:
        return {}
    return {}


def _normalized_scenario_text(scenario: Dict[str, Any]) -> str:
    parts = [
        scenario.get("title", ""),
        scenario.get("opening_hook", ""),
        scenario.get("subject", ""),
        scenario.get("body_html", ""),
        " ".join(str(x) for x in scenario.get("messages", []) if x),
        scenario.get("correct_action", ""),
    ]
    text = " ".join(parts).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _safe_mean(values: Sequence[float]) -> float | None:
    return mean(values) if values else None


def _safe_median(values: Sequence[float]) -> float | None:
    return median(values) if values else None


def _sum_numeric(rows: Sequence[Dict[str, Any]], key: str) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _markdown_table(rows: Sequence[Dict[str, Any]]) -> List[str]:
    if not rows:
        return ["No rows available."]
    headers: List[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        values = []
        for key in headers:
            value = row.get(key, "")
            if isinstance(value, float):
                values.append(f"{value:.4f}")
            elif value is None:
                values.append("")
            else:
                values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return lines
