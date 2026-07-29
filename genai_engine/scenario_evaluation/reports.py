"""Research report and judge-score exports for scenario evaluation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

from .judges import JudgeConfig
from .qualifiers import qualify_score


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def _count_and_percent(df: pd.DataFrame, column: str, value: Any) -> Dict[str, Any]:
    total = len(df)
    count = int((df[column] == value).sum()) if column in df else 0
    return {"count": count, "percent": round(count / total * 100, 2) if total else 0.0}


def _distribution(df: pd.DataFrame, field: str) -> List[Dict[str, Any]]:
    if df.empty or field not in df or "final_decision" not in df:
        return []
    grouped = (
        df.groupby([field, "final_decision"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values([field, "final_decision"])
    )
    return grouped.to_dict(orient="records")


def build_research_report(
    df: pd.DataFrame,
    judge_profile: str,
    judges: Iterable[JudgeConfig],
    weighting_metadata: Mapping[str, Any],
    paid_judges_enabled: bool,
    hardware_warning_messages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a reviewer-facing report object with required sections."""

    judges = list(judges)
    total = len(df)
    decisions = {
        "accepted": _count_and_percent(df, "final_decision", "ACCEPTED"),
        "minor_revision": _count_and_percent(df, "final_decision", "MINOR_REVISION"),
        "major_revision": _count_and_percent(df, "final_decision", "MAJOR_REVISION"),
        "reject_regenerate": _count_and_percent(df, "final_decision", "REJECT_REGENERATE"),
    }
    needs_review = int(df["needs_human_review"].sum()) if "needs_human_review" in df and total else 0
    veto_count = int(df["veto_applied"].sum()) if "veto_applied" in df and total else 0

    criterion_columns = {
        "pedagogical_quality": "pedagogical_quality_score",
        "cybersecurity_realism": "cybersecurity_realism_pc_score",
        "usability_game_clarity": "usability_game_clarity_score",
        "ethical_safety": "ethical_safety_score",
    }
    mean_scores = {}
    for criterion, column in criterion_columns.items():
        score = float(df[column].mean()) if total and column in df else 0.0
        mean_scores[criterion] = {
            "mean": round(score, 4),
            "qualifier": qualify_score(score, criterion).as_dict(),
        }

    failure_reasons = Counter()
    failed_criteria = Counter()
    low_ped_high_ethics = 0
    for _, row in df.iterrows():
        if row.get("final_decision") != "ACCEPTED":
            failed_criteria[str(row.get("weakest_criterion", ""))] += 1
            for item in _loads(row.get("revision_guidance"), []):
                failure_reasons[str(item)] += 1
        if float(row.get("pedagogical_quality_score", 0.0)) < 0.70 and float(row.get("ethical_safety_score", 0.0)) >= 0.85:
            low_ped_high_ethics += 1

    action_rows = []
    if total:
        for _, row in df[df["final_decision"] != "ACCEPTED"].iterrows():
            action_rows.append(
                {
                    "scenario_id": row.get("scenario_id"),
                    "FWS": row.get("final_weighted_score"),
                    "decision": row.get("final_decision"),
                    "weakest_criterion": row.get("weakest_criterion"),
                    "qualifier": row.get("weakest_criterion_qualifier"),
                    "required_action": row.get("decision_action"),
                    "generated_revision_guidance": _loads(row.get("revision_guidance"), []),
                }
            )

    llm_judge_section = {
        "judge_profile_used": judge_profile,
        "paid_judge_enabled": paid_judges_enabled,
        "hardware_warnings": hardware_warning_messages or [],
        "accessibility_statement": "The default evaluation configuration uses open-weight judges to reduce cost barriers for educational users.",
        "judges": [
            {
                **judge.as_dict(),
                "model_size_class": judge.model_size_class,
                "judge_model_type": judge.judge_model_type,
                "requires_api_key": judge.requires_api_key,
            }
            for judge in judges
        ],
    }

    report = {
        "executive_summary": {
            "total_scenarios_evaluated": total,
            **decisions,
            "needs_human_review": {
                "count": needs_review,
                "percent": round(needs_review / total * 100, 2) if total else 0.0,
            },
            "veto_applied_scenarios": veto_count,
        },
        "mean_scores_by_criterion": mean_scores,
        "distribution_by_classification": {
            "role": _distribution(df, "role"),
            "macro_stage": _distribution(df, "macro_stage"),
            "micro_stage": _distribution(df, "micro_stage"),
            "age_group": _distribution(df, "age_group"),
            "channel": _distribution(df, "channel"),
            "variant": _distribution(df, "variant"),
        },
        "failure_analysis": {
            "top_failed_criteria": failed_criteria.most_common(10),
            "most_common_revision_reasons": failure_reasons.most_common(20),
            "scenarios_blocked_by_veto_rule": veto_count,
            "scenarios_rejected_for_ethical_safety": int(
                df["veto_reason"].fillna("").str.contains("Ethical Safety").sum()
            )
            if total and "veto_reason" in df
            else 0,
            "scenarios_rejected_for_cybersecurity_realism": int(
                df["veto_reason"].fillna("").str.contains("Cybersecurity Realism").sum()
            )
            if total and "veto_reason" in df
            else 0,
            "low_pedagogy_but_high_ethical_safety": low_ped_high_ethics,
            "high_judge_disagreement_scenarios": int(df["judge_disagreement"].sum())
            if total and "judge_disagreement" in df
            else 0,
        },
        "actionable_revision_table": action_rows,
        "weighting_method": dict(weighting_metadata),
        "llm_judge_section": llm_judge_section,
        "research_interpretation": (
            "Fixed weights are Phase 1 baseline. Learned weights are Phase 2 empirical improvement. "
            "A Personalized Calibration Network is the Phase 3 future direction. Qualifier intervals make "
            "scores actionable. The Accept state solves validation-loop termination. Criterion-level vetoes "
            "prevent high overall scores from hiding critical failures. Open-weight judges reduce cost "
            "barriers for educational users, and low-resource profiles allow preliminary local testing."
        ),
    }
    return report


