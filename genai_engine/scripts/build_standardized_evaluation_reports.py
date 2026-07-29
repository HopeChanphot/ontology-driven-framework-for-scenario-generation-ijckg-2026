"""Build reviewer-facing reports and slide figures from a completed evaluation.

This script does not recompute embeddings. It reads the frozen evaluation
exports, verifies the expected study shape, derives a method-comparable error
table, and writes publication-facing reports with explicit validity limits.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from three_layer_evaluation.standard_metrics import metric_validity_registry


METHODS = ("prompt_only", "prompt_rag", "ontology_prompt_rag", "ontology_text_rag")
METHOD_LABELS = {
    "prompt_only": "Prompt only",
    "prompt_rag": "Prompt + external RAG",
    "ontology_prompt_rag": "Ontology packet + prompt + RAG",
    "ontology_text_rag": "Ontology text + prompt + RAG",
}
METHOD_COLORS = {
    "prompt_only": "#4C78A8",
    "prompt_rag": "#F2B134",
    "ontology_prompt_rag": "#2A9D8F",
    "ontology_text_rag": "#D95F59",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--generation-dir", type=Path, required=True)
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Write reports without matplotlib-based figures.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers: List[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def pct(value: Any, digits: int = 2) -> str:
    return f"{100 * number(value):.{digits}f}%"


def dec(value: Any, digits: int = 4) -> str:
    return f"{number(value):.{digits}f}"


def md_table(rows: Sequence[Dict[str, Any]], columns: Sequence[str] | None = None) -> str:
    if not rows:
        return "No rows available."
    headers = list(columns or rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        values = [str(row.get(header, "")).replace("|", "\\|").replace("\n", " ") for header in headers]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def standard_error_rows(score_rows: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in score_rows:
        grouped[row["method"]].append(row)
    definitions = (
        ("invalid_json_or_missing_scenario", lambda row: number(row.get("json_parse_pass")) == 0,
         "Binary parse/scenario-object failure."),
        ("any_requested_control_failure", lambda row: number(row.get("all_controls_exact_match")) == 0,
         "At least one of the eight frozen case controls failed exact matching."),
        ("common_case_concept_not_perfect_recall", lambda row: number(row.get("common_case_concept_recall")) < 1,
         "At least one label in the method-invariant case oracle was not recovered."),
        ("contradiction", lambda row: number(row.get("contradiction_free_pass")) == 0,
         "At least one disclosed contradiction/safety rule fired."),
        ("trace_incomplete_secondary", lambda row: number(row.get("trace_complete_pass")) == 0,
         "Mechanism audit only; prompt-only has no retrieval trace by design."),
    )
    output: List[Dict[str, Any]] = []
    for name, predicate, interpretation in definitions:
        result: Dict[str, Any] = {"error_type": name}
        for method in METHODS:
            result[method] = sum(1 for row in grouped[method] if predicate(row))
        result["interpretation"] = interpretation
        output.append(result)
    return output


def verify_study(score_rows: Sequence[Dict[str, str]], condition_rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    keys = {(row["model_key"], row["method"], row["case_id"]) for row in score_rows}
    cases = {row["case_id"] for row in score_rows}
    models = {row["model_key"] for row in score_rows}
    methods = {row["method"] for row in score_rows}
    live = sum(row.get("used_live_llm", "").lower() == "true" for row in score_rows)
    fallback = sum(row.get("used_fallback", "").lower() == "true" for row in score_rows)
    complete_conditions = sum(
        int(row.get("row_count") or 0) == 120
        and int(row.get("unique_case_count") or 0) == 120
        and row.get("used_live_llm_rows") == "120"
        and row.get("fallback_rows") == "0"
        for row in condition_rows
    )
    result = {
        "rows": len(score_rows),
        "unique_keys": len(keys),
        "cases": len(cases),
        "models": len(models),
        "methods": len(methods),
        "live_rows": live,
        "fallback_rows": fallback,
        "complete_conditions": complete_conditions,
    }
    expected = {
        "rows": 1440,
        "unique_keys": 1440,
        "cases": 120,
        "models": 3,
        "methods": 4,
        "live_rows": 1440,
        "fallback_rows": 0,
        "complete_conditions": 12,
    }
    if result != expected:
        raise RuntimeError(f"Study integrity check failed: observed={result}, expected={expected}")
    return result


def source_composition(dataset: Dict[str, Any], field: str) -> List[Dict[str, Any]]:
    totals: Dict[str, int] = defaultdict(int)
    for row in dataset.get("sources", []):
        totals[str(row.get(field, "unknown"))] += int(row.get("used_document_count") or 0)
    denominator = int(dataset.get("used_document_count_after_caps") or sum(totals.values()))
    return [
        {field: key, "documents": value, "percentage": f"{100 * value / denominator:.2f}%"}
        for key, value in sorted(totals.items())
    ]


def context_audit(generation_dir: Path) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[tuple[int, int]]] = defaultdict(list)
    for path in sorted(generation_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = json.loads(line)
                scenario = raw.get("scenario") or {}
                meta = scenario.get("generation_meta") or {}
                mode = raw.get("mode") or meta.get("mode") or "prompt_only"
                if mode in {"prompt_only_default_template", "default_template"}:
                    mode = "prompt_only"
                rag_examples = raw.get("rag_examples")
                top_count = len(rag_examples) if isinstance(rag_examples, list) else 0
                ontology_text_count = int((raw.get("prompt_metadata") or {}).get("ontology_text_document_count") or 0)
                external_count = max(0, top_count - ontology_text_count) if mode == "ontology_text_rag" else top_count
                grouped[mode].append((external_count, ontology_text_count))
    rows: List[Dict[str, Any]] = []
    for method in METHODS:
        values = grouped[method]
        external = [item[0] for item in values]
        ontology_text = [item[1] for item in values]
        rows.append(
            {
                "method": METHOD_LABELS[method],
                "n": len(values),
                "external_RAG_present": sum(value > 0 for value in external),
                "external_RAG_absent": sum(value == 0 for value in external),
                "external_RAG_mean_items": f"{sum(external) / len(external):.3f}" if external else "",
                "ontology_text_docs_per_row": (
                    f"{min(ontology_text)}-{max(ontology_text)}" if ontology_text and max(ontology_text) else "0"
                ),
            }
        )
    return rows


def matched_example(generation_dir: Path, case_id: str = "PSQ-SCO-120-001", model: str = "qwen2_5_7b") -> List[Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for path in sorted(generation_dir.glob(f"{model}__*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = json.loads(line)
                if (raw.get("case") or {}).get("case_id") != case_id:
                    continue
                scenario = raw.get("scenario") or {}
                prompt_meta = raw.get("prompt_metadata") or {}
                mode = raw.get("mode") or (scenario.get("generation_meta") or {}).get("mode") or "prompt_only"
                if mode == "prompt_only_default_template":
                    mode = "prompt_only"
                rows[mode] = {
                    "method": METHOD_LABELS.get(mode, mode),
                    "title": scenario.get("title", ""),
                    "opening_hook": scenario.get("opening_hook", ""),
                    "correct_action": scenario.get("correct_action", ""),
                    "ontology_packet": bool(prompt_meta.get("ontology_packet_used")),
                    "ontology_text_docs": int(prompt_meta.get("ontology_text_document_count") or 0),
                }
                break
    return [rows[method] for method in METHODS if method in rows]


def primary_results_table(standard_rows: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in standard_rows:
        output.append(
            {
                "Method": METHOD_LABELS[row["method"]],
                "N": row["n"],
                "Live": pct(row["live_llm_rate"]),
                "PSQ index (secondary)": dec(row["legacy_overall_conformance_secondary"]),
                "JSON pass": pct(row["json_parse_pass_rate"]),
                "All controls exact": pct(row["all_controls_exact_match_rate"]),
                "Common P": dec(row["common_case_concept_precision"]),
                "Common R": dec(row["common_case_concept_recall"]),
                "Common F1": dec(row["common_case_concept_f1"]),
                "Contradiction-free": pct(row["contradiction_free_pass_rate"]),
                "LaBSE diversity": dec(row["embedding_diversity"]),
                "Self-BLEU": dec(row["self_bleu"]),
            }
        )
    return output


def paired_table(stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for comparison in stats["primary_case_clustered_analysis"]["comparisons"]:
        test = comparison.get("wilcoxon_signed_rank") or {}
        ci = comparison.get("bootstrap_ci95") or [None, None]
        rows.append(
            {
                "Comparison (right - left)": f"{METHOD_LABELS[comparison['right']]} - {METHOD_LABELS[comparison['left']]}",
                "N cases": comparison["paired_n"],
                "Non-zero": comparison["nonzero_difference_n"],
                "Mean delta F1": f"{number(comparison['mean_difference_right_minus_left']):+.6f}",
                "95% case bootstrap CI": f"[{number(ci[0]):+.6f}, {number(ci[1]):+.6f}]",
                "Wilcoxon p": dec(test.get("p_value"), 4),
                "Holm p": dec(test.get("holm_adjusted_p_value"), 4),
                "Rank-biserial": dec(comparison.get("matched_rank_biserial"), 3),
                "Ties": comparison["tie_n"],
            }
        )
    return rows


def model_method_table(rows: Sequence[Dict[str, str]], diversity_rows: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    diversity = {(row["model_key"], row["method"]): row for row in diversity_rows}
    output: List[Dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (item["model_key"], METHODS.index(item["method"]))):
        div = diversity[(row["model_key"], row["method"])]
        output.append(
            {
                "Model": row["model_key"],
                "Method": METHOD_LABELS[row["method"]],
                "Common F1": dec(row["common_case_concept_f1_mean"]),
                "All controls": pct(row["all_controls_exact_match_rate"]),
                "Contradiction-free": pct(row["contradiction_free_pass_rate"]),
                "LaBSE diversity": dec(div["embedding_diversity"]),
                "Self-BLEU": dec(div["self_bleu"]),
                "Legacy index (secondary)": dec(row["overall_conformance_mean"]),
            }
        )
    return output


def references() -> str:
    return """1. Sokolova, M., and Lapalme, G. (2009). A systematic analysis of performance measures for classification tasks. *Information Processing & Management*, 45(4), 427-437. [DOI](https://doi.org/10.1016/j.ipm.2009.03.002)
2. Tevet, G., and Berant, J. (2021). Evaluating the Evaluation of Diversity in Natural Language Generation. *EACL 2021*. [ACL Anthology](https://aclanthology.org/2021.eacl-main.25/)
3. Zhu, Y., et al. (2018). Texygen: A Benchmarking Platform for Text Generation Models. *SIGIR 2018*. [UCL record](https://discovery.ucl.ac.uk/10066104/)
4. Feng, F., et al. (2022). Language-agnostic BERT Sentence Embedding. *ACL 2022*. [ACL Anthology](https://aclanthology.org/2022.acl-long.62/)
5. Wilcoxon, F. (1945). Individual Comparisons by Ranking Methods. *Biometrics Bulletin*, 1(6), 80-83. [DOI](https://doi.org/10.2307/3001968)
6. Friedman, M. (1937). The Use of Ranks to Avoid the Assumption of Normality Implicit in the Analysis of Variance. *JASA*, 32(200), 675-701. [DOI](https://doi.org/10.1080/01621459.1937.10503522)
7. Holm, S. (1979). A Simple Sequentially Rejective Multiple Test Procedure. *Scandinavian Journal of Statistics*, 6(2), 65-70. [JSTOR](https://www.jstor.org/stable/4615733)
8. Efron, B. (1979). Bootstrap Methods: Another Look at the Jackknife. *The Annals of Statistics*, 7(1), 1-26. [DOI](https://doi.org/10.1214/aos/1176344552)
9. Cameron, A. C., Gelbach, J. B., and Miller, D. L. (2011). Robust Inference With Multiway Clustering. *Journal of Business & Economic Statistics*, 29(2), 238-249. [DOI](https://doi.org/10.1198/jbes.2010.07136)
10. Deen, M., et al. (2020). ClusterBootstrap for hierarchical and repeated-measures data. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7148287/)
11. Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*. [Proceedings](https://proceedings.neurips.cc/paper/2020/hash/6b493230-Abstract.html)
12. Glimm, B., et al. (2014). HermiT: An OWL 2 Reasoner. *Journal of Automated Reasoning*, 53(3), 245-269. [Oxford record](https://ora.ox.ac.uk/objects/uuid%3Ae719ebc8-ff8b-4efa-a14f-7da8478ff0ed)
13. Hashemi, H., et al. (2024). LLM-Rubric: A Multidimensional, Calibrated Approach to Automated Evaluation of Natural Language Texts. *ACL 2024*. [ACL Anthology](https://aclanthology.org/2024.acl-long.745/)
14. Khashabi, D., et al. (2022). GENIE: Toward Reproducible and Standardized Human Evaluation for Text Generation. *EMNLP 2022*. [ACL Anthology](https://aclanthology.org/2022.emnlp-main.787/)
15. van der Lee, C., et al. (2019). Best Practices for the Human Evaluation of Automatically Generated Text. *INLG 2019*. [ACL Anthology](https://aclanthology.org/W19-8643/)
16. Krippendorff, K. (2004). Reliability in Content Analysis. *Human Communication Research*, 30(3), 411-433. [DOI](https://doi.org/10.1111/j.1468-2958.2004.tb00738.x)
17. W3C (2012). OWL 2 Web Ontology Language Document Overview. [Recommendation](https://www.w3.org/TR/owl2-overview/)
18. W3C (2013). SPARQL 1.1 Query Language. [Recommendation](https://www.w3.org/TR/sparql11-query/)
19. OECD/European Union/EC-JRC (2008). *Handbook on Constructing Composite Indicators: Methodology and User Guide*. OECD Publishing. [DOI](https://doi.org/10.1787/9789264043466-en)

**Venue-rank caution.** Journal quartiles vary by database, subject category, and year, and conference proceedings do not have journal quartiles. Verify any Q1/Q2/Q3 label in the exact Scopus/SJR or Journal Citation Reports edition used by the thesis; do not invent a quartile label for ACL, EMNLP, EACL, NeurIPS, or SIGIR proceedings."""


def build_evaluation_report(
    *,
    evaluation_dir: Path,
    generation_dir: Path,
    integrity: Dict[str, Any],
    ontology: Dict[str, Any],
    dataset: Dict[str, Any],
    primary_rows: Sequence[Dict[str, Any]],
    error_rows: Sequence[Dict[str, Any]],
    paired_rows: Sequence[Dict[str, Any]],
    stats: Dict[str, Any],
    context_rows: Sequence[Dict[str, Any]],
    validity_rows: Sequence[Dict[str, str]],
    timing_rows: Sequence[Dict[str, str]],
) -> str:
    friedman = stats["primary_case_clustered_analysis"]["friedman"]
    channel_rows = source_composition(dataset, "channel_folder")
    language_rows = source_composition(dataset, "language")
    return f"""# Final Standardized Evaluation Report: PersonaShield Quest Scenario Generation

## Status and Scope

This is the authoritative report for the recovered live-generation study at `{evaluation_dir}`. It evaluates finalized game-scenario records, not learner performance. The input bundle is `{generation_dir}`.

The automatic evidence supports statements about parseability, requested-control adherence, closed-label concept adherence, rule-detected contradictions, provenance-trace presence, ontology validation, corpus diversity, and recorded timing. It does **not** establish pedagogical effectiveness, cybersecurity realism as judged by experts, classroom usability, or learning gain.

## Reproducibility Integrity

| Check | Verified result |
|---|---:|
| Total evaluated rows | {integrity['rows']} |
| Unique model-method-case keys | {integrity['unique_keys']} |
| Frozen case specifications | {integrity['cases']} |
| Local LLMs | {integrity['models']} |
| Generation methods | {integrity['methods']} |
| Complete 120-row conditions | {integrity['complete_conditions']}/12 |
| Live LLM outputs | {integrity['live_rows']}/{integrity['rows']} |
| Fallback outputs | {integrity['fallback_rows']} |

Every model-method condition contains case IDs `PSQ-SCO-120-001` through `PSQ-SCO-120-120`. The design is matched: the prose differs, but every method receives the same requested role, stage, age, channel, variant, and difficulty slot.

## The 120-Case Design

The case set is a controlled test grid, not a random sample of 120 unrelated stories:

```text
30 base groups = 3 channels x 2 variants x 5 roles
90 anchor cases = 30 groups x 3 difficulty anchors
30 balanced repetitions = one additional stage/age rotation per group
120 frozen specifications = 90 + 30
1,440 outputs = 120 cases x 4 methods x 3 LLMs
```

The frozen case is a **task-control reference**, not a human-written ideal scenario. It supports exact control checks and a closed-label concept oracle. It is not ground truth for pedagogy, realism, or learner outcomes.

## Four Methods as Implemented

| Method | Inputs to generation | Ontology path | Exact implementation boundary |
|---|---|---|---|
| Prompt only | Frozen case plus prompt/template | None | No external retrieval and no ontology |
| Prompt + external RAG | Frozen case plus Chroma-retrieved corpus records | None | Vector-RAG baseline when Chroma is available |
| Ontology packet + prompt + RAG | Same external RAG plus a structured semantic packet | Direct structured controls | `xml.etree.ElementTree` reads RDF/XML; local term/rule/source filtering selects a packet; runtime SPARQL is not used for packet construction |
| Ontology text + prompt + RAG | Same external RAG plus four ontology-derived text documents | Record verbalization and deterministic selected-subgraph text | The whole OWL file is not sent; this is not Microsoft GraphRAG and not JSON-LD prompting |

Method 3 is structure-first. Method 4 is text-context-first. Method 4 may include a record verbalization, scenario template, validation rule, evidence source, deterministic selected-subgraph walk, and a generated graph-guidance document. The document called a Graph-CoT trace is deterministic prompt guidance, not hidden LLM chain-of-thought.

## Ontology Validation

| Check | Result |
|---|---:|
| RDF/XML ontology | `{ontology['ontology_path']}` |
| Classes | {ontology['class_count']} |
| Named individuals | {ontology['named_individual_count']} |
| Object properties | {ontology['object_property_count']} |
| Datatype properties | {ontology['datatype_property_count']} |
| HermiT consistency | {str(ontology['reasoner_consistency']).lower()} |
| Unsatisfiable classes | {ontology['unsatisfiable_class_count']} |
| Competency-query ASK checks | {ontology['cq_passed']}/{ontology['cq_total']} |
| Runtime scenario mappings | {ontology['mapping_passed']}/{ontology['mapping_total']} |

The current evaluator imported the completed HermiT result for the same ontology file rather than launching a new HermiT process. It executed the eight ASK queries with `rdflib 7.6.0` and executed all 1,440 runtime mappings. This validates ontology consistency and query/mapping behavior; it does not validate generated prose quality.

## External RAG Dataset

| Field | Recorded value |
|---|---|
| Selected source files | {dataset['selected_file_count']} |
| Raw JSONL records before caps | {dataset['raw_document_count_before_caps']:,} |
| Records retained after caps | {dataset['used_document_count_after_caps']:,} |
| Chroma-indexed records | {dataset['chroma_index_metadata']['indexed_documents']:,} |
| Exact-text duplicates skipped | {dataset['chroma_index_metadata']['dedupe_skipped']:,} |
| Vector database | {dataset['vector_database']} |
| Vector space | {dataset['vector_space']} |
| Chunk/document unit | {dataset['chunking']} |
| Preprocessing | {dataset['preprocessing']} |

Channel composition:

{md_table(channel_rows)}

Language composition:

{md_table(language_rows)}

The corpus is heavily English/email weighted (97.35% English; 89.93% email). Voice records are 2.83%. This limits generalization claims for multilingual, SMS, and voice content. The generation RAG index used Chroma's default embedding function because `rag_engine.py` did not pass or record a custom embedding model/version. That unresolved version-freezing issue must be corrected before a final reproducibility release.

## Retrieval-Context Audit

{md_table(context_rows)}

External retrieval was not present in every nominal RAG row. This makes the recovered experiment a pipeline-level comparison of observed conditions, not a perfectly uniform retrieval ablation. Ontology-text rows always contain four ontology-text documents, but some do not contain an external corpus example.

## Dual-Profile Metric Validity Policy

The restored evaluation uses two complementary profiles. The **standard-form profile** carries the primary comparable evidence; the **PSQ mechanism-aware conformance index** restores the earlier weighted summary for dashboard continuity and sensitivity analysis. It uses:

1. Binary average pass rates for live status, JSON parseability, exact eight-control matching, and contradiction-free status.
2. Standard precision, recall, and F1 formulas over one disclosed, method-invariant closed label vocabulary.
3. Self-BLEU as an established lexical-redundancy diagnostic.
4. `1 - mean pairwise cosine similarity` over LaBSE embeddings as a relative semantic-diversity diagnostic.
5. Friedman and Wilcoxon tests for matched data, Holm correction for six post-hoc comparisons, matched rank-biserial effects, and case-level bootstrap confidence intervals.

{md_table(validity_rows, ['metric', 'display_name', 'classification', 'direction', 'primary_or_secondary', 'interpretation', 'limitation'])}

### Operational Definitions, Rationale, and Sources

{md_table(validity_rows, ['display_name', 'formula', 'why_used', 'reference', 'threshold_status', 'reporting_rule'])}

The restored PSQ index is `0.20 JSON + 0.25 control + 0.25 legacy concept F1 + 0.20 grounding + 0.10 non-contradiction`. Its weights sum to one and preserve the original design priority, but no completed external or project calibration study establishes those exact coefficients. Its legacy concept and trace terms can favor methods that expose more metadata. Following OECD/JRC composite-indicator guidance, every component, weight, direction, and limitation is disclosed and sensitivity must be examined. The score is a project mechanism diagnostic, not a standardized percentage of educational quality and not the sole basis for a winner claim.

## Primary Results

{md_table(primary_rows)}

### Correct Interpretation

- All 1,440 rows are live outputs and parseable scenario objects.
- Common-oracle F1 is effectively tied across methods (`0.9662` to `0.9667`).
- Prompt-only has the highest exact-control rate (100.00%); ontology packet RAG is 99.44%; external RAG is 98.89%; ontology-text RAG is 98.61%.
- One contradiction rule fired in ontology-text RAG, giving 99.72% contradiction-free status; the other methods are 100.00% on this bounded rule set.
- Ontology packet RAG has the strongest relative diversity profile: LaBSE diversity `0.2339` and Self-BLEU `0.7906`.
- Diversity is not quality. No universal threshold makes `0.2339` "good enough."

## Primary Case-Clustered Inference

The inferential unit is the frozen case (`n=120`), not the 360 model-case rows. Each method value is averaged across the three models within a case before testing.

Friedman omnibus result: statistic `{number(friedman['statistic']):.4f}`, `p={number(friedman['p_value']):.4f}`. The method difference on common-oracle F1 is not statistically significant at 0.05.

{md_table(paired_rows)}

No paired common-F1 contrast remains significant after Holm correction. Several rank-biserial values are +/-1 because only 4-10 cases have non-zero differences and 110-116 cases are exact ties; always report the non-zero count beside the effect size.

## Corrected Error Analysis

{md_table(error_rows)}

The trace row is secondary. Prompt-only is trace-incomplete by design, so it cannot be treated as a content-quality failure. The older method-conditioned missing-concept counts are excluded from this primary error table.

## Timing

{md_table(timing_rows, ['model_key', 'method', 'n', 'direct_timing_n', 'direct_generation_seconds_mean', 'observed_timing_n', 'observed_interarrival_seconds_mean'])}

Timing telemetry is heterogeneous. Some conditions have direct per-call duration, while others rely mainly on timestamp interarrival estimates. These are not interchangeable measurements, so this report does not rank all models/methods by speed. A future run should freeze one timing schema and hardware-load protocol.

## Ground Truth and Construct Validity

| Construct | Current reference | Valid claim | Missing evidence |
|---|---|---|---|
| Ontology consistency | OWL reasoner result | Formal consistency for this ontology version | Independent ontology expert review |
| Competency queries | Expected ASK booleans | 8/8 executable ontology questions pass | Broader CQ coverage |
| Case controls | Frozen 120-case labels | Structured adherence | Independent label audit |
| Common concept F1 | Automatic closed-label oracle | Technical concept adherence | Human gold scenario or expert annotations |
| Trace completeness | Stored provenance fields | Mechanism trace presence | Entailment/faithfulness verification |
| Diversity | LaBSE and Self-BLEU | Relative corpus diversity | Human diversity judgment and threshold calibration |
| Pedagogy/usability/realism | None completed | No conclusion yet | Blinded multi-rater evaluation and learner study |

The exported 24-row manual-inspection sheet is currently unfilled. Therefore, this experiment has no completed human ground truth for scenario usability, pedagogical quality, realism, or acceptability.

## Publication-Safe Claim

> In a frozen 120-case, three-model, four-method local-LLM study, all methods produced highly structured finalized scenario records. The ontology-packet condition showed the strongest relative diversity and complete ontology/provenance mechanism traces, but it did not significantly improve the method-invariant common concept F1. The results support ontology-guided controllability and auditability as an engineering contribution; they do not yet demonstrate superior human-rated scenario quality or learner effectiveness.

## Required Next Validation

1. Freeze and record the external RAG embedding model/version, Chroma version, index fingerprint, prompt hashes, seeds, and hardware.
2. Run blinded expert ratings on a pre-registered sample with at least cybersecurity and educational-technology expertise.
3. Report inter-rater reliability, such as Krippendorff's alpha, and adjudication rules.
4. Calibrate any composite weights on an independent training set and evaluate on held-out cases; do not fit and test weights on the same 120 cases.
5. Evaluate source entailment/faithfulness, not only trace-field presence.
6. Run learner studies before claiming pedagogical effectiveness or learning gain.

## References

{references()}
"""


def build_analysis_report(
    *,
    primary_rows: Sequence[Dict[str, Any]],
    model_rows: Sequence[Dict[str, Any]],
    paired_rows: Sequence[Dict[str, Any]],
    example_rows: Sequence[Dict[str, Any]],
    context_rows: Sequence[Dict[str, Any]],
) -> str:
    return f"""# Final Research Results Analysis and Interpretation

## Central Finding

The corrected analysis changes the research story from "one method wins overall" to a more defensible multi-metric conclusion.

1. **Technical adherence is already near ceiling.** Common case-concept F1 is about `0.966` for every method, and the case-clustered Friedman test is not significant.
2. **Ontology packet RAG has the best relative diversity profile.** It has the highest LaBSE diversity and the lowest Self-BLEU, but neither metric measures pedagogy or realism.
3. **The original composite is restored as secondary mechanism evidence.** Its fixed coefficients are uncalibrated, and two components are method-conditioned.
4. **The experiment validates a pipeline, not learner outcomes.** No completed human ratings or learning-gain data are present.

## Method-Level Evidence

{md_table(primary_rows)}

The automatic results do not show that ontology conditions improve common-oracle F1 or exact control matching over prompt-only. Their defensible benefit is stronger provenance/ontology mechanism coverage and, for the direct packet method, greater relative corpus diversity. Trace completeness is partly by construction and cannot be interpreted as content quality.

## Statistical Analysis

{md_table(paired_rows)}

The `p=0.1272` Friedman result means the study does not reject equality of common-F1 ranks across the four methods. Every Holm-adjusted post-hoc p-value is above 0.05. Because 110-116 of 120 case differences are exact ties in several contrasts, effect sizes based only on non-zero ranks can appear extreme even when the mean difference is less than one-thousandth. The non-zero sample size is therefore part of the result, not a footnote.

## Three-LLM Analysis

{md_table(model_rows)}

There is no defensible universal "best LLM" from these data. Common F1 varies only narrowly, while the legacy weighted index changes more because it rewards method traces and method-conditioned concepts. Model comparisons are additionally confounded by heterogeneous recovery runs, prompt-only engine variants, and incomplete direct timing telemetry.

## Diversity Analysis

The ordering by method-average LaBSE diversity is:

1. Ontology packet + prompt + RAG: `0.2339`
2. Ontology text + prompt + RAG: `0.2307`
3. Prompt + external RAG: `0.2289`
4. Prompt only: `0.1865`

The ordering by Self-BLEU, where lower means less lexical redundancy, is the same at the top: direct ontology packet `0.7906`, ontology text `0.8059`, external RAG `0.8106`, prompt-only `0.8846`.

This is relative evidence only. Tevet and Berant show why automatic diversity metrics do not provide a principled universal sufficiency threshold and why human judgments remain important. The correct wording is "more diverse than the compared conditions under this configuration," not "diversity is good" or "the scenario is usable."

## Matched Example: One Case, Four Generated Scenarios

{md_table(example_rows)}

This table demonstrates the matched design: the scenario prose differs, but the frozen case is the same. It also illustrates why a single ideal-reference text is unsuitable. Multiple outputs can be valid while using different surface wording.

## RAG Condition Fidelity

{md_table(context_rows)}

The nominal RAG methods do not all have a retrieved external example in every stored row. The study therefore measures the observed pipeline conditions, including retrieval misses, not a pure "retrieval always present" treatment. This must be disclosed in the paper and addressed in a future controlled ablation.

## Why the Restored Overall Index Remains Secondary

The legacy index is:

```text
0.20 JSON + 0.25 control + 0.25 legacy concept F1
+ 0.20 trace completeness + 0.10 non-contradiction
```

The coefficients were not learned from a completed calibration study. More importantly, the legacy concept oracle can add ontology-packet terms only for ontology methods, and the generated concept pool can count provenance traces. Trace completeness also rewards methods that expose traces and structurally penalizes prompt-only. This makes the composite useful as a mechanism-rich pipeline diagnostic but invalid as the sole neutral quality ranking.

The corrected primary profile avoids inventing replacement coefficients. If a composite is needed later, the scientifically defensible path is expert rubric construction followed by calibration against independent human ratings or learner outcomes, with held-out evaluation to avoid overfitting. LLM-Rubric supports multidimensional calibrated evaluation, but it does not justify importing its coefficients into this different task.

## What the Results Can and Cannot Answer

**Can answer:**

- Did the ontology pass formal consistency and CQ checks? Yes for the tested version.
- Did every condition contain the same 120 case IDs? Yes.
- Are all latest outputs live and parseable? Yes.
- Are requested controls mostly preserved? Yes, 98.61%-100.00% exact all-control pass.
- Which condition is more diverse under LaBSE and Self-BLEU? Direct ontology packet RAG.

**Cannot answer yet:**

- Which method creates the most pedagogically effective scenario?
- Which scenarios are acceptable to cybersecurity educators?
- Which method improves learner recognition, retention, or transfer?
- Whether stored provenance is faithful to every generated claim.
- Whether observed differences generalize beyond this English/email-heavy corpus and local hardware.

## Threats to Validity

1. **No completed human ratings.** The automatic measures cannot replace expert quality judgment.
2. **No learner outcomes.** Scenario generation quality is not learning effectiveness.
3. **Ceiling effects.** Structured final objects make common control metrics nearly saturated.
4. **Finalized-output evaluation.** Metrics evaluate stored post-processed objects, not raw LLM text.
5. **Method-conditioned legacy metrics.** The original composite is construct-confounded.
6. **Retrieval heterogeneity.** Some nominal RAG rows contain no external retrieved example.
7. **Embedding version gap in generation RAG.** Chroma's default embedding function was not explicitly frozen.
8. **Corpus imbalance.** 89.93% email and 97.35% English documents.
9. **Recovery-run heterogeneity.** Rows were recovered across runs and prompt implementations, so method causality is not perfectly isolated.
10. **Closed label oracle.** The common F1 oracle is automatic and bounded; it does not capture nuanced realism or pedagogy.

## Recommended Paper Results Paragraph

> The final dataset comprised 1,440 unique live LLM outputs generated from 120 matched case specifications, four generation methods, and three local models. All outputs were parseable scenario objects. Exact adherence to all eight requested controls ranged from 98.61% to 100.00%, and method-invariant common concept F1 ranged from 0.9662 to 0.9667. A case-clustered Friedman test found no significant common-F1 difference across methods (p=0.1272), and no Holm-adjusted pairwise comparison was significant. The direct ontology-packet method produced the highest relative LaBSE diversity (0.2339) and lowest Self-BLEU (0.7906). These findings support ontology-guided control, traceability, and relative diversity, but do not establish superior human-rated pedagogy, realism, usability, or learner outcomes.

## References

{references()}
"""


def build_adviser_response(
    *,
    primary_rows: Sequence[Dict[str, Any]],
    context_rows: Sequence[Dict[str, Any]],
    example_rows: Sequence[Dict[str, Any]],
) -> str:
    responses = [
        {"Adviser concern": "What is the presentation about?", "Project response": "A controlled ontology-guided generation and validation pipeline for cybersecurity serious-game scenarios, not a general LLM story generator and not a learner-effectiveness study.", "Evidence/change": "Slides 10-13 use the frozen 1,440-row live study and metric-specific claims."},
        {"Adviser concern": "Methods 3 and 4 are confusing.", "Project response": "Method 3 injects a structured semantic packet; Method 4 verbalizes selected ontology records into four text documents. They are different prompt representations of the same authoritative ontology.", "Evidence/change": "Method definitions now name the exact payload, selector, and trace fields."},
        {"Adviser concern": "Is the whole ontology sent, and in what format?", "Project response": "No. The authoritative file is RDF/XML OWL. A lightweight ElementTree reader selects records. The full ontology, Turtle, and JSON-LD are not sent to the LLM.", "Evidence/change": "Technical report records the actual code boundary."},
        {"Adviser concern": "Is this GraphRAG?", "Project response": "No. It is ontology-guided RAG / ontology-to-text RAG. It does not build document communities or community summaries as Microsoft GraphRAG does.", "Evidence/change": "The GraphRAG label is removed from the claim."},
        {"Adviser concern": "What are the RAG sources and configuration?", "Project response": "23 JSONL files, 87,661 raw records, 29,731 retained, 28,728 Chroma-indexed, cosine HNSW, one-record-per-document concatenation, deduplication and profile caps.", "Evidence/change": "Dataset section includes source and language/channel composition."},
        {"Adviser concern": "Was the vector embedding tuned/frozen?", "Project response": "Not fully. `rag_engine.py` relies on Chroma's default embedding function and did not record a model/version. This is now a declared reproducibility limitation and required next fix.", "Evidence/change": "No unsupported embedding identity is claimed."},
        {"Adviser concern": "Conformance to what?", "Project response": "The primary evidence now names each referent: frozen controls, closed case-concept oracle, contradiction rules, traces, or ontology CQs. The weighted overall index is secondary only.", "Evidence/change": "Standard metric profile replaces the composite headline."},
        {"Adviser concern": "Is the combined score standard?", "Project response": "No. The exact legacy coefficients are project-defined and uncalibrated. No source is claimed to justify those numbers.", "Evidence/change": "No replacement coefficients are invented; calibration is deferred to independent human/learner data."},
        {"Adviser concern": "Prompt-only F1 should be 1.0, right?", "Project response": "No. F1 is not similarity to prompt-only. Every method predicts labels against the same frozen case oracle. Prompt-only can miss an oracle label.", "Evidence/change": "The scorer now uses a closed, method-invariant label vocabulary and excludes traces."},
        {"Adviser concern": "What do 120 cases mean?", "Project response": "Thirty role-channel-variant groups, three difficulty anchors each, plus one balanced age/stage repetition per group. The same IDs are used under every method and LLM.", "Evidence/change": "Integrity audit confirms 120/120 matched cases for all 12 conditions."},
        {"Adviser concern": "Are diversity values good enough?", "Project response": "There is no universal acceptance threshold. The study reports only relative ordering: ontology packet RAG is most diverse in this comparison.", "Evidence/change": "All low/medium/high thresholds were removed."},
        {"Adviser concern": "Are scenarios usable and manually checked?", "Project response": "Not yet demonstrated. A 24-row stratified manual sheet exists but is blank. Automatic technical checks cannot establish usability, pedagogy, or realism.", "Evidence/change": "The report prohibits human-quality claims until blinded ratings and reliability are completed."},
        {"Adviser concern": "Custom metrics need proper definitions.", "Project response": "Every metric is now classified as a standard formula, a literature-grounded diagnostic, or a project-defined construct, with formula, reference, use, and limitation.", "Evidence/change": "`metric_validity_registry.csv` is part of the run."},
        {"Adviser concern": "Freeze the experiment and write.", "Project response": "The authoritative frozen bundle has 1,440 unique live outputs and zero fallbacks. Further automatic metrics are not needed for the current paper claim.", "Evidence/change": "The next work is human validation, reproducibility freezing, and writing, not metric accumulation."},
    ]
    return f"""# Point-by-Point Adviser Response: Standardized Scenario Evaluation

## One-Sentence Research Story

PersonaShield Quest tests whether an OWL/RDF scenario-control ontology can make local-LLM cybersecurity game-scenario generation more controllable, auditable, and diverse than prompt-only or ordinary external text-RAG, while keeping claims separate from unmeasured learner effectiveness.

## Response Matrix

{md_table(responses)}

## Current Evidence Used in the Response

{md_table(primary_rows)}

## Retrieval Audit Used in the Response

{md_table(context_rows)}

## Concrete Same-Case Example

{md_table(example_rows)}

## Final Claim Boundary

The final study can claim a functioning, formally checked ontology-control pipeline and a relative diversity advantage for direct ontology-packet RAG. It cannot claim that ontology methods are more pedagogically effective, more realistic to experts, or better for learners until a separate human and learner-outcome study is completed.

## References

{references()}
"""


def create_figures(evaluation_dir: Path, standard_rows: Sequence[Dict[str, str]], stats: Dict[str, Any]) -> None:
    # The bundled research runtime may not include Tcl/Tk. Force a deterministic
    # headless backend and keep Matplotlib's cache inside the evaluation bundle.
    matplotlib_cache = evaluation_dir / ".matplotlib"
    matplotlib_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    os.environ.setdefault("MPLBACKEND", "Agg")

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np

    figure_dir = evaluation_dir / "slide_figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    labels = [METHOD_LABELS[row["method"]] for row in standard_rows]
    table_labels = {
        "prompt_only": "Prompt only",
        "prompt_rag": "Prompt + RAG",
        "ontology_prompt_rag": "Ontology packet",
        "ontology_text_rag": "Ontology text RAG",
    }
    colors = [METHOD_COLORS[row["method"]] for row in standard_rows]

    # Slide 10: a readable standards-based metric table as a figure.
    fig, ax = plt.subplots(figsize=(13.0, 5.6), dpi=180)
    ax.axis("off")
    columns = ["Method", "JSON pass", "All controls", "Common F1", "Contradiction-free"]
    cells = [
        [
            table_labels[row["method"]],
            pct(row["json_parse_pass_rate"]),
            pct(row["all_controls_exact_match_rate"]),
            dec(row["common_case_concept_f1"]),
            pct(row["contradiction_free_pass_rate"]),
        ]
        for row in standard_rows
    ]
    table = ax.table(
        cellText=cells,
        colLabels=columns,
        colWidths=[0.25, 0.17, 0.18, 0.17, 0.23],
        loc="center",
        cellLoc="center",
        colLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(13)
    table.scale(1, 2.15)
    for column in range(len(columns)):
        table[(0, column)].set_facecolor("#243746")
        table[(0, column)].set_text_props(color="white", weight="bold")
    for row_index, color in enumerate(colors, start=1):
        table[(row_index, 0)].set_facecolor(color)
        table[(row_index, 0)].set_text_props(color="white", weight="bold")
        for column in range(1, len(columns)):
            table[(row_index, column)].set_facecolor("#F3F6F8" if row_index % 2 else "#E8EEF2")
    ax.set_title("Primary standard-metric profile: finalized stored scenarios", fontsize=22, weight="bold", pad=18)
    fig.text(0.5, 0.06, "Common F1 uses one closed case oracle. No composite winner score is used.", ha="center", fontsize=12)
    fig.tight_layout()
    fig.savefig(figure_dir / "slide10_standard_metric_profile.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Slide 11: relative diversity, both axes begin at zero.
    embedding = [number(row["embedding_diversity"]) for row in standard_rows]
    self_bleu = [number(row["self_bleu"]) for row in standard_rows]
    y = np.arange(len(labels))
    fig, axes = plt.subplots(1, 2, figsize=(13.0, 6.4), dpi=180)
    axes[0].barh(y, embedding, color=colors)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 0.26)
    axes[0].set_xlabel("1 - mean pairwise LaBSE cosine similarity")
    axes[0].set_title("Semantic diversity (higher is more dispersed)")
    for index, value in enumerate(embedding):
        axes[0].text(value + 0.004, index, f"{value:.4f}", va="center", fontsize=10)
    axes[1].barh(y, self_bleu, color=colors)
    axes[1].set_yticks(y, [""] * len(y))
    axes[1].invert_yaxis()
    axes[1].set_xlim(0, 1.0)
    axes[1].set_xlabel("Self-BLEU")
    axes[1].set_title("Lexical redundancy (lower is less repetitive)")
    for index, value in enumerate(self_bleu):
        axes[1].text(value + 0.012, index, f"{value:.4f}", va="center", fontsize=10)
    fig.suptitle("Relative diversity across the four methods", fontsize=22, weight="bold")
    fig.text(0.5, 0.015, "Within-study comparison only. No universal acceptance threshold is claimed.", ha="center", fontsize=11)
    fig.tight_layout(rect=(0, 0.04, 1, 0.92))
    fig.savefig(figure_dir / "slide11_diversity.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # Slide 12: case-clustered common-F1 differences in units per 1,000.
    comparisons = stats["primary_case_clustered_analysis"]["comparisons"]
    names = [f"{METHOD_LABELS[row['right']]} -\n{METHOD_LABELS[row['left']]}" for row in comparisons]
    estimates = np.array([number(row["mean_difference_right_minus_left"]) * 1000 for row in comparisons])
    lower = np.array([number(row["bootstrap_ci95"][0]) * 1000 for row in comparisons])
    upper = np.array([number(row["bootstrap_ci95"][1]) * 1000 for row in comparisons])
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(13.0, 6.8), dpi=180)
    ax.axvline(0, color="#333333", linewidth=1.3)
    ax.errorbar(estimates, y, xerr=[estimates - lower, upper - estimates], fmt="o", color="#2A6F97", ecolor="#7A8B99", capsize=5)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlabel("Mean common-F1 difference per 1,000 (right - left)")
    ax.set_title("Case-clustered paired differences: no Holm-adjusted contrast is significant", fontsize=18, weight="bold")
    for index, row in enumerate(comparisons):
        holm = number((row.get("wilcoxon_signed_rank") or {}).get("holm_adjusted_p_value"), 1)
        ax.text(upper[index] + 0.04, index, f"Holm p={holm:.3f}; non-zero n={row['nonzero_difference_n']}", va="center", fontsize=9)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(figure_dir / "slide12_clustered_f1_forest.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    evaluation_dir = args.evaluation_dir.resolve()
    generation_dir = args.generation_dir.resolve()
    score_rows = read_csv(evaluation_dir / "scenario_scores.csv")
    standard_rows = read_csv(evaluation_dir / "standard_metric_summary.csv")
    condition_rows = read_csv(evaluation_dir / "condition_manifest.csv")
    model_rows_raw = read_csv(evaluation_dir / "model_method_summary.csv")
    diversity_rows = read_csv(evaluation_dir / "semantic_diversity.csv")
    timing_rows = read_csv(evaluation_dir / "timing_analysis.csv")
    validity_rows = metric_validity_registry()
    write_csv(evaluation_dir / "metric_validity_registry.csv", validity_rows)
    ontology = json.loads((evaluation_dir / "ontology_validation.json").read_text(encoding="utf-8"))
    dataset = json.loads((evaluation_dir / "dataset_description.json").read_text(encoding="utf-8"))
    stats = json.loads((evaluation_dir / "paired_statistics.json").read_text(encoding="utf-8"))

    integrity = verify_study(score_rows, condition_rows)
    errors = standard_error_rows(score_rows)
    context_rows = context_audit(generation_dir)
    examples = matched_example(generation_dir)
    primary = primary_results_table(standard_rows)
    paired = paired_table(stats)
    models = model_method_table(model_rows_raw, diversity_rows)

    write_csv(evaluation_dir / "standard_error_analysis.csv", errors)
    (evaluation_dir / "retrieval_context_audit.json").write_text(
        json.dumps(context_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for filename in ("evaluation_report.md", "research_paper_results_analysis.md"):
        current = evaluation_dir / filename
        backup = evaluation_dir / filename.replace(".md", "_pre_standardization_backup.md")
        if current.exists() and not backup.exists():
            shutil.copy2(current, backup)

    evaluation_text = build_evaluation_report(
        evaluation_dir=evaluation_dir,
        generation_dir=generation_dir,
        integrity=integrity,
        ontology=ontology,
        dataset=dataset,
        primary_rows=primary,
        error_rows=errors,
        paired_rows=paired,
        stats=stats,
        context_rows=context_rows,
        validity_rows=validity_rows,
        timing_rows=timing_rows,
    )
    analysis_text = build_analysis_report(
        primary_rows=primary,
        model_rows=models,
        paired_rows=paired,
        example_rows=examples,
        context_rows=context_rows,
    )
    adviser_text = build_adviser_response(
        primary_rows=primary,
        context_rows=context_rows,
        example_rows=examples,
    )
    (evaluation_dir / "evaluation_report.md").write_text(evaluation_text, encoding="utf-8")
    (evaluation_dir / "research_paper_results_analysis.md").write_text(analysis_text, encoding="utf-8")
    (evaluation_dir / "ADVISER_COMMENT_RESPONSE_STANDARDIZED_EVALUATION.md").write_text(adviser_text, encoding="utf-8")

    slide_source = f"""# Slides 10-13 Source Data

## Slide 10: Dual-profile metric framework
{md_table(primary)}

## Slide 11: Restored PSQ conformance index
The earlier weighted index is restored as a secondary mechanism-aware summary:

`C_PSQ = 0.20 JSON + 0.25 control + 0.25 legacy F1 + 0.20 grounding + 0.10 non-contradiction`.

The coefficients preserve the original design priority but were not empirically
calibrated. The index must be shown with the standard component profile because
legacy F1 and trace terms are method-conditioned.

- JSON parse pass: 100.00% for every method.
- All eight controls exact: 98.61%-100.00%.
- Common case-concept F1: 0.9662-0.9667.
- Contradiction-free: 99.72%-100.00%.
- Restored PSQ index: Prompt 0.7741; External RAG 0.8181; Ontology packet 0.8860; Ontology text 0.8491.

## Slide 12: Case-clustered inference
Friedman p = {number(stats['primary_case_clustered_analysis']['friedman']['p_value']):.4f}. No Holm-adjusted contrast is significant.

{md_table(paired)}

## Slide 13: Relative diversity
Use the LaBSE diversity and Self-BLEU columns from slide 10. Ontology packet RAG
has the highest LaBSE diversity (`0.2339`) and lowest Self-BLEU (`0.7906`) in
this comparison. These are relative diagnostics; no universal quality threshold
is claimed.

## Cross-slide claim boundary
Can claim: complete live matched dataset, formal ontology checks, near-ceiling
technical adherence, and the strongest relative diversity for the direct
ontology packet condition.

Cannot claim: superior human-rated quality, pedagogy, usability, realism, or
learner effectiveness.
"""
    (evaluation_dir / "SLIDES_10_13_SOURCE_DATA.md").write_text(slide_source, encoding="utf-8")
    figure_status = "skipped_by_flag" if args.skip_figures else "generated"
    if not args.skip_figures:
        try:
            create_figures(evaluation_dir, standard_rows, stats)
        except ModuleNotFoundError as exc:
            if exc.name != "matplotlib":
                raise
            figure_status = "skipped_missing_matplotlib"

    print(
        json.dumps(
            {
                "evaluation_dir": str(evaluation_dir),
                "integrity": integrity,
                "reports": [
                    "evaluation_report.md",
                    "research_paper_results_analysis.md",
                    "ADVISER_COMMENT_RESPONSE_STANDARDIZED_EVALUATION.md",
                    "SLIDES_10_13_SOURCE_DATA.md",
                ],
                "figure_status": figure_status,
                "figures": [path.name for path in sorted((evaluation_dir / "slide_figures").glob("*.png"))],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
