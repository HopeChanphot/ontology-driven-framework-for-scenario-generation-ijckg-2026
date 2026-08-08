"""PCUE weighting support for PersonaShield Quest scenario evaluation.

Phase 1 keeps the fixed expert-informed baseline. Phase 2 estimates empirical
weights from play-testing outcome data when enough complete records exist.
Phase 3 is represented as an explicit future-extension interface.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


PCUE_CRITERIA = (
    "pedagogical_quality",
    "cybersecurity_realism",
    "usability_game_clarity",
    "ethical_safety",
)

PCUE_LABELS = {
    "pedagogical_quality": "Pedagogical Quality",
    "cybersecurity_realism": "Cybersecurity Realism",
    "usability_game_clarity": "Usability / Game Clarity",
    "ethical_safety": "Ethical Safety",
}

DEFAULT_BASELINE_WEIGHTS: Dict[str, float] = {
    "pedagogical_quality": 0.40,
    "cybersecurity_realism": 0.35,
    "usability_game_clarity": 0.15,
    "ethical_safety": 0.10,
}

PHASE_1 = "phase_1_fixed_baseline"
PHASE_2 = "phase_2_regression_derived"
PHASE_3 = "phase_3_personalized_calibration_network"

FIELD_ALIASES: Dict[str, Sequence[str]] = {
    "scenario_id": ("scenario_id",),
    "player_id": ("player_id", "anonymized_participant_id", "participant_id"),
    "pre_test_score": ("pre_test_score", "pre_score", "pretest_score"),
    "post_test_score": ("post_test_score", "post_score", "posttest_score"),
    "pedagogical_quality": ("pedagogical_quality", "P score", "P", "p_score"),
    "cybersecurity_realism": ("cybersecurity_realism", "C score", "C", "c_score"),
    "usability_game_clarity": (
        "usability_game_clarity",
        "usability",
        "U score",
        "U",
        "u_score",
    ),
    "ethical_safety": ("ethical_safety", "E score", "E", "e_score"),
}


class WeightConfigError(ValueError):
    """Raised when a PCUE weight configuration is incomplete or invalid."""


@dataclass
class RegressionDataset:
    """Rows that are usable for Phase 2 empirical weight fitting."""

    x: List[List[float]]
    y: List[float]
    valid_rows: int
    excluded_rows: int
    exclusion_reasons: Dict[str, int]


@dataclass
class LearnedWeightResult:
    """Versioned metadata for learned or fallback PCUE weights."""

    phase: str
    sample_size: int
    raw_coefficients: Dict[str, float]
    normalized_weights: Dict[str, float]
    adjusted_r2: Optional[float]
    p_values: Dict[str, Optional[float]]
    date_generated: str
    notes: str
    fallback_used: bool
    fallback_reason: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_weights(weights: Mapping[str, float], tolerance: float = 1e-6) -> Dict[str, float]:
    """Validate that all PCUE weights are present, bounded, and sum to 1.0."""

    if weights is None:
        raise WeightConfigError("Weights are missing.")
    missing = [criterion for criterion in PCUE_CRITERIA if criterion not in weights]
    if missing:
        raise WeightConfigError("Missing PCUE weight(s): " + ", ".join(missing))

    validated: Dict[str, float] = {}
    for criterion in PCUE_CRITERIA:
        try:
            value = float(weights[criterion])
        except (TypeError, ValueError) as exc:
            raise WeightConfigError(f"Weight for {criterion} is not numeric.") from exc
        if value < 0:
            raise WeightConfigError(f"Weight for {criterion} is negative.")
        if value > 1:
            raise WeightConfigError(f"Weight for {criterion} is above 1.")
        validated[criterion] = value

    total = sum(validated.values())
    if abs(total - 1.0) > tolerance:
        raise WeightConfigError(f"PCUE weights must sum to 1.00; found {total:.6f}.")
    return validated


def phase_1_weight_metadata(weights: Optional[Mapping[str, float]] = None) -> Dict[str, Any]:
    """Return report metadata for the fixed baseline weighting phase."""

    validated = validate_weights(weights or DEFAULT_BASELINE_WEIGHTS)
    return {
        "weighting_phase": PHASE_1,
        "weights_used": validated,
        "rationale": "Expert-informed baseline weights used before sufficient play-testing data are available.",
        "learned_weights_used": False,
        "sample_size": None,
        "fallback_reason": None,
    }


def _get(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        if alias in row:
            return row[alias]
    lowered = {str(k).lower(): v for k, v in row.items()}
    for alias in aliases:
        key = alias.lower()
        if key in lowered:
            return lowered[key]
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def normalized_learning_gain(pre_test_score: Any, post_test_score: Any) -> Optional[float]:
    """Compute normalized learning gain, or None when the row is unusable.

    g = (post_test_score - pre_test_score) / (100 - pre_test_score)
    """

    pre = _to_float(pre_test_score)
    post = _to_float(post_test_score)
    if pre is None or post is None:
        return None
    if pre >= 100:
        return None
    return (post - pre) / (100.0 - pre)


def load_playtesting_rows(path: Path) -> List[Dict[str, Any]]:
    """Load Phase 2 play-testing rows from CSV, JSON, or JSONL."""

    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    if path.suffix.lower() == ".jsonl":
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return data["rows"]
    raise ValueError(f"Unsupported play-testing outcome format: {path}")


def build_regression_dataset(rows: Iterable[Mapping[str, Any]]) -> RegressionDataset:
    """Filter play-testing rows down to complete PCUE + learning-gain records."""

    x: List[List[float]] = []
    y: List[float] = []
    reasons: Counter[str] = Counter()

    for row in rows:
        pre = _get(row, FIELD_ALIASES["pre_test_score"])
        post = _get(row, FIELD_ALIASES["post_test_score"])
        gain = normalized_learning_gain(pre, post)
        if gain is None:
            pre_float = _to_float(pre)
            if _to_float(post) is None:
                reasons["missing_post_test_score"] += 1
            elif pre_float is None:
                reasons["missing_pre_test_score"] += 1
            elif pre_float >= 100:
                reasons["pre_test_score_at_or_above_100"] += 1
            else:
                reasons["invalid_learning_gain"] += 1
            continue

        criterion_values: List[float] = []
        missing_pcues = []
        for criterion in PCUE_CRITERIA:
            value = _to_float(_get(row, FIELD_ALIASES[criterion]))
            if value is None:
                missing_pcues.append(criterion)
            else:
                criterion_values.append(max(0.0, min(1.0, value)))
        if missing_pcues:
            reasons["missing_pcue_score"] += 1
            continue

        x.append(criterion_values)
        y.append(gain)

    excluded = sum(reasons.values())
    return RegressionDataset(
        x=x,
        y=y,
        valid_rows=len(y),
        excluded_rows=excluded,
        exclusion_reasons=dict(reasons),
    )


def _fallback_result(sample_size: int, reason: str, notes: str = "") -> LearnedWeightResult:
    return LearnedWeightResult(
        phase=PHASE_2,
        sample_size=sample_size,
        raw_coefficients={},
        normalized_weights=dict(DEFAULT_BASELINE_WEIGHTS),
        adjusted_r2=None,
        p_values={criterion: None for criterion in PCUE_CRITERIA},
        date_generated=datetime.now(timezone.utc).isoformat(),
        notes=notes or "Fell back to Phase 1 fixed baseline weights.",
        fallback_used=True,
        fallback_reason=reason,
    )


def _coefficients_to_weights(coefficients: Mapping[str, float]) -> Optional[Dict[str, float]]:
    clipped: Dict[str, float] = {}
    for criterion in PCUE_CRITERIA:
        value = float(coefficients.get(criterion, 0.0))
        if math.isnan(value) or math.isinf(value):
            return None
        clipped[criterion] = max(0.0, value)
    total = sum(clipped.values())
    if total <= 0:
        return None
    normalized = {criterion: clipped[criterion] / total for criterion in PCUE_CRITERIA}
    return validate_weights(normalized, tolerance=1e-5)


def estimate_regression_derived_weights(
    rows: Iterable[Mapping[str, Any]],
    min_n: int = 30,
) -> LearnedWeightResult:
    """Estimate Phase 2 weights from normalized learning gain using OLS.

    Negative coefficients are clipped to zero before normalization. If the
    regression is underpowered or unstable, the function returns a documented
    fallback to the Phase 1 baseline.
    """

    dataset = build_regression_dataset(rows)
    if dataset.valid_rows < min_n:
        return _fallback_result(
            dataset.valid_rows,
            f"Minimum N >= {min_n} required for Phase 2; found {dataset.valid_rows}.",
            notes=f"Excluded rows by reason: {dataset.exclusion_reasons}",
        )

    try:
        import numpy as np
    except Exception as exc:  # pragma: no cover - exercised only without numpy.
        return _fallback_result(dataset.valid_rows, f"numpy unavailable for regression: {exc}")

    try:
        x = np.asarray(dataset.x, dtype=float)
        y = np.asarray(dataset.y, dtype=float)
        design = np.column_stack([np.ones(len(x)), x])
        beta, *_ = np.linalg.lstsq(design, y, rcond=None)
        predictions = design @ beta
        residual_sum = float(np.sum((y - predictions) ** 2))
        total_sum = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 0.0 if total_sum == 0 else 1.0 - residual_sum / total_sum
        p = len(PCUE_CRITERIA)
        adjusted_r2 = None
        if dataset.valid_rows > p + 1:
            adjusted_r2 = 1.0 - (1.0 - r2) * (dataset.valid_rows - 1) / (dataset.valid_rows - p - 1)
        raw = {criterion: float(beta[i + 1]) for i, criterion in enumerate(PCUE_CRITERIA)}
        normalized = _coefficients_to_weights(raw)
        if normalized is None:
            return _fallback_result(
                dataset.valid_rows,
                "Regression coefficients were all zero, negative, or invalid after clipping.",
                notes=f"Raw coefficients: {raw}",
            )
    except Exception as exc:
        return _fallback_result(dataset.valid_rows, f"Regression failed or was unstable: {exc}")

    return LearnedWeightResult(
        phase=PHASE_2,
        sample_size=dataset.valid_rows,
        raw_coefficients=raw,
        normalized_weights=normalized,
        adjusted_r2=adjusted_r2,
        p_values={criterion: None for criterion in PCUE_CRITERIA},
        date_generated=datetime.now(timezone.utc).isoformat(),
        notes=(
            "Weights estimated by linear regression of normalized learning gain "
            "on PCUE criterion scores. Negative coefficients were clipped to zero."
        ),
        fallback_used=False,
        fallback_reason=None,
    )


def write_learned_weights(result: LearnedWeightResult, output_path: Path) -> Path:
    """Write learned-weight metadata to a versioned JSON file."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
    return output_path


class PersonalizedCalibrationNetworkWeights:
    """Phase 3 placeholder for future LLM-Rubric-style calibration.

    Expected inputs:
    - criterion-level judge distributions
    - human expert ratings
    - normalized learning gain
    - player proficiency level
    - macro_stage
    - micro_stage
    - role
    - age_group
    """

    expected_inputs = (
        "criterion_level_judge_distributions",
        "human_expert_ratings",
        "normalized_learning_gain",
        "player_proficiency_level",
        "macro_stage",
        "micro_stage",
        "role",
        "age_group",
    )

    def fit(self, *_: Any, **__: Any) -> None:
        raise NotImplementedError(
            "Phase 3 Personalized Calibration Network weights are a future extension "
            "inspired by multidimensional calibrated rubric evaluation."
        )

    def predict_weights(self, *_: Any, **__: Any) -> Dict[str, float]:
        raise NotImplementedError(
            "Phase 3 Personalized Calibration Network prediction is not implemented yet."
        )
