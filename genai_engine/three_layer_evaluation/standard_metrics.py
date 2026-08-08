"""Publication-facing metric registry and standard-method summaries.

The evaluator distinguishes a standard statistical formula from the project-
specific construct supplied to that formula. For example, precision, recall,
and F1 are standard measures, but the PersonaShield Quest case-concept oracle
is a study operationalization rather than an external human gold standard.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Dict, List, Sequence

from .models import METHOD_CONDITION_NUMBERS, METHOD_LABELS, METHOD_ORDER, ScenarioScore


def metric_validity_registry() -> List[Dict[str, Any]]:
    """Return an auditable registry of metric provenance and interpretation."""

    rows = [
        {
            "metric": "json_parse_pass_rate",
            "display_name": "JSON parse / scenario-object pass rate",
            "construct": "Technical executability of the finalized scenario record",
            "classification": "standard binary pass-rate form",
            "formula": "mean(I[row parses and contains an inspectable scenario object])",
            "direction": "higher is better",
            "unit_of_analysis": "scenario row; aggregated as a proportion",
            "why_used": "A game engine cannot inspect or deploy a record that cannot be parsed into the required object.",
            "interpretation": "1.00 means every finalized row parsed; it says nothing about whether the prose is realistic or educationally effective.",
            "study_specific_part": "PersonaShield Quest scenario-object requirement",
            "primary_or_secondary": "primary technical validity",
            "reference": "Arithmetic mean of a disclosed binary indicator; no external content-quality standard is claimed",
            "threshold_status": "No universal quality threshold; pass/fail follows the disclosed PSQ object contract.",
            "reporting_rule": "Report numerator, denominator, and percentage; call it a pass rate, not content accuracy.",
            "limitation": "Does not establish content quality or deployability.",
        },
        {
            "metric": "generation_integrity_rates",
            "display_name": "Live-call, model-content-retention, and schema-safe-repair rates",
            "construct": "Whether a finalized scenario preserves content derived from a successful live LLM response",
            "classification": "study-defined lineage audit reported with standard binary pass-rate forms",
            "formula": (
                "LiveCallRate=mean(I[live call succeeded]); "
                "RepairRate=mean(I[final scenario was replaced by schema-safe object]); "
                "RetentionRate=mean(I[live call succeeded and no fallback/repair replaced final content])"
            ),
            "direction": "higher retention and lower repair are preferable; live-call rate alone is insufficient",
            "unit_of_analysis": "scenario row; aggregated by model and condition",
            "why_used": (
                "The engine can receive a successful live response and later replace an unrepairable scenario "
                "with a deterministic schema-safe object. Those events must not be reported as equivalent."
            ),
            "interpretation": (
                "A live call proves model execution. Retention shows that finalized content remained model-derived. "
                "Repair shows pipeline resilience but weakens pure model-generation attribution."
            ),
            "study_specific_part": "PSQ repair_note, llm_source, used_live_llm, and used_fallback lineage fields",
            "primary_or_secondary": "primary generation-integrity audit",
            "reference": (
                "Transparent preprocessing/postprocessing provenance and reproducibility principles; "
                "the PSQ status taxonomy is project-specific"
            ),
            "threshold_status": (
                "No universal content-quality threshold. Publication claims must report all three rates and "
                "must not call repaired rows retained live-model outputs."
            ),
            "reporting_rule": "Report numerator, denominator, and rate by model-condition; stratify quality results by repair status.",
            "limitation": "Retention does not prove that retained content is correct, realistic, or educationally effective.",
        },
        {
            "metric": "game_schema_complete_pass_rate",
            "display_name": "Game-schema completeness pass rate",
            "construct": "Presence of the fields needed to render and execute a PersonaShield Quest scenario",
            "classification": "study-defined checklist reported with a standard binary pass-rate form",
            "formula": "mean(I[all five core scenario fields, difficulty, and red-flag/safe-indicator content are present])",
            "direction": "higher is better",
            "unit_of_analysis": "scenario row; aggregated as a proportion",
            "why_used": "It separates deployable game structure from provenance metadata, which is unavailable by design in Prompt-Only Generation.",
            "interpretation": "1.00 means every finalized row contains the disclosed executable fields; it does not establish pedagogical quality.",
            "study_specific_part": "PSQ title, opening hook, channel, variant, correct action, difficulty, and indicator-content contract",
            "primary_or_secondary": "primary technical validity",
            "reference": "Arithmetic mean of a disclosed binary checklist; the field contract is project-specific",
            "threshold_status": "All disclosed game fields are required for a row-level pass.",
            "reporting_rule": "Report separately from provenance-field completeness.",
            "limitation": "Field presence does not show that field content is correct or usable.",
        },
        {
            "metric": "all_controls_exact_match_rate",
            "display_name": "Exact eight-control adherence rate",
            "construct": "Adherence to the frozen experimental specification",
            "classification": "standard exact-match accuracy form",
            "formula": "mean(I[all eight requested controls match])",
            "direction": "higher is better",
            "unit_of_analysis": "scenario row; all eight fields must match",
            "why_used": "The matched experiment requires role, age, stage, channel, variant, difficulty, attack type, and safe response to remain constant across methods.",
            "interpretation": "A row passes only when every requested control matches; one mismatch makes the row fail.",
            "study_specific_part": "Eight PSQ controls: role, age, stage, channel, variant, difficulty, attack type, safe response",
            "primary_or_secondary": "primary experimental adherence",
            "reference": "Exact-match/accuracy reporting; Sokolova and Lapalme (2009) for task-dependent classification measures",
            "threshold_status": "The exact-match rule is study-defined; no universal scenario-quality cutoff is inferred.",
            "reporting_rule": "Report alongside field-level failures so a near-ceiling rate does not hide which control drifted.",
            "limitation": "A pass can coexist with weak prose, pedagogy, or realism.",
        },
        {
            "metric": "common_case_concept_precision_recall_f1",
            "display_name": "Common case-concept precision, recall, and F1",
            "construct": "Closed-label concept adherence under one method-invariant oracle",
            "classification": "standard P/R/F1 formulas with project-specific oracle",
            "formula": "P=TP/(TP+FP); R=TP/(TP+FN); F1=2PR/(P+R)",
            "direction": "higher is better",
            "unit_of_analysis": "scenario row; summarized by method and paired frozen case",
            "why_used": "Precision separates unsupported detected labels from required labels, recall measures required-label coverage, and F1 balances both without treating prompt-only as a gold response.",
            "interpretation": "High F1 means the structured output contains the closed case labels; it does not score free-form semantic quality.",
            "study_specific_part": "One method-invariant case oracle and closed prediction-label vocabulary; no retrieval or ontology trace credit",
            "primary_or_secondary": "primary comparable concept-coverage diagnostic",
            "reference": "Sokolova and Lapalme (2009), Information Processing & Management",
            "threshold_status": "No universal acceptance cutoff; the oracle and label extractor are disclosed study operationalizations.",
            "reporting_rule": "Always report P, R, and F1 together and state that the oracle is automatic rather than human gold text.",
            "limitation": "The oracle is automatically constructed, not a human-authored gold scenario.",
        },
        {
            "metric": "contradiction_free_pass_rate",
            "display_name": "Contradiction-free rule pass rate",
            "construct": "Absence of pre-specified structural or defensive-safety contradictions",
            "classification": "standard binary pass-rate form",
            "formula": "mean(I[no pre-specified contradiction rule fires])",
            "direction": "higher is better",
            "unit_of_analysis": "scenario row; aggregated as a proportion",
            "why_used": "A high aggregate score must not conceal wrong attack/channel mappings, fake/real inconsistency, or unsafe defensive action.",
            "interpretation": "1.00 means none of the implemented rules fired; unimplemented harms or realism errors can still remain.",
            "study_specific_part": "PSQ wrong-attack, unsafe-action, fake/real consistency rules",
            "primary_or_secondary": "primary safety/control diagnostic",
            "reference": "Rule-based test pass rate; rules and denominators are disclosed",
            "threshold_status": "Rule thresholds are PSQ-specific and bounded by rule coverage.",
            "reporting_rule": "Report both the pass rate and contradiction count; route flagged rows to human review.",
            "limitation": "Rule coverage is bounded and is not equivalent to expert cybersecurity review.",
        },
        {
            "metric": "automated_technical_decision",
            "display_name": "Four-state automated technical-triage decision",
            "construct": "Non-compensatory disposition of machine-checkable defects",
            "classification": "project-defined deterministic validation gate",
            "formula": "ordered rules: parse/contradiction -> reject; missing executable fields, critical or multiple control failures, or >=2 missing case concepts -> major; one noncritical control or one missing case concept -> minor; otherwise accepted",
            "direction": "ACCEPTED is the least severe technical disposition",
            "unit_of_analysis": "scenario row",
            "why_used": "A complete state machine gives the revision loop a termination state without allowing strong unrelated metrics to cancel critical defects.",
            "interpretation": "ACCEPTED means all implemented automated technical gates passed; it is not final educational deployment approval.",
            "study_specific_part": "PSQ technical_gate_v1 rule ordering and critical-control list",
            "primary_or_secondary": "primary validation gate",
            "reference": "Transparent rule-based validation; final expert judgment follows human-evaluation guidance such as van der Lee et al. (2019)",
            "threshold_status": "Issue-count and critical-rule thresholds are disclosed project policy, not empirically calibrated universal constants.",
            "reporting_rule": "Report all four counts, reason codes, revision guidance, and the final-human-review-required flag.",
            "limitation": "Does not score PCUE pedagogy, realism, usability, or ethical nuance.",
        },
        {
            "metric": "full_nominal_treatment_exposure_rate",
            "display_name": "Full nominal condition-exposure rate",
            "construct": "Experimental fidelity: whether a row received the context components named by its assigned condition",
            "classification": "study-defined treatment-fidelity audit reported as a binary pass rate",
            "formula": (
                "C1: no external/ontology context; C2: >=1 external vector context; "
                "C3: >=1 external vector context and >=1 structured ontology source; "
                "C4: >=1 external vector context and >=1 ontology-text context; when a graph-walk variant is "
                "declared, >=1 selected-subgraph graph-walk context is additionally required"
            ),
            "direction": "higher means closer adherence to the nominal condition implementation",
            "unit_of_analysis": "scenario row; aggregated as a condition proportion",
            "why_used": "A nominal RAG assignment is not equivalent to actual retrieval exposure when retrieval returns no context.",
            "interpretation": "A failed exposure audit identifies treatment non-delivery, not necessarily a bad generated scenario.",
            "study_specific_part": "The four PSQ condition definitions and their required context components",
            "primary_or_secondary": "primary experimental-fidelity audit",
            "reference": "Treatment-fidelity and reproducibility principle; implementation contract is PSQ-specific",
            "threshold_status": "The row-level rule is exact and disclosed; it is not a universal scenario-quality threshold.",
            "reporting_rule": "Report numerator, denominator, and rate by condition before making causal condition comparisons.",
            "limitation": "Presence of context does not establish relevance, use, or faithfulness.",
        },
        {
            "metric": "graph_walk_exposure_rate",
            "display_name": "Verified selected-subgraph graph-walk exposure rate",
            "construct": "Delivery of the declared Condition-4 graph-walk document to the generation prompt",
            "classification": "study-defined treatment-component fidelity audit reported as a binary pass rate",
            "formula": "mean(I[selected_subgraph_walk context is exported for graph-walk-required rows])",
            "direction": "higher means more complete graph-walk treatment delivery",
            "unit_of_analysis": "Condition-4 scenario row requiring graph-walk treatment",
            "why_used": (
                "An implemented traversal algorithm has no causal role in an experiment unless its selected-subgraph "
                "text reaches the prompt for the evaluated row."
            ),
            "interpretation": (
                "1.00 means every graph-walk-required row received an identifiable selected-subgraph document; "
                "it does not show that the LLM used that context or that the selected path was optimal."
            ),
            "study_specific_part": (
                "PSQ selected_subgraph_walk document type and deterministic graph-to-text strategy metadata"
            ),
            "primary_or_secondary": "primary Condition-4 treatment-fidelity audit",
            "reference": (
                "Graph Chain-of-Thought (Jin et al., Findings of ACL 2024) motivates explicit graph reasoning; "
                "the deterministic PSQ walk and exposure indicator are project-specific"
            ),
            "threshold_status": "The declared graph-walk experiment requires one identifiable walk context per assigned row.",
            "reporting_rule": "Report required rows, exposed rows, and rate separately from external-RAG exposure.",
            "limitation": "Exposure is not graph-path quality, answer faithfulness, or a causal effect estimate.",
        },
        {
            "metric": "engine_validation_pass_rate",
            "display_name": "Generation-engine validation pass rate",
            "construct": "Pass rate under the generation engine's own post-generation quality rules",
            "classification": "project-defined rule-suite pass rate",
            "formula": "mean(I[raw generation record validation_passed=true]) over evaluated rows",
            "direction": "higher means fewer engine quality flags",
            "unit_of_analysis": "scenario row; aggregated by model and condition",
            "why_used": "It preserves the engine's original rule result instead of replacing it with the later independent evaluator decision.",
            "interpretation": "Failure means at least one generation-engine rule fired; inspect validation_issues for the reason.",
            "study_specific_part": "PSQ generation validator and quality_flags",
            "primary_or_secondary": "secondary pipeline audit",
            "reference": "Transparent rule-suite pass-rate reporting; the rule content and thresholds are PSQ-specific",
            "threshold_status": "A row passes only when the generation record explicitly stores validation_passed=true.",
            "reporting_rule": "Keep separate from JSON/schema validity and the independent technical_gate_v1 decision.",
            "limitation": "The rule suite is not an external human gold standard and can contain duplicate or correlated checks.",
        },
        {
            "metric": "source_linkage_and_similarity_estimability",
            "display_name": "Scenario-to-context linkage and source-similarity estimability audit",
            "construct": "Whether a generated scenario can be traced to its ordered retrieved context set and whether a defensible source-relevance/faithfulness score can be calculated",
            "classification": "provenance audit; no similarity value is fabricated when required evidence is absent",
            "formula": "counts exported context/source IDs, retrieval scores, retrieval query, and claim-source mappings; status is NOT_ESTIMABLE when query-score or claim-support evidence is missing",
            "direction": "coverage/status measure; not a quality ranking",
            "unit_of_analysis": "scenario row and its ordered context set",
            "why_used": "RAG evaluation must distinguish retrieval relevance from generation faithfulness and cannot compare every scenario with one unrelated combined source.",
            "interpretation": "A source ID establishes provenance linkage only. It does not prove that the source supports a generated claim.",
            "study_specific_part": "PSQ frozen-export fields and source-linkage status taxonomy",
            "primary_or_secondary": "secondary mechanism audit",
            "reference": "KILT (Petroni et al., 2021), RAGAS (Es et al., 2024), ARES (Saad-Falcon et al., 2024), and RAGChecker (Ru et al., 2024)",
            "threshold_status": "No numeric threshold is used in the current frozen run; unestimable similarity is reported explicitly.",
            "reporting_rule": "Map one scenario to its own ordered context set and separate retrieval relevance, claim faithfulness, and corpus diversity.",
            "limitation": "Historical exports do not contain complete query/rank/distance or claim-level entailment annotations.",
        },
        {
            "metric": "self_bleu",
            "display_name": "Self-BLEU lexical redundancy",
            "construct": "Within-condition lexical repetition",
            "classification": "established text-generation diversity metric",
            "formula": "mean BLEU(sample_i, all other samples as references)",
            "direction": "lower indicates less lexical redundancy",
            "unit_of_analysis": "120-scenario model-by-method collection",
            "why_used": "It detects repeated surface wording and template-like mode collapse across a generated collection.",
            "interpretation": "Lower values mean scenarios share fewer n-gram patterns; they do not imply factual, pedagogical, or ethical quality.",
            "study_specific_part": "Computed within each 120-scenario model-by-method condition",
            "primary_or_secondary": "secondary lexical redundancy diagnostic",
            "reference": "Zhu et al. (2018), Texygen, SIGIR",
            "threshold_status": "Relative within-study comparison only; no universal good/bad cutoff.",
            "reporting_rule": "Report the text field composition, tokenizer/BLEU implementation, collection size, and direction.",
            "limitation": "Lower indicates less lexical repetition, not higher scenario quality; no universal cutoff is used.",
        },
        {
            "metric": "embedding_cosine_diversity",
            "display_name": "Sentence-embedding cosine dispersion",
            "construct": "Within-condition semantic dispersion",
            "classification": "literature-grounded semantic-diversity diagnostic",
            "formula": "1 - mean cosine similarity over unordered embedding pairs",
            "direction": "higher indicates greater relative semantic dispersion",
            "unit_of_analysis": "120-scenario model-by-method collection",
            "why_used": "Embedding space can detect meaning-level similarity that surface n-gram overlap may miss.",
            "interpretation": "Higher values mean the player-facing texts are farther apart under the exact frozen embedding representation named in run metadata.",
            "study_specific_part": "Configured Sentence-Transformers embeddings of player-facing scenario text within each condition",
            "primary_or_secondary": "secondary semantic diversity diagnostic",
            "reference": "Reimers and Gurevych (2019), SBERT; Feng et al. (2022), LaBSE; Tevet and Berant (2021), EACL",
            "threshold_status": "Relative within-study comparison only; no universal good/bad cutoff.",
            "reporting_rule": "Record the embedding model/version and report with Self-BLEU and human inspection rather than alone.",
            "limitation": "Relative within-study comparison only; no universal good/bad threshold is claimed.",
        },
        {
            "metric": "trace_completeness",
            "display_name": "Provenance-field completeness",
            "construct": "Presence of declared source and retrieval audit fields",
            "classification": "project-defined provenance diagnostic",
            "formula": "fraction of six declared trace/provenance fields present",
            "direction": "higher means more declared audit fields are present",
            "unit_of_analysis": "scenario row; six-field project checklist",
            "why_used": "The ontology/RAG engineering claim requires auditable source identifiers, evidence roles, and retrieval metadata.",
            "interpretation": "A complete trace shows where the pipeline says context came from; it does not prove that the generated claim is entailed by that source.",
            "study_specific_part": "PSQ source ID/title, evidence role, provenance, retrieval mode, record ID",
            "primary_or_secondary": "secondary mechanism audit",
            "reference": "Project-defined provenance checklist; no external metric standard is claimed",
            "threshold_status": "PSQ checklist, not a standard quality scale; prompt-only is incomplete by design.",
            "reporting_rule": "Never rank content quality from this metric; disclose method-conditioned availability.",
            "limitation": "Trace presence does not prove that generated claims are entailed by the source.",
        },
        {
            "metric": "ontology_semantic_scope",
            "display_name": "Ontology-trace/control conformance diagnostic",
            "construct": "Preservation of selected ontology controls in an ABox-like scenario record",
            "classification": "project-defined ontology diagnostic",
            "formula": "disclosed rule-weighted structural scope score",
            "direction": "higher means more implemented ontology-scope checks pass",
            "unit_of_analysis": "scenario row; PSQ structural rule set",
            "why_used": "It audits whether generated instances stay inside the selected channel, attack, cue, response, and evidence envelope.",
            "interpretation": "A high score is structural scope coverage under implemented rules, not logical entailment or learned ontology-embedding accuracy.",
            "study_specific_part": "PSQ packet/text traces, controls, and non-contradiction",
            "primary_or_secondary": "secondary mechanism audit",
            "reference": "Project rule audit informed by OWL TBox/ABox separation and KG-to-text faithfulness literature; not an ontology-embedding implementation",
            "threshold_status": "Project-defined; no external benchmark calibrates its scale.",
            "reporting_rule": "Publish the component rules and keep this separate from human-rated pedagogy and realism.",
            "limitation": "Must not be described as a standard metric or external gold-standard accuracy.",
        },
        {
            "metric": "legacy_overall_conformance",
            "display_name": "PSQ mechanism-aware conformance index",
            "construct": "Compact summary of technical, case, concept, trace, and contradiction diagnostics",
            "classification": "project-defined linear composite diagnostic",
            "formula": "0.20 JSON + 0.25 control + 0.25 legacy F1 + 0.20 trace completeness + 0.10 non-contradiction",
            "direction": "higher means stronger performance on this exact component mix",
            "unit_of_analysis": "scenario row, then arithmetic mean by method",
            "why_used": "It restores the original dashboard-style summary for pipeline monitoring while component metrics remain visible.",
            "interpretation": "The score is a PSQ mechanism index, not a validated percentage of overall scenario quality.",
            "study_specific_part": "Fixed PSQ coefficients and legacy method-conditioned concept diagnostic",
            "primary_or_secondary": "secondary sensitivity/backward-compatibility only",
            "reference": "OECD/JRC (2008) for transparent composite-indicator construction and sensitivity analysis; no external study establishes these exact PSQ coefficients",
            "threshold_status": "Coefficients are uncalibrated design-priority weights; no universal acceptance threshold.",
            "reporting_rule": "Report all five components, the exact formula, sensitivity status, and the method-invariant standard profile beside the index.",
            "limitation": "Not suitable as the sole ranking outcome; legacy F1 and trace credit are method-conditioned and can favor ontology-enabled pipelines.",
        },
    ]

    operational = {
        "json_parse_pass_rate": {
            "formal_input": "one finalized JSONL row",
            "formal_output": "row indicator in {0,1}; method output is numerator/denominator and mean pass rate",
            "threshold": "row passes only when parsing succeeds and an inspectable scenario object exists",
            "workflow_layer": "Layer 2, before all content checks",
            "calculation_time": "after generation and recovery merge, during each evaluation run",
            "frequency": "once per scenario row; aggregated once per model-condition and condition",
            "metric_role": "validation gate",
        },
        "generation_integrity_rates": {
            "formal_input": "used_live_llm, used_fallback, scenario.llm_source, and generation_meta.repair_note",
            "formal_output": "three row indicators and aggregated live-call, repair, and model-content-retention rates",
            "threshold": "no universal quality cutoff; pure live-model attribution requires retained live content",
            "workflow_layer": "input-lineage audit before scenario-quality interpretation",
            "calculation_time": "while each finalized generation record is loaded",
            "frequency": "once per scenario row; summarized per model-condition and condition",
            "metric_role": "audit measure and attribution safeguard",
        },
        "game_schema_complete_pass_rate": {
            "formal_input": "parsed scenario fields",
            "formal_output": "field fraction plus all-fields-present indicator in {0,1}",
            "threshold": "all seven disclosed field checks must pass",
            "workflow_layer": "Layer 2, immediately after JSON parsing",
            "calculation_time": "during each evaluation run",
            "frequency": "once per scenario row",
            "metric_role": "validation gate",
        },
        "all_controls_exact_match_rate": {
            "formal_input": "frozen case specification and parsed scenario metadata",
            "formal_output": "eight field indicators, their mean, and an all-eight indicator in {0,1}",
            "threshold": "all eight requested controls must match for exact-match pass",
            "workflow_layer": "Layer 2 case-conformance checks",
            "calculation_time": "during each evaluation run",
            "frequency": "once per scenario row",
            "metric_role": "validation gate and comparative audit",
        },
        "common_case_concept_precision_recall_f1": {
            "formal_input": "method-invariant case oracle and closed labels extracted from player-facing scenario fields",
            "formal_output": "P, R, and harmonic-mean F1 in [0,1] plus matched/missing labels",
            "threshold": "no universal research threshold; missing-label counts feed the disclosed technical decision rule",
            "workflow_layer": "Layer 2 case-concept audit; Layer 3 paired comparison",
            "calculation_time": "during each evaluation run",
            "frequency": "once per scenario row; summarized and paired by frozen case",
            "metric_role": "comparative evaluation metric with decision-rule input",
        },
        "contradiction_free_pass_rate": {
            "formal_input": "parsed scenario, frozen channel/variant case, and bounded defensive-safety rules",
            "formal_output": "contradiction reasons and pass indicator in {0,1}",
            "threshold": "zero fired contradiction rules",
            "workflow_layer": "Layer 2 non-compensatory safety/consistency checks",
            "calculation_time": "during each evaluation run",
            "frequency": "once per scenario row",
            "metric_role": "validation gate",
        },
        "automated_technical_decision": {
            "formal_input": "parse, game-schema, control, common-concept, and contradiction defects",
            "formal_output": "ACCEPTED, MINOR_REVISION, MAJOR_REVISION, or REJECT_REGENERATE with reason codes",
            "threshold": "the complete ordered technical_gate_v1 rule stated in the formula",
            "workflow_layer": "end of Layer 2 before PCUE and human review",
            "calculation_time": "after all row-level technical checks",
            "frequency": "once per scenario row in each evaluation run",
            "metric_role": "validation gate",
        },
        "source_linkage_and_similarity_estimability": {
            "formal_input": "scenario-specific retrieved contexts and exported source/query/score/claim-map metadata",
            "formal_output": "coverage counts and categorical estimability status; no synthetic similarity score",
            "threshold": "not applicable; missing evidence yields NOT_ESTIMABLE_FROM_FROZEN_EXPORT",
            "workflow_layer": "Layer 2 RAG provenance audit",
            "calculation_time": "after loading frozen generation records",
            "frequency": "once per scenario row; summarized per condition",
            "metric_role": "audit measure",
        },
        "full_nominal_treatment_exposure_rate": {
            "formal_input": "assigned condition and scenario-specific external, structured-ontology, and ontology-text context counts",
            "formal_output": "row indicator in {0,1}; condition-level numerator, denominator, and mean pass rate",
            "threshold": "the exact condition-specific context contract stated in the formula",
            "workflow_layer": "Layer 2 experimental-fidelity audit before outcome comparison",
            "calculation_time": "after loading frozen generation records",
            "frequency": "once per scenario row; summarized per condition",
            "metric_role": "audit measure and causal-interpretation safeguard",
        },
        "graph_walk_exposure_rate": {
            "formal_input": "Condition-4 prompt contexts, document types, source IDs, and graph-text strategy metadata",
            "formal_output": "required-row indicator, verified-exposure indicator, numerator, denominator, and rate",
            "threshold": "one selected_subgraph_walk context for every graph-walk-required row",
            "workflow_layer": "Layer 2 treatment-fidelity audit before method comparison",
            "calculation_time": "after loading scenario-specific prompt-context records",
            "frequency": "once per scenario row; summarized for graph-walk-required Condition-4 rows",
            "metric_role": "audit measure and causal-interpretation safeguard",
        },
        "engine_validation_pass_rate": {
            "formal_input": "raw generation record validation_passed and validation_issues",
            "formal_output": "row value in {0,1} when evaluated plus condition-level evaluated/pass rates",
            "threshold": "validation_passed must be true for a row-level pass",
            "workflow_layer": "generation-engine audit imported before independent Layer-2 checks",
            "calculation_time": "during generation, then summarized during evaluation",
            "frequency": "once per scenario row",
            "metric_role": "secondary audit measure",
        },
        "self_bleu": {
            "formal_input": "120 player-facing scenario texts in one model-condition collection",
            "formal_output": "mean corpus-internal BLEU redundancy score in [0,1]",
            "threshold": "none; lower is interpreted only relative to matched conditions",
            "workflow_layer": "Layer 3 collection-level diversity analysis",
            "calculation_time": "after all 120 rows for a model-condition are available",
            "frequency": "once for each of 12 model-condition collections, then summarized by condition",
            "metric_role": "comparative evaluation metric",
        },
        "embedding_cosine_diversity": {
            "formal_input": "embeddings from the run-declared Sentence-Transformers model for 120 player-facing scenario texts in one model-condition collection",
            "formal_output": "1 minus mean unordered-pair cosine similarity",
            "threshold": "none; higher is interpreted only relative to matched conditions",
            "workflow_layer": "Layer 3 collection-level diversity analysis",
            "calculation_time": "after all 120 rows for a model-condition are available",
            "frequency": "once for each of 12 model-condition collections, then summarized by condition",
            "metric_role": "comparative evaluation metric",
        },
        "trace_completeness": {
            "formal_input": "six declared provenance fields in each finalized row",
            "formal_output": "present-field fraction in [0,1] and complete indicator",
            "threshold": "all six fields for a trace-complete audit row",
            "workflow_layer": "Layer 2 mechanism/provenance audit",
            "calculation_time": "during each evaluation run",
            "frequency": "once per scenario row",
            "metric_role": "audit measure",
        },
        "ontology_semantic_scope": {
            "formal_input": "ontology trace, frozen controls, and bounded non-contradiction checks",
            "formal_output": "project rule-coverage score in [0,1]",
            "threshold": "none for acceptance; components are published separately",
            "workflow_layer": "Layer 2 ontology mechanism audit",
            "calculation_time": "during each evaluation run",
            "frequency": "once per scenario row",
            "metric_role": "audit measure",
        },
        "legacy_overall_conformance": {
            "formal_input": "five normalized project diagnostics",
            "formal_output": "uncalibrated linear composite in [0,1]",
            "threshold": "none in the revised decision pipeline",
            "workflow_layer": "legacy Layer 2 dashboard compatibility",
            "calculation_time": "during each evaluation run",
            "frequency": "once per scenario row; summarized by condition",
            "metric_role": "secondary sensitivity measure, never a validation gate",
        },
    }
    for row in rows:
        row.update(operational[row["metric"]])
    return rows


def standard_metric_summary(
    scores: Sequence[ScenarioScore],
    diversity_summary_rows: Sequence[Dict[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Summarize the primary comparable metrics by generation method."""

    grouped: Dict[str, List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        grouped[score.method].append(score)
    diversity_by_method = {str(row.get("method")): row for row in diversity_summary_rows}

    rows: List[Dict[str, Any]] = []
    for method in METHOD_ORDER:
        group = grouped.get(method, [])
        if not group:
            continue
        diversity = diversity_by_method.get(method, {})
        rows.append(
            {
                "method": method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
                "condition_name": METHOD_LABELS.get(method, method),
                "n": len(group),
                "live_llm_rate": _mean([1 if score.used_live_llm else 0 for score in group]),
                "schema_safe_repair_rate": _mean(
                    [1 if score.schema_safe_repair_used else 0 for score in group]
                ),
                "live_model_content_retention_rate": _mean(
                    [1 if score.live_model_content_retained else 0 for score in group]
                ),
                "engine_validation_evaluated_rate": _mean(
                    [1 if score.engine_validation_passed is not None else 0 for score in group]
                ),
                "engine_validation_pass_rate": _mean(
                    [
                        1 if score.engine_validation_passed else 0
                        for score in group
                        if score.engine_validation_passed is not None
                    ]
                ),
                "json_parse_pass_rate": _mean([score.json_parse_pass for score in group]),
                "game_schema_complete_pass_rate": _mean(
                    [score.game_schema_complete_pass for score in group]
                ),
                "all_controls_exact_match_rate": _mean([score.all_controls_exact_match for score in group]),
                "common_case_concept_precision": _mean(
                    [score.common_case_concept_precision for score in group]
                ),
                "common_case_concept_recall": _mean([score.common_case_concept_recall for score in group]),
                "common_case_concept_f1": _mean([score.common_case_concept_f1 for score in group]),
                "contradiction_free_pass_rate": _mean([score.contradiction_free_pass for score in group]),
                "accepted_technical_rate": _mean(
                    [1 if score.automated_decision == "ACCEPTED" else 0 for score in group]
                ),
                "minor_revision_technical_rate": _mean(
                    [1 if score.automated_decision == "MINOR_REVISION" else 0 for score in group]
                ),
                "major_revision_technical_rate": _mean(
                    [1 if score.automated_decision == "MAJOR_REVISION" else 0 for score in group]
                ),
                "reject_regenerate_technical_rate": _mean(
                    [1 if score.automated_decision == "REJECT_REGENERATE" else 0 for score in group]
                ),
                "embedding_diversity": diversity.get("embedding_diversity_mean"),
                "embedding_backend": diversity.get("embedding_backend"),
                "embedding_model": diversity.get("embedding_model"),
                "self_bleu": diversity.get("self_bleu_mean"),
                "diversity_interpretation": "relative comparison only; no universal acceptance cutoff",
                "schema_provenance_complete_rate_secondary": _mean(
                    [score.schema_complete_pass for score in group]
                ),
                "legacy_overall_conformance_secondary": _mean([score.overall_conformance for score in group]),
            }
        )
    return rows


def standard_error_analysis(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Return method-comparable failures without legacy trace/concept confounding."""

    grouped: Dict[str, List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        grouped[score.method].append(score)
    definitions = (
        (
            "schema_safe_repair_used",
            lambda score: score.schema_safe_repair_used,
            "A successful live call was followed by replacement with the deterministic schema-safe scenario object; this is an attribution/integrity flag, not necessarily a content defect.",
        ),
        (
            "generation_engine_validation_failed",
            lambda score: score.engine_validation_passed is False,
            "At least one generation-engine quality rule fired; inspect engine_validation_issues separately from the independent technical decision.",
        ),
        (
            "invalid_json_or_missing_scenario",
            lambda score: score.json_parse_pass == 0,
            "Binary parse/scenario-object failure.",
        ),
        (
            "any_requested_control_failure",
            lambda score: score.all_controls_exact_match == 0,
            "At least one of the eight frozen case controls failed exact matching.",
        ),
        (
            "game_schema_incomplete",
            lambda score: score.game_schema_complete_pass == 0,
            "At least one disclosed game-executable field is missing.",
        ),
        (
            "common_case_concept_not_perfect_recall",
            lambda score: score.common_case_concept_recall < 1.0,
            "At least one label in the method-invariant case oracle was not recovered.",
        ),
        (
            "contradiction",
            lambda score: score.contradiction_free_pass == 0,
            "At least one disclosed contradiction/safety rule fired.",
        ),
        (
            "trace_incomplete_secondary",
            lambda score: score.trace_complete_pass == 0,
            "Project mechanism audit only; prompt-only has no retrieval trace by design.",
        ),
        (
            "not_automatically_accepted",
            lambda score: score.automated_decision != "ACCEPTED",
            "The technical_gate_v1 decision is Minor Revision, Major Revision, or Reject/Regenerate; human approval is still required for every row.",
        ),
    )
    rows: List[Dict[str, Any]] = []
    for error_type, predicate, interpretation in definitions:
        row: Dict[str, Any] = {"error_type": error_type}
        for method in METHOD_ORDER:
            row[method] = sum(1 for score in grouped.get(method, []) if predicate(score))
        row["interpretation"] = interpretation
        rows.append(row)
    return rows


def _mean(values: Sequence[float | int]) -> float | None:
    return mean(float(value) for value in values) if values else None
