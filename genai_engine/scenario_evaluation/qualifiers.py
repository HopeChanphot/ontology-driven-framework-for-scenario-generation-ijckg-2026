"""Qualifier intervals for PersonaShield Quest scenario validation.

The reviewer-facing goal is to convert a normalized score such as 0.4733 into
an interpretable quality label and an actionable default revision action.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class QualifierResult:
    """Human-readable interpretation of a normalized 0..1 score."""

    score: float
    qualifier: str
    marker: str
    interval_min: float
    interval_max: float
    meaning: str
    default_revision_action: str

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


BASE_QUALIFIER_MEANINGS: Dict[str, str] = {
    "EXCELLENT": "Fully meets the criterion. No revision needed.",
    "GOOD": "Meets core expectations with minor gaps. Light edit recommended.",
    "ADEQUATE": "Meets minimum threshold but has notable gaps. Targeted revision recommended.",
    "POOR": "Partially meets the criterion with major gaps. Significant rewrite required.",
    "FAIL": "Does not meet the criterion. Regenerate or discard.",
}

DEFAULT_ACTIONS: Dict[str, str] = {
    "EXCELLENT": "No revision needed.",
    "GOOD": "Light edit recommended.",
    "ADEQUATE": "Targeted revision recommended.",
    "POOR": "Significant rewrite required.",
    "FAIL": "Regenerate or discard.",
}

QUALIFIER_INTERVALS = (
    ("Excellent", "EXCELLENT", 0.85, 1.00),
    ("Good", "GOOD", 0.70, 0.84),
    ("Adequate", "ADEQUATE", 0.50, 0.69),
    ("Poor", "POOR", 0.25, 0.49),
    ("Fail", "FAIL", 0.00, 0.24),
)

CRITERION_SPECIFIC_MEANINGS: Dict[str, Dict[str, str]] = {
    "pedagogical_quality": {
        "EXCELLENT": (
            "Clear learning objective, Bloom-aligned action, scaffolded hint, "
            "consequence feedback, and strong wrong-choice explanation."
        ),
        "GOOD": "Clear learning objective and mostly useful feedback, with minor scaffolding gaps.",
        "ADEQUATE": "A measurable learning objective exists, but scaffolding or Bloom alignment is weak.",
        "POOR": "Weak learning-objective connection, limited scaffolding, and generic feedback.",
        "FAIL": "No discernible learning objective or educational value.",
    },
    "cybersecurity_realism": {
        "EXCELLENT": (
            "Realistic phishing/smishing/vishing behavior, appropriate red flags, "
            "plausible role/channel context, and safe defensive action."
        ),
        "GOOD": "Mostly realistic with minor unrealistic details.",
        "ADEQUATE": "Recognizable attack or legitimate pattern, but some realism is weak or generic.",
        "POOR": "Major realism gaps, implausible context, weak red flags, or weak safe indicators.",
        "FAIL": "Fabricated, incoherent, or incorrect cybersecurity behavior.",
    },
    "usability_game_clarity": {
        "EXCELLENT": "The player can clearly understand the scenario, choices, consequences, and next action.",
        "GOOD": "Minor clarity or wording issues.",
        "ADEQUATE": "Playable, but with multiple clarity issues.",
        "POOR": "Confusing choices, unclear task, or poor interface fit.",
        "FAIL": "Not playable or not understandable.",
    },
    "ethical_safety": {
        "EXCELLENT": "No discriminatory content, no harmful operational guidance, and defensive framing only.",
        "GOOD": "Minor wording issue but safe overall.",
        "ADEQUATE": "Safe but needs clearer defensive framing.",
        "POOR": "Borderline unsafe, biased, or unclear risk framing.",
        "FAIL": "Harmful, discriminatory, or operationally dangerous content.",
    },
}


def _clamp01(score: float) -> float:
    if math.isnan(score) or math.isinf(score):
        return 0.0
    return max(0.0, min(1.0, score))


def _interval_for_score(score: float) -> tuple[str, str, float, float]:
    for qualifier, marker, interval_min, interval_max in QUALIFIER_INTERVALS:
        if interval_min <= score <= interval_max:
            return qualifier, marker, interval_min, interval_max
    return "Fail", "FAIL", 0.00, 0.24


def qualify_score(score: float, criterion: Optional[str] = None) -> QualifierResult:
    """Map a normalized score to a five-level qualifier interval.

    Args:
        score: Normalized score, expected in 0..1. Invalid values are clamped.
        criterion: Optional PCUE criterion key for criterion-specific meaning.

    Returns:
        A QualifierResult with label, machine marker, interval, meaning, and
        default revision action.
    """

    normalized = _clamp01(float(score))
    qualifier, marker, interval_min, interval_max = _interval_for_score(normalized)
    criterion_key = (criterion or "").strip().lower()
    meaning = CRITERION_SPECIFIC_MEANINGS.get(criterion_key, {}).get(
        marker, BASE_QUALIFIER_MEANINGS[marker]
    )
    return QualifierResult(
        score=normalized,
        qualifier=qualifier,
        marker=marker,
        interval_min=interval_min,
        interval_max=interval_max,
        meaning=meaning,
        default_revision_action=DEFAULT_ACTIONS[marker],
    )


def qualify_scores(scores: Dict[str, float]) -> Dict[str, Dict[str, object]]:
    """Qualify a dictionary of criterion scores."""

    return {
        criterion: qualify_score(score, criterion=criterion).as_dict()
        for criterion, score in scores.items()
    }
