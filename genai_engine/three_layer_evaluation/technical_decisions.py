"""Transparent non-compensatory technical triage for generated scenarios.

These decisions concern machine-checkable scenario integrity only. They do not
replace PCUE scoring, cybersecurity expert review, or final deployment approval.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Sequence


ACCEPTED = "ACCEPTED"
MINOR_REVISION = "MINOR_REVISION"
MAJOR_REVISION = "MAJOR_REVISION"
REJECT_REGENERATE = "REJECT_REGENERATE"
DECISION_ORDER = (ACCEPTED, MINOR_REVISION, MAJOR_REVISION, REJECT_REGENERATE)

DECISION_POLICY_VERSION = "technical_gate_v1"
DECISION_SCOPE = "automated_technical_triage_only"

CRITICAL_CONTROL_FIELDS = frozenset({"channel", "variant", "attack_type", "safe_response"})


@dataclass(frozen=True)
class TechnicalDecision:
    """One automated technical-triage outcome and its auditable reasons."""

    decision: str
    reason_codes: List[str]
    revision_guidance: List[str]
    policy_version: str = DECISION_POLICY_VERSION
    scope: str = DECISION_SCOPE
    final_human_review_required: bool = True

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def determine_technical_decision(
    *,
    json_parse_pass: bool,
    game_schema_missing: Sequence[str],
    failed_controls: Sequence[str],
    common_case_concepts_missing: Sequence[str],
    contradiction_reasons: Sequence[str],
) -> TechnicalDecision:
    """Apply the disclosed four-state, non-compensatory technical gate.

    The rule intentionally avoids a weighted composite. Critical parse,
    contradiction, schema, and case-control defects cannot be offset by strong
    values on unrelated metrics.
    """

    reasons: List[str] = []
    guidance: List[str] = []

    if not json_parse_pass:
        reasons.append("INVALID_JSON_OR_MISSING_SCENARIO_OBJECT")
        guidance.append("Regenerate a single parseable JSON object that contains the required scenario object.")
        return _result(REJECT_REGENERATE, reasons, guidance)

    if contradiction_reasons:
        reasons.extend(f"CONTRADICTION:{reason}" for reason in contradiction_reasons)
        guidance.append("Regenerate the scenario after correcting fake/real, attack/channel, and defensive-action contradictions.")
        return _result(REJECT_REGENERATE, reasons, guidance)

    critical_failures = sorted(set(failed_controls) & CRITICAL_CONTROL_FIELDS)
    noncritical_failures = sorted(set(failed_controls) - CRITICAL_CONTROL_FIELDS)

    if game_schema_missing:
        reasons.extend(f"MISSING_GAME_FIELD:{field}" for field in game_schema_missing)
        guidance.append("Add every missing game-executable field before re-evaluation.")

    if critical_failures:
        reasons.extend(f"CRITICAL_CONTROL_MISMATCH:{field}" for field in critical_failures)
        guidance.append("Rewrite the scenario so channel, variant, attack type, and safe response match the frozen case.")

    if len(failed_controls) >= 2:
        reasons.append("MULTIPLE_CASE_CONTROL_MISMATCHES")
        guidance.append("Reapply the complete frozen case specification, including role, age, stage, and difficulty.")

    if len(common_case_concepts_missing) >= 2:
        reasons.append("MULTIPLE_REQUIRED_CASE_CONCEPTS_MISSING")
        guidance.append("Restore the missing attack, cue, verification, safe-action, or legitimate-workflow concepts.")

    if game_schema_missing or critical_failures or len(failed_controls) >= 2 or len(common_case_concepts_missing) >= 2:
        return _result(MAJOR_REVISION, reasons, guidance)

    if noncritical_failures:
        reasons.extend(f"CASE_CONTROL_MISMATCH:{field}" for field in noncritical_failures)
        guidance.append("Correct the mismatched role, age group, stage, or difficulty field.")

    if common_case_concepts_missing:
        reasons.extend(f"REQUIRED_CASE_CONCEPT_MISSING:{item}" for item in common_case_concepts_missing)
        guidance.append("Add the missing case concept without changing the frozen channel, variant, or attack type.")

    if reasons:
        return _result(MINOR_REVISION, reasons, guidance)

    return _result(
        ACCEPTED,
        ["ALL_AUTOMATED_TECHNICAL_GATES_PASSED"],
        ["No automated technical revision is required; continue to PCUE and human expert review."],
    )


def _result(decision: str, reasons: Sequence[str], guidance: Sequence[str]) -> TechnicalDecision:
    return TechnicalDecision(
        decision=decision,
        reason_codes=_dedupe(reasons),
        revision_guidance=_dedupe(guidance),
    )


def _dedupe(values: Sequence[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
