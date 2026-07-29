
"""
PersonaShield Quest — Game System Config Helpers (v4.1)
=======================================================
Formal placement, training-loop, mastery-loop, and stage-transition logic.
This file does not run the game itself; it exports the rules the game can consume.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import (
    FULL_PATH_FORMULA,
    MASTERY_LOOP_POLICY,
    NEXT_STAGE_MAP,
    ORDERED_STAGE_IDS,
    PLACEMENT_STAGE_BANDS,
    PLACEMENT_TEST_QUESTIONS,
    PREV_STAGE_MAP,
    REGRESSION_POLICY,
    TRAINING_LOOP_POLICY,
)
from schemas import (
    GameSystemConfig,
    LoopGate,
    LoopPolicy,
    PlacementOption,
    PlacementQuestion,
    PlacementStageBand,
    PlacementTestConfig,
)


def _placement_config() -> PlacementTestConfig:
    return PlacementTestConfig(
        questions=[
            PlacementQuestion(
                question_id=q["question_id"],
                prompt=q["prompt"],
                dimension=q["dimension"],
                options=[PlacementOption(**opt) for opt in q["options"]],
            )
            for q in PLACEMENT_TEST_QUESTIONS
        ],
        stage_bands=[PlacementStageBand(**band) for band in PLACEMENT_STAGE_BANDS],
        scoring_note=(
            "Each selected answer contributes points. The total placement score determines the recommended starting stage."
        ),
    )


def _loop_policy(data: Dict[str, Any]) -> LoopPolicy:
    return LoopPolicy(
        loop_name=data["loop_name"],
        window_scenarios=data["window_scenarios"],
        goal=data["goal"],
        promotion_gate=LoopGate(**data["promotion_gate"]),
        failure_response=data.get("failure_response", {}),
        completion_rule=data.get("completion_rule"),
    )


def build_game_system_config() -> GameSystemConfig:
    return GameSystemConfig(
        placement_test=_placement_config(),
        training_loop=_loop_policy(TRAINING_LOOP_POLICY),
        mastery_loop=_loop_policy(MASTERY_LOOP_POLICY),
        regression_policy=REGRESSION_POLICY,
        stage_order=ORDERED_STAGE_IDS,
        next_stage_map=NEXT_STAGE_MAP,
        previous_stage_map=PREV_STAGE_MAP,
        path_formula=FULL_PATH_FORMULA,
    )


def recommend_start_stage(total_score: int) -> str:
    for band in PLACEMENT_STAGE_BANDS:
        if band["min_score"] <= total_score <= band["max_score"]:
            return band["stage_id"]
    return PLACEMENT_STAGE_BANDS[0]["stage_id"]


def score_placement_answers(answer_points: List[int]) -> Dict[str, Any]:
    total_score = sum(max(0, int(p)) for p in answer_points)
    return {
        "total_score": total_score,
        "recommended_stage_id": recommend_start_stage(total_score),
        "max_possible_score": sum(max(opt["points"] for opt in q["options"]) for q in PLACEMENT_TEST_QUESTIONS),
    }


def next_stage(stage_id: str) -> Optional[str]:
    return NEXT_STAGE_MAP.get(stage_id)


def previous_stage(stage_id: str) -> Optional[str]:
    return PREV_STAGE_MAP.get(stage_id)


def evaluate_stage_window(
    current_stage_id: str,
    metrics: Dict[str, float],
    *,
    in_mastery_loop: bool,
    consecutive_failures: int = 0,
) -> Dict[str, Any]:
    """
    Returns a transition recommendation the game core can interpret.

    Expected metrics keys:
      accuracy, behavior, speed, safe_choice_rate
    """
    loop_policy = MASTERY_LOOP_POLICY if in_mastery_loop else TRAINING_LOOP_POLICY
    gate = loop_policy["promotion_gate"]

    passed = (
        metrics.get("accuracy", 0.0) >= gate["accuracy_min"]
        and metrics.get("behavior", 0.0) >= gate["behavior_min"]
        and metrics.get("speed", 0.0) >= gate["speed_min"]
        and metrics.get("safe_choice_rate", 0.0) >= gate["safe_choice_rate_min"]
    )

    if passed:
        if in_mastery_loop:
            return {
                "result": "promote",
                "next_stage_id": next_stage(current_stage_id),
                "complete_training": next_stage(current_stage_id) is None,
                "loop_name": loop_policy["loop_name"],
                "reason": "Mastery loop passed.",
            }
        return {
            "result": "enter_mastery_loop",
            "next_stage_id": current_stage_id,
            "complete_training": False,
            "loop_name": loop_policy["loop_name"],
            "reason": "Training loop passed; learner should attempt mastery loop.",
        }

    # fail path
    if consecutive_failures + 1 >= REGRESSION_POLICY["persistent_failure_action"]["windows_required"]:
        prev_stage = previous_stage(current_stage_id)
        return {
            "result": "regress",
            "next_stage_id": prev_stage or current_stage_id,
            "complete_training": False,
            "loop_name": loop_policy["loop_name"],
            "reason": "Persistent failure triggered regression policy.",
            "regression_reason": "persistent_failure",
        }

    return {
        "result": "repeat_training_loop",
        "next_stage_id": current_stage_id,
        "complete_training": False,
        "loop_name": TRAINING_LOOP_POLICY["loop_name"],
        "reason": "Single weak window: repeat with more support and clearer cues.",
        "regression_reason": "single_window_support",
    }
