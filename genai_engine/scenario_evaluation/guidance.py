"""Criterion-specific revision guidance for PersonaShield Quest scenarios."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from .qualifiers import qualify_score


def generate_revision_guidance(
    scenario: Optional[Mapping[str, Any]],
    criterion_scores: Mapping[str, float],
    qualifiers: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> List[str]:
    """Generate actionable, criterion-specific revision guidance."""

    del scenario  # Reserved for future scenario-field-aware guidance.
    guidance: List[str] = []
    p = float(criterion_scores.get("pedagogical_quality", 0.0))
    c = float(criterion_scores.get("cybersecurity_realism", 0.0))
    u = float(criterion_scores.get("usability_game_clarity", 0.0))
    e = float(criterion_scores.get("ethical_safety", 0.0))

    if qualifiers is None:
        qualifiers = {
            key: qualify_score(value, key).as_dict()
            for key, value in criterion_scores.items()
        }

    if p < 0.50:
        guidance.extend(
            [
                "Pedagogical Quality is Poor or Fail: significant rewrite required.",
                "Add or improve an explicit learning_objective.",
                "Add Bloom Level 3+ application/analysis action so the player applies or analyzes knowledge.",
                "Add a consequence layer explaining what happens if the unsafe choice is selected.",
                "Add LO-linked hint_text that directly supports the learning objective.",
                "Improve wrong-choice explanations.",
                "Make correct_action explain the defensive behavior and why it matters.",
                "Ensure at least one player choice requires applying knowledge rather than only recognizing obvious red flags.",
                "Feedback should explicitly name the attack type, red flag, safe indicator, and correct defense.",
            ]
        )
    elif p < 0.70:
        guidance.extend(
            [
                "Pedagogical Quality is Adequate: keep the scenario but revise scaffolding, feedback, and Bloom alignment.",
                "Improve at least one weak choice and make the learning objective more measurable.",
            ]
        )
    elif p < 0.85:
        guidance.append(
            "Pedagogical Quality is Good: only a light edit is needed; add clarity or one extra explanation if missing."
        )
    else:
        guidance.append("Pedagogical Quality is Excellent: no pedagogical revision needed.")

    if c < 0.50:
        guidance.extend(
            [
                "Cybersecurity Realism is weak: strengthen phishing/smishing/vishing plausibility.",
                "Add role-appropriate red flags or safe indicators tied to the selected channel and variant.",
                "Ensure fake/real variant correctness and avoid mixing malicious artifacts into legitimate scenarios.",
                "Make the safe defensive action realistic for the workplace workflow.",
            ]
        )
    elif c < 0.70:
        guidance.append(
            "Cybersecurity Realism is Adequate: revise generic details into concrete role, channel, and workflow cues."
        )

    if u < 0.50:
        guidance.extend(
            [
                "Usability / Game Clarity is weak: clarify the player task, choices, consequences, and next action.",
                "Rewrite confusing choice labels and make feedback concise enough for gameplay.",
                "Check that the scenario fits the game interface and channel presentation.",
            ]
        )
    elif u < 0.70:
        guidance.append(
            "Usability / Game Clarity is Adequate: tighten wording and remove ambiguous or redundant choices."
        )

    if e >= 0.85:
        guidance.append(
            "Ethical Safety achieved an Excellent rating: no ethical revision needed."
        )
    elif e < 0.50:
        guidance.extend(
            [
                "Ethical Safety is weak: remove discriminatory, harmful, or operationally dangerous content.",
                "Reframe the scenario as defensive awareness and avoid step-by-step misuse guidance.",
            ]
        )
    elif e < 0.70:
        guidance.append(
            "Ethical Safety is Adequate: make the defensive framing clearer and remove borderline wording."
        )

    if e >= 0.85 and p < 0.70:
        guidance.append(
            "Ethical Safety is strong, but Pedagogical Quality is weak. This indicates that the scenario is safe but not yet instructionally effective."
        )

    return guidance


def criterion_interpretation(criterion: str, score: float) -> str:
    """Return one-line criterion interpretation for reports."""

    qualifier = qualify_score(score, criterion)
    if criterion == "ethical_safety" and score >= 0.85:
        return (
            "Ethical Safety achieved an Excellent rating, indicating that the scenario avoids "
            "discriminatory wording, harmful operational detail, and unsafe instruction. "
            "No ethical revision is required."
        )
    if criterion == "pedagogical_quality" and score < 0.50:
        return (
            f"Pedagogical Quality = {score:.4f}; Qualifier = {qualifier.qualifier}; "
            "significant rewrite required because learning-objective scaffolding, Bloom alignment, "
            "and feedback are weak."
        )
    return f"{criterion} = {score:.4f}; Qualifier = {qualifier.qualifier}; {qualifier.meaning}"
