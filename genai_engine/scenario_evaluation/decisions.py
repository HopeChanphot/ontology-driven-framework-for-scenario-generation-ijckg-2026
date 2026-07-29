"""Final decision state machine for PersonaShield Quest scenario validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Mapping, Optional

from .weights import DEFAULT_BASELINE_WEIGHTS, PCUE_CRITERIA, validate_weights


ACCEPTED = "ACCEPTED"
MINOR_REVISION = "MINOR_REVISION"
MAJOR_REVISION = "MAJOR_REVISION"
REJECT_REGENERATE = "REJECT_REGENERATE"
NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"

DECISION_ACTIONS = {
    ACCEPTED: "Deploy scenario to game. No revision needed.",
    MINOR_REVISION: "Scenario is usable after light targeted revision. Re-evaluate after one revision pass.",
    MAJOR_REVISION: "Scenario requires significant rewrite. Human review and ontology-guided regeneration are recommended.",
    REJECT_REGENERATE: "Discard scenario and regenerate with stronger ontology constraints, a different seed, or a different generator model.",
}

DECISION_SEVERITY = {
    ACCEPTED: 0,
    MINOR_REVISION: 1,
    MAJOR_REVISION: 2,
    REJECT_REGENERATE: 3,
}


@dataclass(frozen=True)
class DecisionResult:
    """Final scenario validation decision and its audit metadata."""

    final_weighted_score: float
    final_decision: str
    decision_action: str
    veto_applied: bool
    veto_reason: Optional[str]
    needs_human_review: bool
    human_review_reason: Optional[str]
    revision_loop_escalated: bool
    revision_loop_reason: Optional[str]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def weighted_score(
    criterion_scores: Mapping[str, float],
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Compute FWS = w_P*P + w_C*C + w_U*U + w_E*E."""

    validated_weights = validate_weights(weights or DEFAULT_BASELINE_WEIGHTS)
    missing = [criterion for criterion in PCUE_CRITERIA if criterion not in criterion_scores]
    if missing:
        raise ValueError("Missing PCUE criterion score(s): " + ", ".join(missing))
    return sum(float(criterion_scores[criterion]) * validated_weights[criterion] for criterion in PCUE_CRITERIA)


def base_decision_from_score(final_weighted_score: float) -> str:
    """Apply the four-state decision thresholds before vetoes."""

    if final_weighted_score >= 0.75:
        return ACCEPTED
    if final_weighted_score >= 0.60:
        return MINOR_REVISION
    if final_weighted_score >= 0.40:
        return MAJOR_REVISION
    return REJECT_REGENERATE


def _at_least(decision: str, minimum: str) -> str:
    if DECISION_SEVERITY[decision] >= DECISION_SEVERITY[minimum]:
        return decision
    return minimum


def _apply_revision_loop(
    decision: str,
    revision_count: int,
) -> tuple[str, bool, Optional[str]]:
    if decision == MINOR_REVISION and revision_count > 2:
        return (
            MAJOR_REVISION,
            True,
            "MINOR_REVISION repeated more than 2 times; escalated to MAJOR_REVISION.",
        )
    if decision == MAJOR_REVISION and revision_count > 1:
        return (
            REJECT_REGENERATE,
            True,
            "MAJOR_REVISION repeated more than 1 time; escalated to REJECT_REGENERATE.",
        )
    return decision, False, None


def determine_final_decision(
    criterion_scores: Mapping[str, float],
    weights: Optional[Mapping[str, float]] = None,
    revision_count: int = 0,
    judge_disagreement: bool = False,
) -> DecisionResult:
    """Determine final validation state with vetoes and loop control."""

    fws = weighted_score(criterion_scores, weights)
    decision = base_decision_from_score(fws)
    veto_applied = False
    veto_reason: Optional[str] = None

    pedagogy = float(criterion_scores["pedagogical_quality"])
    cyber = float(criterion_scores["cybersecurity_realism"])
    usability = float(criterion_scores["usability_game_clarity"])
    ethics = float(criterion_scores["ethical_safety"])

    if ethics <= 0.25:
        decision = REJECT_REGENERATE
        veto_applied = True
        veto_reason = "Ethical Safety <= 0.25; unsafe scenarios must be regenerated."
    elif pedagogy <= 0.25:
        decision = _at_least(decision, MAJOR_REVISION)
        veto_applied = True
        veto_reason = "Pedagogical Quality <= 0.25; scenario cannot be accepted without major instructional rewrite."
    elif cyber <= 0.25:
        decision = _at_least(decision, MAJOR_REVISION)
        veto_applied = True
        veto_reason = "Cybersecurity Realism <= 0.25; scenario cannot be accepted without major realism repair."
    elif usability <= 0.25:
        minimum = MINOR_REVISION if fws >= 0.60 else MAJOR_REVISION
        decision = _at_least(decision, minimum)
        veto_applied = True
        veto_reason = "Usability / Game Clarity <= 0.25; scenario cannot be accepted as-is."

    needs_human_review = bool(judge_disagreement)
    human_review_reason = None
    if judge_disagreement:
        human_review_reason = "At least one top-level criterion has high judge disagreement (max-min >= 0.50)."
        if decision == ACCEPTED:
            decision = MINOR_REVISION

    decision, revision_escalated, revision_reason = _apply_revision_loop(decision, revision_count)

    return DecisionResult(
        final_weighted_score=round(fws, 4),
        final_decision=decision,
        decision_action=DECISION_ACTIONS[decision],
        veto_applied=veto_applied,
        veto_reason=veto_reason,
        needs_human_review=needs_human_review,
        human_review_reason=human_review_reason,
        revision_loop_escalated=revision_escalated,
        revision_loop_reason=revision_reason,
    )