def report_to_markdown(report: Mapping[str, Any]) -> str:
    """Render the research report as compact Markdown."""

    summary = report["executive_summary"]
    mean_scores = report["mean_scores_by_criterion"]
    lines = [
        "# PersonaShield Quest Scenario Evaluation Report",
        "",
        "## Executive Summary",
        f"Total scenarios evaluated: {summary['total_scenarios_evaluated']}",
        f"Accepted: {summary['accepted']['count']} ({summary['accepted']['percent']}%)",
        f"Minor Revision: {summary['minor_revision']['count']} ({summary['minor_revision']['percent']}%)",
        f"Major Revision: {summary['major_revision']['count']} ({summary['major_revision']['percent']}%)",
        f"Reject/Regenerate: {summary['reject_regenerate']['count']} ({summary['reject_regenerate']['percent']}%)",
        f"Needs Human Review: {summary['needs_human_review']['count']} ({summary['needs_human_review']['percent']}%)",
        f"Veto-applied scenarios: {summary['veto_applied_scenarios']}",
        "",
        "## Mean Scores By Criterion",
    ]
    labels = {
        "pedagogical_quality": "Pedagogical Quality",
        "cybersecurity_realism": "Cybersecurity Realism",
        "usability_game_clarity": "Usability / Game Clarity",
        "ethical_safety": "Ethical Safety",
    }
    for criterion, label in labels.items():
        item = mean_scores[criterion]
        lines.append(f"- {label}: {item['mean']:.4f} ({item['qualifier']['qualifier']})")
    lines.extend(
        [
            "",
            "## Weighting Method",
            f"Phase: {report['weighting_method'].get('weighting_phase', report['weighting_method'].get('phase'))}",
            f"Weights used: `{json.dumps(report['weighting_method'].get('weights_used', report['weighting_method'].get('normalized_weights', {})))}`",
            "",
            "## LLM Judges",
            "The Layer 2 evaluation used open-weight / open-access judge profiles. No paid proprietary API is required for the primary validation pipeline.",
        ]
    )
    for judge in report["llm_judge_section"]["judges"]:
        lines.append(
            f"- {judge['judge_id']}: {judge['model_name']} ({judge['provider_type']}, {judge['cost_mode']}, {judge['model_size_class']})"
        )
    lines.extend(
        [
            "",
            "## Research Interpretation",
            str(report["research_interpretation"]),
        ]
    )
    return "\n".join(lines) + "\n"


def write_research_report(report: Mapping[str, Any], out_dir: Path) -> Dict[str, Path]:
    out_dir = Path(out_dir)
    json_path = out_dir / "layer1_layer2_research_report.json"
    md_path = out_dir / "layer1_layer2_research_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report_to_markdown(report), encoding="utf-8")
    return {"research_report_json": json_path, "research_report_md": md_path}


def export_judge_score_tables(df: pd.DataFrame, out_dir: Path) -> Dict[str, Path]:
    """Export judge scores in long and wide forms for agreement statistics."""

    long_rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        score_rows = _loads(row.get("judge_scores_json"), [])
        for judge_score in score_rows:
            normalized = judge_score.get("normalized_scores", {})
            raw = judge_score.get("raw_scores", {})
            for criterion, normalized_score in normalized.items():
                long_rows.append(
                    {
                        "scenario_id": row.get("scenario_id"),
                        "judge_id": judge_score.get("judge_id"),
                        "judge_model": judge_score.get("judge_model"),
                        "model_family": judge_score.get("model_family"),
                        "provider_type": judge_score.get("provider_type"),
                        "role": judge_score.get("role"),
                        "macro_stage": row.get("macro_stage"),
                        "micro_stage": row.get("micro_stage"),
                        "age_group": row.get("age_group"),
                        "channel": row.get("channel"),
                        "variant": row.get("variant"),
                        "criterion": criterion,
                        "raw_score": raw.get(criterion),
                        "normalized_score": normalized_score,
                        "qualifier": qualify_score(float(normalized_score), criterion).qualifier,
                        "final_weighted_score": row.get("final_weighted_score"),
                        "final_decision": row.get("final_decision"),
                    }
                )

    long_path = Path(out_dir) / "judge_scores_long.csv"
    wide_path = Path(out_dir) / "judge_scores_wide.csv"
    long_df = pd.DataFrame(long_rows)
    long_df.to_csv(long_path, index=False, encoding="utf-8-sig")
    if long_df.empty:
        pd.DataFrame().to_csv(wide_path, index=False, encoding="utf-8-sig")
    else:
        wide_df = long_df.pivot_table(
            index=["scenario_id", "macro_stage", "micro_stage", "age_group", "channel", "variant", "final_weighted_score", "final_decision"],
            columns=["judge_id", "criterion"],
            values="normalized_score",
            aggfunc="first",
        )
        wide_df.columns = [f"{judge}_{criterion}" for judge, criterion in wide_df.columns]
        wide_df.reset_index().to_csv(wide_path, index=False, encoding="utf-8-sig")
    return {"judge_scores_long_csv": long_path, "judge_scores_wide_csv": wide_path}
