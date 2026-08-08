"""Paper-ready 120-case sampling plan for PSQ-SCO ontology evaluation."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from config import AGE_GROUPS, CHANNELS, ROLES, STAGE_BY_ID, VARIANTS, build_generation_seed

PAPER_120_CASE_SET_ID = "psq_sco_paper_120"
FULL_1350_CASE_SET_ID = "psq_full_1350"

DIFFICULTY_ANCHORS = [
    (
        "low_foundational",
        "BEGINNER_INTRODUCTORY",
        "Low difficulty anchor: explicit cues, foundational recognition, high scaffolding.",
    ),
    (
        "medium_applied",
        "INTERMEDIATE_DEVELOPING",
        "Medium difficulty anchor: multiple cues, applied comparison, moderate ambiguity.",
    ),
    (
        "high_expert",
        "EXPERT_ADVANCED",
        "High difficulty anchor: subtle cues, strategic reflection, low explicit scaffolding.",
    ),
]

REPETITION_STAGE_ROTATION = [
    "BEGINNER_DEVELOPING",
    "BEGINNER_ADVANCED",
    "INTERMEDIATE_INTRODUCTORY",
    "INTERMEDIATE_ADVANCED",
    "EXPERT_INTRODUCTORY",
    "EXPERT_DEVELOPING",
]

CASE_SET_RATIONALE = (
    "The 120-case set is designed for paper evaluation of PSQ-SCO against the prompt+RAG baseline. "
    "It uses 30 base groups from 3 channels x 2 variants x 5 roles. Each group is tested at three "
    "difficulty anchors, giving 90 cases. One balanced repetition is added per group, giving 30 more "
    "cases and a total of 120. The repetition is not random duplication: it rotates through the six "
    "non-anchor stages and all five age groups so the sample can test stability, age suitability, and "
    "non-anchor stage behavior without expanding to the full 1,350-slot scenario space."
)

FULL_1350_RATIONALE = (
    "The full 1,350-case set enumerates every PersonaShield Quest scenario slot for one "
    "retrieval mode and language mode: 5 roles x 9 macro/micro stages x 5 age groups x "
    "3 channels x 2 variants. It is used when the researcher wants exhaustive coverage "
    "instead of the smaller 120-case paper sample."
)


@dataclass(frozen=True)
class PaperCase:
    """One frozen case definition used in both generation modes."""

    case_id: str
    case_set_id: str
    group_id: str
    group_index: int
    case_index: int
    role: str
    channel: str
    variant: str
    difficulty_condition: str
    stage_id: str
    macro_stage: str
    micro_stage: str
    stage_index: int
    difficulty_band: str
    age_group_code: str
    age_group_label: str
    retrieval_mode: str
    language_mode: str
    modes_to_compare: List[str]
    rationale: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def build_seed(self) -> Any:
        return build_generation_seed(
            self.role,
            self.stage_id,
            self.age_group_code,
            self.retrieval_mode,
            language_mode=self.language_mode,
        )


def generation_capacity(model_count: int = 1, mode_count: int = 1, retrieval_mode_count: int = 1) -> Dict[str, int]:
    """Return scenario-slot capacity for the configured PersonaShield space."""

    per_retrieval_mode = len(ROLES) * len(STAGE_BY_ID) * len(AGE_GROUPS) * len(CHANNELS) * len(VARIANTS)
    return {
        "roles": len(ROLES),
        "stages": len(STAGE_BY_ID),
        "age_groups": len(AGE_GROUPS),
        "channels": len(CHANNELS),
        "variants": len(VARIANTS),
        "per_model_per_retrieval_mode_per_generation_mode": per_retrieval_mode,
        "with_requested_retrieval_modes": per_retrieval_mode * retrieval_mode_count,
        "with_requested_modes": per_retrieval_mode * retrieval_mode_count * mode_count,
        "with_requested_models": per_retrieval_mode * retrieval_mode_count * mode_count * model_count,
    }


def build_paper_120_cases(
    *,
    retrieval_mode: str = "ENGLISH_GLOBAL",
    language_mode: str = "en",
) -> List[PaperCase]:
    """Build the deterministic 120-case ontology evaluation set."""

    cases: List[PaperCase] = []
    age_codes = [item["age_group_code"] for item in AGE_GROUPS]
    age_labels = {item["age_group_code"]: item["age_group_label"] for item in AGE_GROUPS}
    group_index = 0
    for channel in CHANNELS:
        for variant in VARIANTS:
            for role in ROLES:
                group_index += 1
                group_id = f"G{group_index:02d}_{role}_{channel}_{variant}"
                stage_plan = list(DIFFICULTY_ANCHORS)
                repeated_stage = REPETITION_STAGE_ROTATION[(group_index - 1) % len(REPETITION_STAGE_ROTATION)]
                stage_plan.append(
                    (
                        "balanced_repetition",
                        repeated_stage,
                        "Balanced repetition: one additional matched case per base group to test stability, age rotation, and non-anchor stage behavior.",
                    )
                )
                for condition_index, (difficulty_condition, stage_id, rationale) in enumerate(stage_plan):
                    case_number = len(cases) + 1
                    age_group_code = age_codes[((group_index - 1) + condition_index) % len(age_codes)]
                    stage = STAGE_BY_ID[stage_id]
                    cases.append(
                        PaperCase(
                            case_id=f"PSQ-SCO-120-{case_number:03d}",
                            case_set_id=PAPER_120_CASE_SET_ID,
                            group_id=group_id,
                            group_index=group_index,
                            case_index=case_number,
                            role=role,
                            channel=channel,
                            variant=variant,
                            difficulty_condition=difficulty_condition,
                            stage_id=stage_id,
                            macro_stage=stage["macro_stage"],
                            micro_stage=stage["micro_stage"],
                            stage_index=int(stage["index"]),
                            difficulty_band=stage["difficulty_band"],
                            age_group_code=age_group_code,
                            age_group_label=age_labels[age_group_code],
                            retrieval_mode=retrieval_mode,
                            language_mode=language_mode,
                            modes_to_compare=["prompt_rag", "ontology_prompt_rag"],
                            rationale=rationale,
                        )
                    )
    return cases


def build_all_1350_cases(
    *,
    retrieval_mode: str = "ENGLISH_GLOBAL",
    language_mode: str = "en",
) -> List[PaperCase]:
    """Build the complete 5 x 9 x 5 x 3 x 2 PersonaShield scenario slot set."""

    cases: List[PaperCase] = []
    age_labels = {item["age_group_code"]: item["age_group_label"] for item in AGE_GROUPS}
    stage_ids = sorted(STAGE_BY_ID, key=lambda stage_id: int(STAGE_BY_ID[stage_id]["index"]))
    for role in ROLES:
        for stage_id in stage_ids:
            stage = STAGE_BY_ID[stage_id]
            for age_group in AGE_GROUPS:
                age_group_code = age_group["age_group_code"]
                for channel in CHANNELS:
                    for variant in VARIANTS:
                        case_number = len(cases) + 1
                        group_id = f"FULL_{role}_{stage_id}_{age_group_code}_{channel}_{variant}"
                        cases.append(
                            PaperCase(
                                case_id=f"PSQ-FULL-1350-{case_number:04d}",
                                case_set_id=FULL_1350_CASE_SET_ID,
                                group_id=group_id,
                                group_index=case_number,
                                case_index=case_number,
                                role=role,
                                channel=channel,
                                variant=variant,
                                difficulty_condition="full_factorial",
                                stage_id=stage_id,
                                macro_stage=stage["macro_stage"],
                                micro_stage=stage["micro_stage"],
                                stage_index=int(stage["index"]),
                                difficulty_band=stage["difficulty_band"],
                                age_group_code=age_group_code,
                                age_group_label=age_labels[age_group_code],
                                retrieval_mode=retrieval_mode,
                                language_mode=language_mode,
                                modes_to_compare=["prompt_rag", "ontology_prompt_rag"],
                                rationale=FULL_1350_RATIONALE,
                            )
                        )
    return cases


def case_set_summary(cases: Sequence[PaperCase], modes: Sequence[str] | None = None) -> Dict[str, Any]:
    """Summarize a paper case set for reports and CLI output."""

    def count_by(field: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for case in cases:
            value = str(getattr(case, field))
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    case_set_id = cases[0].case_set_id if cases else PAPER_120_CASE_SET_ID
    modes_to_compare = list(modes) if modes is not None else ["prompt_rag", "ontology_prompt_rag"]
    base = {
        "case_set_id": case_set_id,
        "case_count": len(cases),
        "modes_to_compare": modes_to_compare,
        "outputs_for_selected_modes": len(cases) * len(modes_to_compare),
        "outputs_when_mode_both": len(cases) * 2,
        "outputs_when_mode_three_mode": len(cases) * 3,
        "counts_by_role": count_by("role"),
        "counts_by_channel": count_by("channel"),
        "counts_by_variant": count_by("variant"),
        "counts_by_difficulty_condition": count_by("difficulty_condition"),
        "counts_by_age_group": count_by("age_group_code"),
        "counts_by_stage": count_by("stage_id"),
    }
    if case_set_id == FULL_1350_CASE_SET_ID:
        return {
            **base,
            "rationale": FULL_1350_RATIONALE,
            "total_formula": "5 roles x 9 stages x 5 age groups x 3 channels x 2 variants = 1,350 cases",
            "outputs_when_mode_prompt_rag": len(cases),
            "outputs_when_mode_ontology_prompt_rag": len(cases),
            "outputs_when_mode_ontology_text_rag": len(cases),
            "outputs_when_mode_prompt_only": len(cases),
        }
    if case_set_id != PAPER_120_CASE_SET_ID:
        return {
            **base,
            "rationale": cases[0].rationale if cases else "Custom scenario-generation case set.",
            "total_formula": f"{len(cases)} selected case(s)",
        }
    return {
        **base,
        "rationale": CASE_SET_RATIONALE,
        "base_group_formula": "3 channels x 2 variants x 5 roles = 30 base groups",
        "difficulty_formula": "30 base groups x 3 difficulty anchors = 90 cases",
        "balanced_repetition_formula": "30 base groups x 1 balanced repetition = 30 cases",
        "total_formula": "90 + 30 = 120 cases",
    }


def export_case_manifest(
    cases: Sequence[PaperCase],
    json_path: Path,
    csv_path: Path,
    modes: Sequence[str] | None = None,
) -> None:
    """Export case definitions as JSON and CSV."""

    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    modes_to_compare = list(modes) if modes is not None else None
    rows = []
    for case in cases:
        row = case.as_dict()
        if modes_to_compare is not None:
            row["modes_to_compare"] = modes_to_compare
        rows.append(row)
    payload = {
        "summary": case_set_summary(cases, modes=modes),
        "cases": rows,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not rows:
        csv_path.write_text("", encoding="utf-8")
        return
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
