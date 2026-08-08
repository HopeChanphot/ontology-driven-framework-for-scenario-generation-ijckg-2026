"""Consensus scoring for multiple PersonaShield Quest LLM judges."""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .judges import JudgeConfig, detect_self_judge_risk
from .qualifiers import qualify_score
from .weights import PCUE_CRITERIA


@dataclass(frozen=True)
class JudgeScore:
    judge_id: str
    judge_model: str
    model_family: str
    provider_type: str
    local_runtime: str
    role: str
    raw_scores: Dict[str, float]
    normalized_scores: Dict[str, float]
    explanation: str = ""
    confidence: Optional[float] = None
    self_judge_risk: bool = False
    metadata: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConsensusResult:
    criterion_stats: Dict[str, Dict[str, Any]]
    aggregated_scores: Dict[str, float]
    judge_disagreement: bool
    high_disagreement_criteria: List[str]
    judge_scores: List[JudgeScore]
    self_judge_risk: bool

    def as_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["judge_scores"] = [score.as_dict() for score in self.judge_scores]
        return result


def aggregate_judge_scores(judge_scores: Iterable[JudgeScore]) -> ConsensusResult:
    """Aggregate multiple judge scores into criterion-level statistics."""

    scores = list(judge_scores)
    if not scores:
        raise ValueError("At least one judge score is required for consensus aggregation.")

    criterion_stats: Dict[str, Dict[str, Any]] = {}
    aggregated: Dict[str, float] = {}
    high_disagreement: List[str] = []
    for criterion in PCUE_CRITERIA:
        values = [float(score.normalized_scores.get(criterion, 0.0)) for score in scores]
        low = min(values)
        high = max(values)
        diff = high - low
        flag = diff >= 0.50
        if flag:
            high_disagreement.append(criterion)
        mean_value = statistics.mean(values)
        aggregated[criterion] = round(mean_value, 4)
        criterion_stats[criterion] = {
            "mean": round(mean_value, 4),
            "median": round(statistics.median(values), 4),
            "stdev": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
            "highest": round(high, 4),
            "lowest": round(low, 4),
            "difference": round(diff, 4),
            "high_disagreement": flag,
            "qualifier": qualify_score(mean_value, criterion).as_dict(),
        }

    return ConsensusResult(
        criterion_stats=criterion_stats,
        aggregated_scores=aggregated,
        judge_disagreement=bool(high_disagreement),
        high_disagreement_criteria=high_disagreement,
        judge_scores=scores,
        self_judge_risk=any(score.self_judge_risk for score in scores),
    )


def _normalized_to_likert(score: float) -> int:
    if score >= 0.85:
        return 4
    if score >= 0.70:
        return 3
    if score >= 0.50:
        return 2
    return 1


def proxy_judge_scores_from_layer2(
    layer2_scores: Mapping[str, Any],
    judges: Iterable[JudgeConfig],
    scenario: Mapping[str, Any],
) -> List[JudgeScore]:
    """Create deterministic judge-score records from existing heuristic scores.

    This keeps the default evaluator cost-free while preserving the same
    metadata shape used by live LLM judge runs.
    """

    base = {
        "pedagogical_quality": float(layer2_scores.get("openai_pedagogy_quality_score", 0.0)),
        "cybersecurity_realism": float(layer2_scores.get("cybersecurity_realism_score", 0.0)),
        "usability_game_clarity": float(layer2_scores.get("game_usability_score", 0.0)),
        "ethical_safety": float(layer2_scores.get("safety_score", 0.0)),
    }
    consistency = float(layer2_scores.get("fake_real_consistency_score", 0.0))
    feedback = float(layer2_scores.get("feedback_quality_score", 0.0))
    choice = float(layer2_scores.get("choice_quality_score", 0.0))

    results: List[JudgeScore] = []
    for judge in judges:
        normalized = dict(base)
        role = judge.role.lower()
        if "pedagogy" in role:
            normalized["pedagogical_quality"] = round(
                0.70 * base["pedagogical_quality"] + 0.20 * feedback + 0.10 * choice,
                4,
            )
        elif "cyber" in role:
            normalized["cybersecurity_realism"] = round(
                0.75 * base["cybersecurity_realism"] + 0.25 * consistency,
                4,
            )
        elif "usability" in role or "game" in role:
            normalized["usability_game_clarity"] = round(
                0.80 * base["usability_game_clarity"] + 0.20 * choice,
                4,
            )
        elif "multilingual" in role or "json" in role:
            normalized["usability_game_clarity"] = round(
                0.60 * base["usability_game_clarity"] + 0.20 * base["pedagogical_quality"] + 0.20 * consistency,
                4,
            )
        raw = {criterion: _normalized_to_likert(score) for criterion, score in normalized.items()}
        results.append(
            JudgeScore(
                judge_id=judge.judge_id,
                judge_model=judge.model_name,
                model_family=judge.model_family,
                provider_type=judge.provider_type,
                local_runtime=judge.local_runtime,
                role=judge.role,
                raw_scores=raw,
                normalized_scores=normalized,
                explanation="Deterministic heuristic proxy score; no paid or live API call was made.",
                confidence=None,
                self_judge_risk=detect_self_judge_risk(scenario, judge),
                metadata={
                    "prompt_version": judge.prompt_version,
                    "rubric_version": judge.rubric_version,
                    "temperature": judge.temperature,
                    "seed": judge.seed,
                    "cost_mode": judge.cost_mode,
                    "model_size_class": judge.model_size_class,
                },
            )
        )
    return results
