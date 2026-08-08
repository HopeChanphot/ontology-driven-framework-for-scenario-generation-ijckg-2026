"""Method/model comparison and lightweight paired statistics."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .models import METHOD_CONDITION_NUMBERS, METHOD_LABELS, METHOD_ORDER, ScenarioScore
from .technical_decisions import DECISION_ORDER


METRIC_COLUMNS = (
    "json_validity",
    "schema_completeness",
    "control_adherence",
    "required_concept_precision",
    "required_concept_recall",
    "required_concept_f1",
    "common_case_concept_precision",
    "common_case_concept_recall",
    "common_case_concept_f1",
    "grounding_completeness",
    "ontology_semantic_scope",
    "contradiction_rate",
    "overall_conformance",
)


def method_summary(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Summarize the main scenario-validation metrics by generation method."""

    rows: List[Dict[str, Any]] = []
    by_method: Dict[str, List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        by_method[score.method].append(score)
    for method in METHOD_ORDER:
        group = by_method.get(method, [])
        if not group:
            continue
        rows.append(_summary_row(_method_fields(method), group))
    return rows


def model_method_summary(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Summarize primary metrics and legacy conformance by LLM and method."""

    by_pair: Dict[Tuple[str, str], List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        by_pair[(score.model_key, score.method)].append(score)
    rows: List[Dict[str, Any]] = []
    for (model_key, method), group in sorted(by_pair.items()):
        rows.append(
            {
                "model_key": model_key,
                **_method_fields(method),
                "n": len(group),
                "overall_conformance_mean": _safe_mean([x.overall_conformance for x in group]),
                "overall_conformance_median": _safe_median([x.overall_conformance for x in group]),
                "overall_conformance_sd": _safe_pstdev([x.overall_conformance for x in group]),
                "common_case_concept_f1_mean": _safe_mean([x.common_case_concept_f1 for x in group]),
                "all_controls_exact_match_rate": _safe_mean([x.all_controls_exact_match for x in group]),
                "contradiction_free_pass_rate": _safe_mean([x.contradiction_free_pass for x in group]),
            }
        )
    return rows


def decision_summary(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Count automated technical-triage decisions by condition."""

    rows: List[Dict[str, Any]] = []
    for method in METHOD_ORDER:
        group = [score for score in scores if score.method == method]
        if not group:
            continue
        row: Dict[str, Any] = {**_method_fields(method), "n": len(group)}
        counts = Counter(score.automated_decision for score in group)
        for decision in DECISION_ORDER:
            key = decision.lower()
            row[f"{key}_count"] = counts.get(decision, 0)
            row[f"{key}_percentage"] = counts.get(decision, 0) / len(group)
        row["decision_scope"] = "automated technical triage; PCUE and human approval remain required"
        rows.append(row)
    return rows


def model_method_decision_summary(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Count automated technical-triage decisions by LLM and condition."""

    grouped: Dict[Tuple[str, str], List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        grouped[(score.model_key, score.method)].append(score)
    rows: List[Dict[str, Any]] = []
    for (model_key, method), group in sorted(grouped.items()):
        counts = Counter(score.automated_decision for score in group)
        row: Dict[str, Any] = {"model_key": model_key, **_method_fields(method), "n": len(group)}
        for decision in DECISION_ORDER:
            key = decision.lower()
            row[f"{key}_count"] = counts.get(decision, 0)
            row[f"{key}_percentage"] = counts.get(decision, 0) / len(group)
        rows.append(row)
    return rows


def model_method_matrix(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Return compact 3 x 3 style rows: one row per model, one score per method."""

    by_pair: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for score in scores:
        by_pair[(score.model_key, score.method)].append(score.overall_conformance)
    models = sorted({score.model_key for score in scores})
    rows: List[Dict[str, Any]] = []
    for model in models:
        row: Dict[str, Any] = {"model_key": model}
        for method in METHOD_ORDER:
            values = by_pair.get((model, method), [])
            row[method] = _safe_mean(values)
        rows.append(row)
    return rows


def error_analysis(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Count major error categories by method."""

    categories = {
        "missing_evidence": lambda s: s.grounding_completeness < 1.0,
        "schema_incomplete": lambda s: s.schema_completeness < 1.0,
        "wrong_channel": lambda s: "channel" in s.failed_control_fields,
        "wrong_attack": lambda s: "attack_type" in s.failed_control_fields,
        "unsafe_action": lambda s: any("unsafe_correct_action" in reason for reason in s.contradiction_reasons),
        "contradiction": lambda s: bool(s.contradiction),
        "missing_required_concepts": lambda s: s.required_concept_recall < 1.0,
        "invalid_json_or_missing_scenario": lambda s: s.json_validity < 1.0,
        "invalid_json_or_schema": lambda s: s.json_validity < 1.0 or s.schema_completeness < 1.0,
    }
    rows: List[Dict[str, Any]] = []
    for category, predicate in categories.items():
        row: Dict[str, Any] = {"error_type": category}
        for method in METHOD_ORDER:
            group = [score for score in scores if score.method == method]
            row[method] = sum(1 for score in group if predicate(score))
        rows.append(row)
    return rows


def paper_labeled_error_analysis(scores: Sequence[ScenarioScore]) -> List[Dict[str, Any]]:
    """Return paper-facing error labels while preserving raw reproducibility elsewhere."""

    categories = (
        (
            "missing_evidence",
            lambda s: s.grounding_completeness < 1.0,
            "Output lacks full evidence/provenance grounding.",
        ),
        (
            "wrong_channel",
            lambda s: "channel" in s.failed_control_fields,
            "Generated channel does not match requested channel.",
        ),
        (
            "wrong_attack",
            lambda s: "attack_type" in s.failed_control_fields,
            "Generated attack type does not match requested channel/variant expectation.",
        ),
        (
            "unsafe_action",
            lambda s: any("unsafe_correct_action" in reason for reason in s.contradiction_reasons),
            "Generated response recommends unsafe or inappropriate defensive behavior.",
        ),
        (
            "contradiction",
            lambda s: bool(s.contradiction),
            "Generated scenario contains a serious internal inconsistency.",
        ),
        (
            "common_case_concept_not_perfect_recall",
            lambda s: s.common_case_concept_recall < 1.0,
            "Strict diagnostic using the method-invariant case oracle; interpret with common-case precision, recall, and F1.",
        ),
        (
            "legacy_method_conditioned_concept_not_perfect_recall",
            lambda s: s.required_concept_recall < 1.0,
            "Backward-compatible diagnostic only; its oracle can include method-specific packet concepts.",
        ),
        (
            "schema_provenance_incomplete",
            lambda s: s.schema_completeness < 1.0,
            "The row is parseable, but required executable fields or evidence/provenance fields are incomplete.",
        ),
        (
            "invalid_json_or_missing_scenario",
            lambda s: s.json_validity < 1.0,
            "The row could not be parsed into an inspectable scenario object; reported means are average pass rates.",
        ),
    )
    rows: List[Dict[str, Any]] = []
    for category, predicate, interpretation in categories:
        row: Dict[str, Any] = {"error_type": category}
        for method in METHOD_ORDER:
            group = [score for score in scores if score.method == method]
            row[method] = sum(1 for score in group if predicate(score))
        row["interpretation"] = interpretation
        rows.append(row)
    return rows


def paired_statistics(scores: Sequence[ScenarioScore]) -> Dict[str, Any]:
    """Compute paired analyses with model-case and case-clustered estimands.

    The primary analysis uses the method-invariant common-case concept F1. The
    fixed-weight overall conformance index remains as a secondary compatibility
    analysis. Case-clustered results average the three model outputs within each
    frozen case before inference, so the inferential unit is the 120 case
    specification rather than 360 correlated model-case rows.
    """

    primary_model_case = _metric_analysis_by_model_case(scores, "common_case_concept_f1")
    primary_case_clustered = _metric_analysis_by_case(scores, "common_case_concept_f1")
    legacy_model_case = _metric_analysis_by_model_case(scores, "overall_conformance")
    legacy_case_clustered = _metric_analysis_by_case(scores, "overall_conformance")
    binary = _binary_pass_analysis(scores)
    legacy_friedman_alias = dict(legacy_model_case.get("friedman", {}))
    legacy_friedman_alias.update(
        {
            "metric": "overall_conformance",
            "deprecated_alias": True,
            "replacement": "all_method_friedman_primary_model_case or all_method_friedman_legacy_model_case",
        }
    )

    return {
        "notes": [
            "Primary inference uses the method-invariant common-case concept F1.",
            "The common oracle is project-specific; precision, recall, F1, Wilcoxon, Friedman, Holm, bootstrap, and rank-biserial formulas are standard.",
            "Case-clustered analysis (n=120 cases) is primary because every case is repeated across three LLMs.",
            "Legacy overall conformance is retained only for backward compatibility and sensitivity analysis.",
        ],
        "primary_metric": "common_case_concept_f1",
        "primary_model_case_analysis": primary_model_case,
        "primary_case_clustered_analysis": primary_case_clustered,
        "binary_pass_analysis": binary,
        "secondary_legacy_overall_conformance": {
            "model_case_analysis": legacy_model_case,
            "case_clustered_analysis": legacy_case_clustered,
        },
        "all_method_friedman_primary_model_case": primary_model_case.get("friedman", {}),
        "all_method_friedman_primary_case_clustered": primary_case_clustered.get("friedman", {}),
        "all_method_friedman_legacy_model_case": legacy_model_case.get("friedman", {}),
        "all_method_friedman_legacy_case_clustered": legacy_case_clustered.get("friedman", {}),
        # Backward-compatible aliases for earlier report consumers.
        "comparisons": legacy_model_case.get("comparisons", []),
        "all_method_friedman": legacy_friedman_alias,
        "all_method_cochran_q": binary.get("cochran_q", {}),
    }


def _summary_row(prefix: Dict[str, Any], group: Sequence[ScenarioScore]) -> Dict[str, Any]:
    row = dict(prefix)
    row["n"] = len(group)
    row["json_validity"] = _safe_mean([x.json_validity for x in group])
    row["schema_completeness"] = _safe_mean([x.schema_completeness for x in group])
    row["game_schema_completeness"] = _safe_mean([x.game_schema_completeness for x in group])
    row["control_adherence"] = _safe_mean([x.control_adherence for x in group])
    row["required_concept_precision"] = _safe_mean([x.required_concept_precision for x in group])
    row["required_concept_recall"] = _safe_mean([x.required_concept_recall for x in group])
    row["required_concept_f1"] = _safe_mean([x.required_concept_f1 for x in group])
    row["common_case_concept_precision"] = _safe_mean([x.common_case_concept_precision for x in group])
    row["common_case_concept_recall"] = _safe_mean([x.common_case_concept_recall for x in group])
    row["common_case_concept_f1"] = _safe_mean([x.common_case_concept_f1 for x in group])
    row["json_parse_pass_rate"] = _safe_mean([x.json_parse_pass for x in group])
    row["schema_complete_pass_rate"] = _safe_mean([x.schema_complete_pass for x in group])
    row["game_schema_complete_pass_rate"] = _safe_mean([x.game_schema_complete_pass for x in group])
    row["all_controls_exact_match_rate"] = _safe_mean([x.all_controls_exact_match for x in group])
    row["trace_complete_pass_rate"] = _safe_mean([x.trace_complete_pass for x in group])
    row["contradiction_free_pass_rate"] = _safe_mean([x.contradiction_free_pass for x in group])
    row["grounding_completeness"] = _safe_mean([x.grounding_completeness for x in group])
    row["ontology_semantic_scope"] = _safe_mean([x.ontology_semantic_scope for x in group])
    row["contradiction_rate"] = _safe_mean([x.contradiction for x in group])
    row["overall_conformance"] = _safe_mean([x.overall_conformance for x in group])
    row["live_llm_rate"] = _safe_mean([1.0 if x.used_live_llm else 0.0 for x in group])
    row["fallback_rate"] = _safe_mean([1.0 if x.used_fallback else 0.0 for x in group])
    row["generation_seconds_mean"] = _safe_mean([x.generation_seconds for x in group if x.generation_seconds is not None])
    row["observed_interarrival_seconds_mean"] = _safe_mean(
        [x.observed_interarrival_seconds for x in group if x.observed_interarrival_seconds is not None]
    )
    row["parse_retry_count_mean"] = _safe_mean([float(x.parse_retry_count) for x in group])
    row["overall_conformance_ci95_low"], row["overall_conformance_ci95_high"] = bootstrap_ci(
        [x.overall_conformance for x in group]
    )
    return row


def _method_fields(method: str) -> Dict[str, Any]:
    return {
        "method": method,
        "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
        "condition_name": METHOD_LABELS.get(method, method),
    }


COMPARISON_PAIRS = (
    ("prompt_only", "prompt_rag"),
    ("prompt_rag", "ontology_prompt_rag"),
    ("ontology_prompt_rag", "ontology_text_rag"),
    ("prompt_rag", "ontology_text_rag"),
    ("prompt_only", "ontology_prompt_rag"),
    ("prompt_only", "ontology_text_rag"),
)


def _metric_analysis_by_model_case(scores: Sequence[ScenarioScore], metric: str) -> Dict[str, Any]:
    by_key: Dict[Tuple[str, str], Dict[str, ScenarioScore]] = defaultdict(dict)
    for score in scores:
        by_key[(score.model_key, score.case_id)][score.method] = score

    comparisons: List[Dict[str, Any]] = []
    for left, right in COMPARISON_PAIRS:
        pairs = [(methods[left], methods[right]) for methods in by_key.values() if left in methods and right in methods]
        comparisons.append(
            _paired_numeric_comparison(
                left,
                right,
                [_score_metric(a, metric) for a, _ in pairs],
                [_score_metric(b, metric) for _, b in pairs],
                metric=metric,
                unit="model_case",
            )
        )
    _attach_holm_adjusted_p_values(comparisons)
    complete = [methods for methods in by_key.values() if all(method in methods for method in METHOD_ORDER)]
    matrix = [[_score_metric(methods[method], metric) for method in METHOD_ORDER] for methods in complete]
    return {
        "metric": metric,
        "unit": "model_case",
        "complete_block_n": len(complete),
        "comparisons": comparisons,
        "friedman": _friedman_optional(matrix),
    }


def _metric_analysis_by_case(scores: Sequence[ScenarioScore], metric: str) -> Dict[str, Any]:
    values: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for score in scores:
        values[score.case_id][score.method].append(_score_metric(score, metric))
    case_means: Dict[str, Dict[str, float]] = {
        case_id: {method: mean(method_values) for method, method_values in methods.items()}
        for case_id, methods in values.items()
    }

    comparisons: List[Dict[str, Any]] = []
    for left, right in COMPARISON_PAIRS:
        paired = [methods for methods in case_means.values() if left in methods and right in methods]
        comparisons.append(
            _paired_numeric_comparison(
                left,
                right,
                [methods[left] for methods in paired],
                [methods[right] for methods in paired],
                metric=metric,
                unit="case_cluster",
            )
        )
    _attach_holm_adjusted_p_values(comparisons)
    complete = [methods for methods in case_means.values() if all(method in methods for method in METHOD_ORDER)]
    matrix = [[methods[method] for method in METHOD_ORDER] for methods in complete]
    return {
        "metric": metric,
        "unit": "case_cluster",
        "cluster_definition": "mean across available LLMs within each frozen case and method",
        "complete_case_n": len(complete),
        "comparisons": comparisons,
        "friedman": _friedman_optional(matrix),
    }


def _paired_numeric_comparison(
    left: str,
    right: str,
    left_values: Sequence[float],
    right_values: Sequence[float],
    *,
    metric: str,
    unit: str,
) -> Dict[str, Any]:
    differences = [right_value - left_value for left_value, right_value in zip(left_values, right_values)]
    non_zero = [difference for difference in differences if difference != 0.0]
    return {
        "metric": metric,
        "unit": unit,
        "left": left,
        "right": right,
        "paired_n": len(differences),
        "nonzero_difference_n": len(non_zero),
        "positive_difference_n": sum(1 for difference in non_zero if difference > 0),
        "negative_difference_n": sum(1 for difference in non_zero if difference < 0),
        "tie_n": len(differences) - len(non_zero),
        "mean_left": _safe_mean(left_values),
        "mean_right": _safe_mean(right_values),
        "mean_difference_right_minus_left": _safe_mean(differences),
        "median_difference_right_minus_left": _safe_median(differences),
        "bootstrap_ci95": bootstrap_ci(differences, iterations=5000),
        "wilcoxon_signed_rank": _wilcoxon_optional(left_values, right_values),
        "matched_rank_biserial": rank_biserial_from_differences(differences),
        "sign_dominance": sign_dominance_from_differences(differences),
    }


def _binary_pass_analysis(scores: Sequence[ScenarioScore]) -> Dict[str, Any]:
    by_key: Dict[Tuple[str, str], Dict[str, ScenarioScore]] = defaultdict(dict)
    for score in scores:
        by_key[(score.model_key, score.case_id)][score.method] = score
    complete = [methods for methods in by_key.values() if all(method in methods for method in METHOD_ORDER)]
    matrix = [[methods[method].contradiction_free_pass for method in METHOD_ORDER] for methods in complete]
    comparisons: List[Dict[str, Any]] = []
    for left, right in COMPARISON_PAIRS:
        paired = [(methods[left], methods[right]) for methods in by_key.values() if left in methods and right in methods]
        comparisons.append(
            {
                "left": left,
                "right": right,
                "paired_n": len(paired),
                "mcnemar": _mcnemar_exact(
                    [a.contradiction_free_pass for a, _ in paired],
                    [b.contradiction_free_pass for _, b in paired],
                ),
            }
        )
    return {
        "metric": "contradiction_free_pass",
        "unit": "model_case",
        "complete_block_n": len(complete),
        "comparisons": comparisons,
        "cochran_q": _cochran_q_optional(matrix),
    }


def _score_metric(score: ScenarioScore, metric: str) -> float:
    return float(getattr(score, metric))


def _attach_holm_adjusted_p_values(comparisons: Sequence[Dict[str, Any]]) -> None:
    completed: List[Tuple[int, float]] = []
    for index, comparison in enumerate(comparisons):
        test = comparison.get("wilcoxon_signed_rank", {})
        if test.get("status") == "completed" and test.get("p_value") is not None:
            completed.append((index, float(test["p_value"])))
    ordered = sorted(completed, key=lambda item: item[1])
    running = 0.0
    total = len(ordered)
    for rank, (index, p_value) in enumerate(ordered):
        adjusted = min(1.0, (total - rank) * p_value)
        running = max(running, adjusted)
        comparisons[index]["wilcoxon_signed_rank"]["holm_adjusted_p_value"] = running
        comparisons[index]["wilcoxon_signed_rank"]["holm_family_size"] = total


def _wilcoxon_optional(left: Sequence[float], right: Sequence[float]) -> Dict[str, Any]:
    if len(left) < 2:
        return {"status": "not_run_too_few_pairs"}
    if all(float(a) == float(b) for a, b in zip(left, right)):
        return {"status": "not_run_all_differences_zero", "statistic": 0.0, "p_value": 1.0}
    try:
        from scipy.stats import wilcoxon  # type: ignore
    except Exception:
        return {"status": "not_run_scipy_not_installed"}
    try:
        statistic, p_value = wilcoxon(right, left, zero_method="wilcox")
        return {"status": "completed", "statistic": float(statistic), "p_value": float(p_value)}
    except Exception as exc:
        return {"status": f"not_run_error:{type(exc).__name__}:{str(exc)[:200]}"}


def _friedman_optional(matrix: Sequence[Sequence[float]]) -> Dict[str, Any]:
    if len(matrix) < 2:
        return {"status": "not_run_too_few_blocks"}
    if all(len(set(float(value) for value in row)) <= 1 for row in matrix):
        return {
            "status": "not_run_all_blocks_tied",
            "n_blocks": len(matrix),
            "statistic": 0.0,
            "p_value": 1.0,
            "interpretation": "Every method has the same value within every matched block; no rank variation exists to test.",
        }
    try:
        from scipy.stats import friedmanchisquare  # type: ignore
    except Exception:
        return {"status": "not_run_scipy_not_installed", "n_blocks": len(matrix)}
    try:
        columns = list(zip(*matrix))
        statistic, p_value = friedmanchisquare(*columns)
        if math.isnan(float(statistic)) or math.isnan(float(p_value)):
            return {"status": "not_run_degenerate_rank_variance", "n_blocks": len(matrix)}
        return {"status": "completed", "n_blocks": len(matrix), "statistic": float(statistic), "p_value": float(p_value)}
    except Exception as exc:
        return {"status": f"not_run_error:{type(exc).__name__}:{str(exc)[:200]}", "n_blocks": len(matrix)}


def _cochran_q_optional(matrix: Sequence[Sequence[int]]) -> Dict[str, Any]:
    if len(matrix) < 2 or not matrix or len(matrix[0]) < 2:
        return {"status": "not_run_too_few_blocks_or_methods", "n_blocks": len(matrix)}
    k = len(matrix[0])
    if any(len(row) != k or any(int(value) not in (0, 1) for value in row) for row in matrix):
        return {"status": "not_run_invalid_binary_matrix", "n_blocks": len(matrix)}
    column_totals = [sum(int(row[column]) for row in matrix) for column in range(k)]
    row_totals = [sum(int(value) for value in row) for row in matrix]
    total = sum(column_totals)
    denominator = k * total - sum(value * value for value in row_totals)
    if denominator == 0:
        return {
            "status": "not_run_no_discordant_blocks",
            "n_blocks": len(matrix),
            "statistic": 0.0,
            "p_value": 1.0,
        }
    numerator = (k - 1) * (k * sum(value * value for value in column_totals) - total * total)
    statistic = numerator / denominator
    try:
        from scipy.stats import chi2  # type: ignore

        p_value = float(chi2.sf(statistic, k - 1))
    except Exception:
        p_value = None
    return {
        "status": "completed_asymptotic" if p_value is not None else "completed_statistic_p_value_unavailable",
        "n_blocks": len(matrix),
        "method_count": k,
        "degrees_of_freedom": k - 1,
        "statistic": float(statistic),
        "p_value": p_value,
        "formula": "(k-1)*(k*sum(C_j^2)-T^2)/(k*T-sum(R_i^2))",
    }


def _mcnemar_exact(left_pass: Sequence[int], right_pass: Sequence[int]) -> Dict[str, Any]:
    b = sum(1 for left, right in zip(left_pass, right_pass) if left == 1 and right == 0)
    c = sum(1 for left, right in zip(left_pass, right_pass) if left == 0 and right == 1)
    n = b + c
    if n == 0:
        return {"status": "not_run_no_discordant_pairs", "b": b, "c": c}
    p_exact = 2 * min(_binom_cdf(min(b, c), n, 0.5), 1 - _binom_cdf(min(b, c) - 1, n, 0.5))
    return {"status": "completed_exact_binomial", "b": b, "c": c, "p_value": min(1.0, p_exact)}


def bootstrap_ci(values: Sequence[float], *, iterations: int = 1000, seed: int = 20260705) -> Tuple[float | None, float | None]:
    clean = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if not clean:
        return None, None
    if len(clean) == 1:
        return clean[0], clean[0]
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        sample = [rng.choice(clean) for _ in clean]
        estimates.append(mean(sample))
    estimates.sort()
    low = estimates[int(0.025 * (iterations - 1))]
    high = estimates[int(0.975 * (iterations - 1))]
    return low, high


def rank_biserial_from_differences(differences: Sequence[float]) -> float | None:
    """Return matched-pairs rank-biserial correlation.

    Absolute non-zero differences are ranked with average ranks for ties. The
    effect is `(positive rank sum - negative rank sum) / total rank sum`, so a
    positive value means the right-hand method tends to score higher.
    """

    non_zero = [float(diff) for diff in differences if float(diff) != 0.0]
    if not non_zero:
        return None
    ordered = sorted(enumerate(non_zero), key=lambda item: abs(item[1]))
    ranks = [0.0] * len(non_zero)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        magnitude = abs(ordered[cursor][1])
        while end < len(ordered) and abs(ordered[end][1]) == magnitude:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        for position in range(cursor, end):
            ranks[ordered[position][0]] = average_rank
        cursor = end
    positive_ranks = sum(rank for rank, diff in zip(ranks, non_zero) if diff > 0)
    negative_ranks = sum(rank for rank, diff in zip(ranks, non_zero) if diff < 0)
    denominator = positive_ranks + negative_ranks
    return (positive_ranks - negative_ranks) / denominator if denominator else None


def sign_dominance_from_differences(differences: Sequence[float]) -> float | None:
    """Return the unranked sign-count dominance as a separate diagnostic."""

    non_zero = [float(diff) for diff in differences if float(diff) != 0.0]
    if not non_zero:
        return None
    positives = sum(1 for diff in non_zero if diff > 0)
    negatives = sum(1 for diff in non_zero if diff < 0)
    return (positives - negatives) / len(non_zero)


def _binom_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    total = 0.0
    for i in range(0, k + 1):
        total += math.comb(n, i) * (p**i) * ((1 - p) ** (n - i))
    return total


def _safe_mean(values: Sequence[float]) -> float | None:
    return mean(values) if values else None


def _safe_median(values: Sequence[float]) -> float | None:
    return median(values) if values else None


def _safe_pstdev(values: Sequence[float]) -> float | None:
    return pstdev(values) if len(values) > 1 else 0.0 if values else None
