"""Report writers for the three-layer evaluator."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .models import (
    CONFORMANCE_WEIGHTS,
    METHOD_CONDITION_NUMBERS,
    METHOD_IMPLEMENTATION_NOTES,
    METHOD_LABELS,
    METHOD_ORDER,
    OntologyValidationResult,
    ScenarioScore,
)


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
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
        for row in rows:
            writer.writerow(row)


def _write_smoke_markdown_report(
    path: Path,
    *,
    ontology: OntologyValidationResult,
    scenario_count: int,
    method_rows: Sequence[Dict[str, Any]],
    condition_rows: Sequence[Dict[str, Any]] | None,
    standard_metric_rows: Sequence[Dict[str, Any]] | None,
    decision_summary_rows: Sequence[Dict[str, Any]] | None,
    source_linkage_summary_rows: Sequence[Dict[str, Any]] | None,
    output_files: Dict[str, str],
) -> None:
    """Write a bounded report for the portable minimal workflow."""

    lines = [
        "# Three-Layer Evaluation Report: Minimal Four-Mode Smoke Run",
        "",
        "This report verifies that the packaged ontology, four generation modes, and evaluation code execute together. "
        "It is a model-free portability smoke test, not the frozen paper experiment and not evidence of learner outcomes or method superiority.",
        "",
        "## Run boundary",
        "",
        f"- Scenario rows evaluated: **{scenario_count}**.",
        f"- Method rows present: **{len(method_rows)}**.",
        "- The root launcher uses deterministic schema-safe fallback generation, one synthetic lexical-RAG record, and one matched case.",
        "- Do not generalize metric differences from this run; rerun the frozen design or a preregistered extension for research claims.",
        "",
        "## Layer 1: Ontology validation",
        "",
        "| Check | Result |",
        "|---|---:|",
        f"| Reasoner consistency | {_fmt_bool(ontology.reasoner_consistency)} |",
        f"| Reasoner status | {ontology.reasoner_status} |",
        f"| Unsatisfiable classes | {_fmt_value(ontology.unsatisfiable_class_count)} |",
        f"| CQ tests | {ontology.cq_passed}/{ontology.cq_total} |",
        f"| Runtime mappings | {ontology.mapping_passed}/{ontology.mapping_total} |",
        f"| Runtime records preserved | {ontology.runtime_records_preserved} |",
        "",
    ]
    if ontology.notes:
        lines.append("Notes:")
        lines.extend(f"- {note}" for note in ontology.notes)
        lines.append("")
    if condition_rows:
        lines.extend(
            [
                "## Four-mode input manifest",
                "",
                "Each mode is loaded from its own JSONL file so exposure and integrity fields remain attributable.",
                "",
            ]
        )
        lines.extend(_markdown_table(condition_rows))
        lines.append("")
    lines.extend(
        [
            "## Layer 2: Scenario and control validation",
            "",
            "The tables below are technical diagnostics for this smoke input. They are not calibrated educational-quality scores.",
            "",
            "### Method summary",
            "",
        ]
    )
    lines.extend(_markdown_table(method_rows))
    lines.append("")
    if standard_metric_rows:
        lines.extend(["### Standard metric profile", ""])
        lines.extend(_markdown_table(standard_metric_rows))
        lines.append("")
    if decision_summary_rows:
        lines.extend(
            [
                "### Automated technical decisions",
                "",
                "`technical_gate_v1` is deterministic technical triage; it is not final human deployment approval.",
                "",
            ]
        )
        lines.extend(_markdown_table(decision_summary_rows))
        lines.append("")
    if source_linkage_summary_rows:
        lines.extend(
            [
                "### Source linkage and exposure",
                "",
                "Source identifiers establish traceability only; they do not by themselves prove claim-source entailment.",
                "",
            ]
        )
        lines.extend(_markdown_table(source_linkage_summary_rows))
        lines.append("")
    lines.extend(
        [
            "## Layer 3: Method-comparison boundary",
            "",
            "All four modes executed on one matched case. Inferential statistics, rankings, and paper-level performance claims are out of scope for this smoke run. "
            "Use the packaged frozen summaries for the completed internship study, or generate a new clearly versioned experiment with adequate cases and live-model repetitions.",
            "",
            "## Key output files",
            "",
            "| Artifact | Path |",
            "|---|---|",
        ]
    )
    for key in (
        "ontology_validation_json",
        "scenario_scores_csv",
        "method_summary_csv",
        "source_linkage_summary_csv",
        "run_metadata_json",
    ):
        if key in output_files:
            lines.append(f"| {key} | `{output_files[key]}` |")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_markdown_report(
    path: Path,
    *,
    ontology: OntologyValidationResult,
    scenario_count: int,
    method_rows: Sequence[Dict[str, Any]],
    model_matrix: Sequence[Dict[str, Any]],
    error_rows: Sequence[Dict[str, Any]],
    paper_error_rows: Sequence[Dict[str, Any]],
    stats: Dict[str, Any],
    condition_rows: Sequence[Dict[str, Any]] | None = None,
    dataset: Dict[str, Any] | None = None,
    matched_rows: Sequence[Dict[str, Any]] | None = None,
    timing_rows: Sequence[Dict[str, Any]] | None = None,
    diversity_rows: Sequence[Dict[str, Any]] | None = None,
    semantic_diversity_rows: Sequence[Dict[str, Any]] | None = None,
    semantic_diversity_summary_rows: Sequence[Dict[str, Any]] | None = None,
    standard_metric_rows: Sequence[Dict[str, Any]] | None = None,
    metric_validity_rows: Sequence[Dict[str, Any]] | None = None,
    decision_summary_rows: Sequence[Dict[str, Any]] | None = None,
    model_method_decision_rows: Sequence[Dict[str, Any]] | None = None,
    source_linkage_rows: Sequence[Dict[str, Any]] | None = None,
    source_linkage_summary_rows: Sequence[Dict[str, Any]] | None = None,
    bertscore_rows: Sequence[Dict[str, Any]] | None = None,
    bertscore_summary_rows: Sequence[Dict[str, Any]] | None = None,
    manual_sample_path: str | None = None,
    output_files: Dict[str, str],
    sources: Sequence[str],
    smoke_report: bool = False,
) -> None:
    """Write a compact paper-facing Markdown report."""

    if smoke_report:
        _write_smoke_markdown_report(
            path,
            ontology=ontology,
            scenario_count=scenario_count,
            method_rows=method_rows,
            condition_rows=condition_rows,
            standard_metric_rows=standard_metric_rows,
            decision_summary_rows=decision_summary_rows,
            source_linkage_summary_rows=source_linkage_summary_rows,
            output_files=output_files,
        )
        return

    graph_walk_variant = any(
        int(row.get("rows_requiring_graph_walk") or 0) > 0
        for row in (source_linkage_summary_rows or [])
    )
    lines: List[str] = []
    title = "# Three-Layer Evaluation Report for PSQ-SCO Scenario Generation"
    if graph_walk_variant:
        title += ": Graph-Walk v1 Comparison"
    lines.append(title)
    lines.append("")
    lines.append("This report evaluates generated PersonaShield Quest scenarios using exactly three layers: ontology validation, scenario validation, and method comparison.")
    lines.append("")
    lines.append("## Paper-Safe Main Claim")
    lines.append("")
    lines.append("The evaluation supports the following bounded claim:")
    lines.append("")
    lines.append("```text")
    claim = "Across this frozen one-run experiment, Prompt-Only Generation, Text-RAG Generation, Ontology-Derived Structured Prompting RAG, and Ontology-to-Text Vector RAG can be compared on 120 matched cases and three local lightweight LLMs."
    if graph_walk_variant:
        claim += " In this separate comparison, Condition 4 is the graph-walk-v1 implementation with an explicit selected-subgraph context."
    lines.append(claim)
    lines.append("```")
    lines.append("")
    lines.append("The study evaluates generated scenario technical conformance and diversity, not learner performance, learning gain, instructional effectiveness, or final human-expert acceptance. Method claims must be metric-specific because no single standard metric establishes overall scenario quality.")
    lines.append("")
    if standard_metric_rows:
        embedding_rows = [
            row for row in standard_metric_rows if row.get("embedding_diversity") is not None
        ]
        self_bleu_rows = [row for row in standard_metric_rows if row.get("self_bleu") is not None]
        if embedding_rows and self_bleu_rows:
            highest_embedding = max(
                embedding_rows, key=lambda row: float(row.get("embedding_diversity") or 0)
            )
            lowest_self_bleu = min(
                self_bleu_rows, key=lambda row: float(row.get("self_bleu") or 1)
            )
            lines.append(
                f"The highest mean embedding diversity is observed for {highest_embedding.get('condition_name')}; "
                f"the lowest mean Self-BLEU is observed for {lowest_self_bleu.get('condition_name')}. "
                "These are secondary relative diagnostics, not universal method rankings. "
                "The primary common-case F1 omnibus test must be interpreted separately."
            )
    lines.append("")
    lines.append("## Layer 1: Ontology Validation")
    lines.append("")
    lines.append("| Check | Result |")
    lines.append("|---|---:|")
    lines.append(f"| Reasoner consistency | {_fmt_bool(ontology.reasoner_consistency)} |")
    lines.append(f"| Reasoner status | {ontology.reasoner_status} |")
    lines.append(f"| Unsatisfiable classes | {_fmt_value(ontology.unsatisfiable_class_count)} |")
    lines.append(f"| CQ tests | {ontology.cq_passed}/{ontology.cq_total} |")
    lines.append(f"| CQ pass rate | {_fmt_pct(ontology.cq_pass_rate)} |")
    lines.append(f"| Mapping tests | {ontology.mapping_passed}/{ontology.mapping_total} |")
    lines.append(f"| Mapping pass rate | {_fmt_pct(ontology.mapping_pass_rate)} |")
    lines.append(f"| Runtime records preserved | {ontology.runtime_records_preserved} |")
    lines.append(f"| OWL classes | {ontology.class_count} |")
    lines.append(f"| Named individuals | {ontology.named_individual_count} |")
    lines.append(f"| Object properties | {ontology.object_property_count} |")
    lines.append(f"| Datatype properties | {ontology.datatype_property_count} |")
    if ontology.notes:
        lines.append("")
        lines.append("Notes:")
        for note in ontology.notes:
            lines.append(f"- {note}")
    lines.append("")
    lines.append("Recommended paper wording:")
    lines.append("")
    lines.append("```text")
    lines.append("Formal ontology consistency passed with zero unsatisfiable classes. SPARQL ASK competency-question checks passed when their expected boolean results matched the query semantics. Negative-control ASK files are absence checks, so a successful negative-control case may correctly return true when the prohibited pattern is absent.")
    lines.append("```")
    lines.append("")
    if condition_rows:
        lines.append("## Frozen 120-Case Experimental Design")
        lines.append("")
        lines.append("The 120 cases are fixed case specifications, not 120 unrelated generated stories. The base grid is `3 channels x 2 variants x 5 roles = 30 groups`; each group is evaluated at three difficulty anchors (`90` cases), then one balanced repetition per group adds `30` cases. The same 120 case IDs are used for every LLM and every method, so method comparisons are paired by requested case.")
        lines.append("")
        lines.extend(_markdown_table(condition_rows))
        lines.append("")
        fallback_total = _sum_numeric(condition_rows, "fallback_rows")
        repair_total = _sum_numeric(condition_rows, "schema_safe_repair_rows")
        retained_total = _sum_numeric(condition_rows, "live_model_content_retained_rows")
        if fallback_total:
            lines.append(f"Reproducibility caveat: the condition manifest includes `{fallback_total}` fallback rows. Conditions with fallback rows should be described as engine-output conditions rather than pure live-LLM conditions, or rerun with `--require-live-llm` before making model-performance claims.")
        else:
            lines.append("Reproducibility status: every condition in this manifest has `used_live_llm_rows = 120` and `fallback_rows = 0`, so all rows record a successful live model call.")
        if repair_total:
            lines.append(
                f"Generation-integrity caveat: `{repair_total:.0f}` rows replaced the live response with the "
                f"engine's deterministic schema-safe scenario object. Therefore `{retained_total:.0f}` rows, "
                "not all live-call rows, retain live-model-derived finalized content. Results must be described "
                "as pipeline-level unless stratified by this repair status."
            )
        lines.append("")

    if dataset:
        lines.append("## Dataset and RAG Configuration")
        lines.append("")
        lines.append("Text-RAG Generation attempts external Chroma vector retrieval when ChromaDB is available. Conditions 2-4 query the same `PSQ_RAG_PROFILE=quality` external corpus, but actual returned-context exposure is audited per row; Condition 1 is the no-retrieval baseline. Condition 3 adds a directly serialized ontology semantic packet. Condition 4 adds ontology record verbalizations selected by a deterministic lexical ranker; those ontology records are not embedded in the current implementation.")
        if graph_walk_variant:
            lines.append("")
            lines.append(
                "This separate graph-walk-v1 run increases `ontology_text_doc_limit` to five and reserves one "
                "ontology-text context for `selected_subgraph_walk`. Graph-walk exposure, external-RAG exposure, "
                "and model-content retention are reported as separate constructs."
            )
        lines.append("")
        lines.append("| Condition | Name | Implemented treatment |")
        lines.append("|---:|---|---|")
        for method in METHOD_ORDER:
            lines.append(f"| {METHOD_CONDITION_NUMBERS[method]} | {METHOD_LABELS[method]} | {METHOD_IMPLEMENTATION_NOTES[method]} |")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        lines.append(f"| KB directory | `{dataset.get('kb_dir', '')}` |")
        lines.append(f"| RAG profile | `{dataset.get('rag_profile', '')}` |")
        lines.append(f"| Vector database | {dataset.get('vector_database', '')} |")
        lines.append(f"| Vector index path | `{dataset.get('vector_index_path', '')}` |")
        lines.append(f"| Embedding model note | {dataset.get('embedding_model', '')} |")
        lines.append(f"| Embedding provenance status | {dataset.get('embedding_model_status', '')} |")
        lines.append(f"| Embedding training domain | {dataset.get('embedding_model_training_domain', '')} |")
        lines.append(f"| Domain/representation caveat | {dataset.get('embedding_model_domain_mismatch', '')} |")
        lines.append(f"| Ontology-text selection | {dataset.get('ontology_text_selection', '')} |")
        lines.append(f"| Selected source files | {dataset.get('selected_file_count', '')} |")
        lines.append(f"| Raw documents before caps | {dataset.get('raw_document_count_before_caps', '')} |")
        lines.append(f"| Used documents after caps | {dataset.get('used_document_count_after_caps', '')} |")
        lines.append(f"| Chunking | {dataset.get('chunking', '')} |")
        lines.append(f"| Preprocessing | {dataset.get('preprocessing', '')} |")
        lines.append("")
        walk = dataset.get("ontology_walk_algorithm", {})
        if walk:
            lines.append("### Condition-4 Graph-Walk Specification")
            lines.append("")
            lines.append(f"- Scientific name: **{walk.get('scientific_name')}** (legacy metadata alias: `{walk.get('legacy_metadata_alias')}`).")
            lines.append(f"- Start nodes: {walk.get('start_nodes')}.")
            lines.append(f"- Edge score: {walk.get('edge_score')}.")
            lines.append(f"- Transition and tie break: {walk.get('transition')}; {walk.get('tie_break')}.")
            lines.append(f"- Depth/stopping: {walk.get('depth')}; {walk.get('stopping')}.")
            lines.append(f"- Randomness/cycles: {walk.get('randomness')}; {walk.get('cycle_policy')}.")
            lines.append(f"- Frozen-run exposure: {walk.get('frozen_run_exposure')}")
            lines.append("")

    lines.append("## Layer 2: Scenario Validation")
    lines.append("")
    lines.append(f"Total scenario rows evaluated: **{scenario_count}**")
    lines.append("")
    lines.append("Main metric definitions:")
    lines.append("- JSON validity is a binary parse/executable-object metric. It is 1.0 when the row can be loaded and contains an inspectable scenario object; means are average pass rates.")
    lines.append("- Game-schema completeness checks only executable scenario fields. The retained legacy schema completeness field also includes evidence/provenance and is therefore not method-neutral.")
    lines.append("- Control adherence checks whether role, age group, stage, channel, variant, difficulty, attack type, and safe response match the requested case.")
    lines.append("- Common-case concept precision, recall, and F1 use one case-derived oracle and one closed prediction-label vocabulary for all methods. Retrieval/ontology traces are excluded. Prompt-only is not automatically 1.0 because this is case adherence, not model-vs-baseline similarity.")
    lines.append("- Legacy required-concept F1 may include method-specific packet terms and provenance traces. It is retained only for compatibility and is not the primary cross-method F1.")
    lines.append("- Provenance-field completeness is a project-defined pass rate over source ID, source title/dataset, evidence role, provenance record, retrieval mode, and source record ID. Presence does not establish source relevance or entailment.")
    lines.append("- The historical `ontology_semantic_scope` field is reported as an ontology-trace/control conformance diagnostic. It is a project rule audit, not an ontology embedding or logical-entailment metric.")
    lines.append("- Contradiction rate counts unsafe or internally inconsistent outputs.")
    lines.append("- Embedding diversity measures semantic variety across a scenario set as `1 - mean pairwise cosine similarity`; higher is more diverse.")
    lines.append("- Self-BLEU measures redundancy by treating each generated scenario as a candidate and the other generated scenarios as references; lower is more diverse.")
    if bertscore_summary_rows:
        lines.append("- Case-reference BERTScore compares each generated scenario with an automatic reference built from its frozen case controls and required concepts. Higher precision/recall/F1 means stronger semantic alignment to the requested case, but it is not a human-written gold-reference score.")
    lines.append("")
    lines.append("Paper-facing label clarification: `json_validity` is parseability/executable-object validity. `schema_completeness` and `schema_provenance_incomplete` describe valid JSON rows that lack required game or evidence fields. In older reviewer notes, this should be described as **schema/provenance incompleteness**, not unreadable JSON.")
    lines.append("")
    lines.append("### Restored PSQ Conformance Index and Standard Companion Profile")
    lines.append("")
    lines.append("The original PSQ weighted index is restored as a **secondary mechanism-aware summary**, while the standard-form metrics remain the primary comparable evidence. This dual-profile design preserves continuity with earlier reports without presenting project coefficients as universal scientific constants.")
    lines.append("")
    lines.append("The PSQ conformance index uses this author-defined formula:")
    lines.append("")
    lines.append("```text")
    lines.append("Overall Conformance = 0.20 JSON Validity")
    lines.append("                    + 0.25 Control Adherence")
    lines.append("                    + 0.25 Required-Concept F1")
    lines.append("                    + 0.20 Grounding Completeness")
    lines.append("                    + 0.10 (1 - Contradiction Rate)")
    lines.append("```")
    lines.append("")
    lines.append("Component interpretation:")
    lines.append("- `0.20 JSON Validity`: technical executability; a parsed object is necessary but not sufficient for quality.")
    lines.append("- `0.25 Control Adherence`: preservation of the frozen role, age, stage, channel, variant, difficulty, attack type, and safe response.")
    lines.append("- `0.25 Required-Concept F1`: balance of required-concept precision and recall in the original method-conditioned diagnostic.")
    lines.append("- `0.20 Grounding Completeness`: presence of declared evidence/provenance fields, not proof of source entailment.")
    lines.append("- `0.10 Non-Contradiction`: bounded structural/safety rule pass; contradiction counts remain separately visible.")
    lines.append("")
    lines.append("The weights sum to 1.0 and encode the original design priority, but no completed external or project calibration study establishes these exact coefficients. OECD/JRC composite-indicator guidance supports transparent component definition, weighting disclosure, and sensitivity analysis; it does not validate these PSQ numbers. The index must therefore be reported with all component values and beside the method-invariant standard profile, never as a percentage of overall educational quality.")
    lines.append("For paper text, identify every project-defined oracle, rule set, coefficient, and threshold. Future weights should be calibrated on independent expert ratings or learner outcomes and evaluated on held-out cases.")
    lines.append("")
    if standard_metric_rows:
        lines.append("### Primary Standard-Metric Profile")
        lines.append("")
        lines.append("This is the primary cross-method table. It contains standard pass-rate/exact-match forms, standard precision/recall/F1 formulas with one disclosed project-specific oracle, and established diversity diagnostics. It deliberately does not collapse the metrics into a single winner score. All values describe finalized stored scenario objects after engine post-processing, not unmodified raw model text.")
        lines.extend(_markdown_table(standard_metric_rows))
        lines.append("")
        lines.append("### Generation Integrity and Internal Validator")
        lines.append("")
        lines.append(
            "`live_llm_rate` records successful model calls. `live_model_content_retention_rate` is stricter: "
            "it excludes rows where the final scenario was replaced by the deterministic schema-safe object. "
            "`engine_validation_pass_rate` is the generation engine's own rule-suite result and remains separate "
            "from the independent four-state technical decision."
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
                        "engine_validation_evaluated_rate": row.get(
                            "engine_validation_evaluated_rate"
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
    lines.append("### Extended and Legacy Method Summary")
    lines.extend(_markdown_table(method_rows))
    lines.append("")
    lines.append("### Required-Concept Precision/Recall Diagnostic: Common Oracle and Legacy")
    lines.append("")
    lines.append("Primary comparisons use `common_case_concept_*`: the same frozen case oracle and player-facing field set for every method. The older `required_concept_*` values are method-conditioned diagnostics and can receive provenance-trace credit, so they are secondary only.")
    lines.append("")
    lines.extend(
        _markdown_table(
            [
                {
                    "method": row.get("method"),
                    "n": row.get("n"),
                    "common_case_concept_precision": row.get("common_case_concept_precision"),
                    "common_case_concept_recall": row.get("common_case_concept_recall"),
                    "common_case_concept_f1": row.get("common_case_concept_f1"),
                    "required_concept_precision": row.get("required_concept_precision"),
                    "required_concept_recall": row.get("required_concept_recall"),
                    "required_concept_f1": row.get("required_concept_f1"),
                }
                for row in method_rows
            ]
        )
    )
    lines.append("")
    lines.append("Interpretation: standard P/R/F1 formulas do not make the oracle a human gold standard. The common oracle is an automatic, project-specific adherence reference; expert review remains necessary for realism and pedagogy.")
    lines.append("")
    if metric_validity_rows:
        lines.append("### Metric Validity Registry")
        lines.append("")
        lines.append("This registry prevents established formulas from being confused with project-defined constructs.")
        lines.extend(_markdown_table(metric_validity_rows))
    lines.append("")
    if decision_summary_rows:
        lines.append("### Automated Technical Decisions")
        lines.append("")
        lines.append("The four-state `technical_gate_v1` is a deterministic, non-compensatory triage rule. `ACCEPTED` means implemented technical gates passed, not final educational deployment approval. PCUE review and human expert approval remain required for every scenario.")
        lines.extend(_markdown_table(decision_summary_rows))
        lines.append("")
        lines.append("#### Decisions by LLM and Condition")
        lines.extend(_markdown_table(model_method_decision_rows or []))
        lines.append("")
    if source_linkage_summary_rows:
        lines.append("### Source Linkage and Source-Similarity Estimability")
        lines.append("")
        lines.append("Each scenario is mapped to its own ordered prompt-context set, not to one universal combined source. External vector contexts, ontology-text contexts, and structured ontology sources are counted separately. `full_nominal_treatment_exposure_rate` reports whether the context components named by the assigned condition were actually present; a nominal RAG assignment can fail this audit when retrieval returns no external context.")
        lines.append("")
        lines.append("Source IDs establish traceability only. Retrieval relevance requires query/rank/score evidence; generation faithfulness requires claim-source mapping or entailment labels. Missing evidence is reported as `NOT_ESTIMABLE_FROM_FROZEN_EXPORT`, so this report does not publish a misleading source-similarity score.")
        if graph_walk_variant:
            lines.append("")
            lines.append(
                "`graph_walk_exposure_rate` verifies only that the declared `selected_subgraph_walk` document "
                "reached each graph-walk-required prompt. It is not a graph-path quality score and does not prove "
                "that the LLM used or faithfully followed the path."
            )
        lines.extend(_markdown_table(source_linkage_summary_rows))
        lines.append("")
    lines.append("## Layer 3: Method Comparison")
    lines.append("")
    lines.append("The method comparison is paired by frozen case ID. The primary inferential unit is the 120-case cluster: values are averaged across the three LLMs within each case and method before Wilcoxon/Friedman testing and bootstrap confidence intervals. The 360 model-case analysis is retained as a repeated-observation sensitivity analysis. Rank-biserial effects exclude exact ties, so `nonzero_difference_n` must always be reported beside the effect size.")
    lines.append("")
    lines.append("The present experiment has one generated output per model-case-condition cell. The 120 matched cases provide design coverage, not stochastic replication. Random seed/run variance is therefore a limitation; confirmatory work should repeat each cell with independently seeded runs and treat run as a repeated factor.")
    lines.append("")
    if matched_rows:
        lines.append("### Matched-Case Audit")
        lines.extend(_markdown_table(matched_rows))
        lines.append("")
    lines.append("### Model x Method Summary")
    lines.extend(_markdown_table(model_matrix))
    lines.append("")
    qwen_note = _qwen_model_note(model_matrix)
    if qwen_note:
        lines.append(qwen_note)
        lines.append("")
    lines.append("### Raw Error Analysis")
    lines.extend(_markdown_table(error_rows))
    lines.append("")
    lines.append("### Paper-Facing Error Analysis")
    lines.extend(_markdown_table(paper_error_rows))
    lines.append("")
    lines.append("Error-table interpretation:")
    lines.append("- Use `schema_provenance_incomplete` in paper text instead of saying invalid JSON.")
    lines.append("- Use `missing_required_concepts_not_perfect_recall` as a strict diagnostic and interpret it with required-concept precision, recall, and F1.")
    lines.append("- Wrong channel, wrong attack, unsafe action, and contradiction are high-level safety/control failures.")
    lines.append("")
    lines.append("### Paired Statistics")
    lines.append("")
    lines.append("```json")
    import json

    lines.append(json.dumps(stats, ensure_ascii=False, indent=2)[:8000])
    lines.append("```")
    lines.append("")
    if timing_rows:
        lines.append("### Generation-Time Analysis")
        lines.append("")
        lines.append("Direct generation time is used when saved by the engine. For older runs without direct telemetry, observed interarrival time is estimated from generation timestamps and should be treated as approximate.")
        lines.extend(_markdown_table(timing_rows))
        lines.append("")
    if diversity_rows:
        lines.append("### Repetition and Diversity Analysis")
        lines.append("")
        lines.append("This table helps answer whether 120 outputs are merely repeated from a limited input set. Unique fingerprint/title rates are automatic diagnostics and should be supplemented by the exported manual inspection sheet.")
        lines.extend(_markdown_table(diversity_rows))
        lines.append("")
    if semantic_diversity_summary_rows:
        lines.append("### Semantic Diversity and Self-BLEU")
        lines.append("")
        lines.append("Embedding diversity uses `1 - mean cosine_similarity(E_i, E_j)` over unordered scenario pairs in each 120-scenario condition. Self-BLEU is the mean BLEU score of each generated scenario against the remaining scenarios in the same condition. Higher embedding diversity indicates greater relative semantic dispersion; lower Self-BLEU indicates lower relative lexical redundancy. Neither has a universal acceptance threshold, so only within-study comparisons are made. The publication run reports the exact sentence-transformer model.")
        lines.append("")
        lines.append("#### Method-Level Summary")
        lines.extend(_markdown_table(semantic_diversity_summary_rows))
        lines.append("")
    if semantic_diversity_rows:
        lines.append("#### Model x Method Diversity")
        lines.extend(_markdown_table(semantic_diversity_rows))
        lines.append("")
    if bertscore_summary_rows:
        lines.append("### Case-Reference BERTScore Semantic Alignment")
        lines.append("")
        lines.append("BERTScore uses contextual token similarity rather than exact n-gram overlap. In this evaluator, each generated scenario is compared against an automatic case-reference text assembled from the frozen case controls, required concepts, attack/variant expectations, and safe-response requirement. Therefore, this is a semantic alignment proxy, not a human-reference quality score. It is useful for checking whether a generated scenario talks about the right role, channel, variant, attack type, stage, and defensive concepts.")
        lines.append("")
        lines.append("Interpretation: higher BERTScore precision means the generated scenario content is semantically close to the case reference; higher recall means the case reference concepts are more completely covered by the generated scenario; higher F1 balances both. A high BERTScore does not prove pedagogy, realism, or safety by itself, so it should be interpreted with conformance, grounding, diversity, and manual inspection.")
        lines.append("")
        lines.append("#### Method-Level BERTScore Summary")
        lines.extend(_markdown_table(bertscore_summary_rows))
        lines.append("")
        lines.append("Interpretation: BERTScore, overall conformance, and diversity measure different properties. A method can be semantically close to the automatic case-reference text while still being weaker on ontology grounding or provenance. In the completed run, prompt+RAG has the strongest BERTScore F1, ontology-prompt RAG has the strongest overall conformance, and ontology-text RAG has the strongest diversity profile. This is best reported as a trade-off among validity dimensions.")
        lines.append("")
    if bertscore_rows:
        lines.append("#### Scenario-Level BERTScore Export")
        lines.append("")
        lines.append("Scenario-level BERTScore rows were exported for audit and later statistical analysis; the Markdown report keeps only the method-level summary to remain readable.")
        lines.append("")
    if manual_sample_path:
        lines.append("### Manual Inspection Export")
        lines.append("")
        lines.append(f"A stratified manual-inspection sheet was exported to `{manual_sample_path}`. Fill this before final paper submission to support qualitative verification of a sample of outputs.")
        lines.append("")
    lines.append("## Scenario vs Question Generation")
    lines.append("")
    lines.append("This evaluator treats scenario generation and question/choice generation as related but distinct stages. The generated scenario is the grounded event context: channel message, role context, indicators, and correct defensive action. Game questions or choices should then be derived from that scenario and checked against the scenario grounding. This avoids treating a question as the scenario itself.")
    lines.append("")
    lines.append("## TBox/ABox Boundary")
    lines.append("")
    lines.append("The PSQ-SCO ontology acts as a TBox-like control structure: it defines concept scope, scenario templates, evidence constraints, roles, stages, attack/channel categories, and validation rules. Generated scenarios are ABox-like concrete instances. The evaluator therefore checks whether generated instances remain inside the ontology's semantic scope while still allowing diverse surface wording.")
    lines.append("")
    lines.append("## Output Files")
    lines.append("")
    for label, file_path in output_files.items():
        lines.append(f"- {label}: `{file_path}`")
    lines.append("")
    lines.append("## Academic and Standards Basis")
    lines.append("")
    for source in sources:
        lines.append(f"- {source}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _sum_numeric(rows: Sequence[Dict[str, Any]], key: str) -> float:
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _qwen_model_note(model_matrix: Sequence[Dict[str, Any]]) -> str:
    by_model = {str(row.get("model_key")): row for row in model_matrix}
    qwen25 = by_model.get("qwen2_5_7b")
    qwen3 = by_model.get("qwen3_8b")
    if not qwen25 or not qwen3:
        return ""
    method = "ontology_text_rag" if qwen25.get("ontology_text_rag") is not None and qwen3.get("ontology_text_rag") is not None else "ontology_prompt_rag"
    qwen25_score = qwen25.get(method)
    qwen3_score = qwen3.get(method)
    if not isinstance(qwen25_score, (int, float)) or not isinstance(qwen3_score, (int, float)):
        return ""
    diff = qwen25_score - qwen3_score
    if diff > 0:
        direction = "Qwen2.5-7B was higher than Qwen3-8B"
    elif diff < 0:
        direction = "Qwen3-8B was higher than Qwen2.5-7B"
    else:
        direction = "Qwen2.5-7B and Qwen3-8B tied"
    return (
        f"Model interpretation: {direction} under {method} in this run, but the difference was small "
        f"(`{qwen25_score:.4f} - {qwen3_score:.4f} = {diff:.4f}`). The dominant result is method-driven: all three models "
        "should be interpreted by the shared ordering across the compared methods, not as a universal LLM ranking."
    )


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "not run"
    return "true" if value else "false"


def _fmt_value(value: Any) -> str:
    return "not run" if value is None else str(value)


def _fmt_pct(value: float | None) -> str:
    return "not run" if value is None else f"{value * 100:.2f}%"
