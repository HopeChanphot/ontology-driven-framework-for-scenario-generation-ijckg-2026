#!/usr/bin/env python3
"""
PersonaShield Quest Scenario Evaluator
Layer 1: Rule-based JSON structure and variant-consistency tests
Layer 2: Automated scenario-quality scoring / LLM-as-judge preparation

Author: generated for PersonaShield Quest scenario-pool evaluation
Python: 3.10+

What this program does
----------------------
1. Loads one or more scenario_pool JSON files.
2. Supports both PersonaShield scenario structures:
   A) v4.x nested object structure:
      scenario_id -> channel -> variant -> model_name -> scenario_object
   B) older list-per-model structure:
      scenario_id -> channel -> variant -> model_name -> [scenario_object, ...]
3. Runs Layer 1 automated checks:
   - top-level scenario structure
   - required scenario fields
   - channel / variant consistency
   - fake vs real separation
   - safe / unsafe choice logic
   - score, hint, URL and red-flag consistency
4. Runs Layer 2 automated scenario-quality scoring:
   - OpenAI-style pedagogy / overall scenario quality score
   - Claude-style cybersecurity realism / safety score
   - Gemini-style game usability / cross-check score
   - combined score
5. Exports:
   - detailed CSV: one row per scenario variant/model/channel
   - summary CSV: aggregated results by source file, model, channel, variant
   - issue CSV: rows that fail Layer 1 or fall below quality thresholds
   - optional Excel workbook with all three sheets

Important note
--------------
This script does not call OpenAI, Anthropic, or Google APIs by default.
It produces deterministic rule-based and heuristic scores that can be used as
pre-screening before sending a smaller sample to real LLM judges or human experts.

Basic usage
-----------
python personashield_layer1_layer2_evaluator.py scenario_pool.json --out-dir ./evaluation_output
python personashield_layer1_layer2_evaluator.py scenario_pool1.json scenario_pool2.json --excel

Optional real LLM API integration
---------------------------------
This script intentionally keeps API calls disabled to avoid cost, privacy, and
rate-limit problems. See the JUDGE_PROMPT_TEMPLATE constant near the end of this
file if you want to send selected rows to GPT / Claude / Gemini manually or add
API clients later.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import pandas as pd
except ImportError as exc:
    raise SystemExit(
        "pandas is required. Install with: pip install pandas openpyxl"
    ) from exc

from scenario_evaluation.consensus import aggregate_judge_scores, proxy_judge_scores_from_layer2
from scenario_evaluation.decisions import determine_final_decision
from scenario_evaluation.guidance import generate_revision_guidance
from scenario_evaluation.judges import (
    DEFAULT_PROFILE_NAME,
    JUDGE_PROFILES,
    JudgeConfig,
    JudgeConfigError,
    hardware_warnings,
    reproducibility_metadata,
    select_judges,
)
from scenario_evaluation.live_judging import run_live_judges_with_proxy_fallback
from scenario_evaluation.qualifiers import qualify_score, qualify_scores
from scenario_evaluation.reports import (
    build_research_report,
    export_judge_score_tables,
    write_research_report,
)
from scenario_evaluation.weights import (
    DEFAULT_BASELINE_WEIGHTS,
    PHASE_1,
    PHASE_2,
    estimate_regression_derived_weights,
    load_playtesting_rows,
    phase_1_weight_metadata,
    write_learned_weights,
)


CHANNELS = ("sms", "email", "voice")
VARIANTS = ("fake", "real")

TOP_REQUIRED_KEYS = ["_profile", "_learning", "_rules", "_gsdl", "_bundle_meta"]

COMMON_REQUIRED_FIELDS = [
    "scenario_id",
    "channel",
    "variant",
    "correct_action",
]

# v4.x pools normally include game_choices; older pools may not.
GAMEPLAY_REQUIRED_FIELDS = ["game_choices"]

# These are strongly expected in v4.x. In older pools they may be nested inside
# sms_content/email_content/voice_content.
QUALITY_OPTIONAL_FIELDS = [
    "opening_hook",
    "title",
    "hint_text",
    "quality_score",
    "red_flags",
    "safe_indicators",
    "learning_focus",
]

SAFE_OUTCOMES = {"safe", "correct", "legitimate", "report", "verify"}
UNSAFE_OUTCOMES = {"unsafe", "incorrect", "click", "reply", "share", "ignore"}

URGENCY_PATTERNS = [
    r"\burgent\b",
    r"\bimmediate\b",
    r"\bimmediately\b",
    r"\basap\b",
    r"\btime[- ]?sensitive\b",
    r"\bwithin\s+\d+\s*(minutes?|hours?|mins?|hrs?)\b",
    r"\bdeadline\b",
    r"\bcut[- ]?off\b",
    r"\baccount.*(locked|suspended|blocked|frozen)\b",
    r"\bfailure to\b",
]

SENSITIVE_REQUEST_PATTERNS = [
    r"\bpassword\b",
    r"\blogin\b",
    r"\bcredential",
    r"\botp\b",
    r"\bsecurity code\b",
    r"\bbank detail",
    r"\bpayment instruction",
    r"\bwire transfer",
    r"\bbeneficiary",
    r"\bremote access\b",
    r"\bdownload\b",
    r"\battachment\b",
]

URL_PATTERN = re.compile(r"https?://[^\s'\"<>]+|www\.[^\s'\"<>]+", re.IGNORECASE)


@dataclass
class EvaluationRow:
    source_file: str
    persona_path_id: str
    scenario_key: str
    scenario_id: str
    role: str
    stage_id: str
    macro_stage: str
    micro_stage: str
    age_group: str
    channel: str
    variant: str
    model_name: str
    item_index: int

    # Layer 1
    layer1_pass: bool
    layer1_error_count: int
    layer1_warning_count: int
    layer1_errors: str
    layer1_warnings: str

    # Layer 2 primitive metrics
    text_chars: int
    readability_score: float
    learning_alignment_score: float
    choice_quality_score: float
    feedback_quality_score: float
    fake_real_consistency_score: float
    cybersecurity_realism_score: float
    safety_score: float
    game_usability_score: float

    # Layer 2 composite judges
    openai_pedagogy_quality_score: float
    claude_cybersecurity_safety_score: float
    gemini_game_usability_score: float
    combined_layer2_score: float
    quality_band: str

    # Research-ready PCUE fields added for reviewer-responsive validation
    pedagogical_quality_score: float
    cybersecurity_realism_pc_score: float
    usability_game_clarity_score: float
    ethical_safety_score: float
    qualifier: str
    criterion_qualifiers: str
    final_weighted_score: float
    final_decision: str
    decision_action: str
    revision_guidance: str
    weighting_phase: str
    weights_used: str
    veto_applied: bool
    veto_reason: str
    judge_metadata: str
    judge_scores_json: str
    judge_profile: str
    judge_disagreement: bool
    judge_disagreement_reason: str
    needs_human_review: bool
    self_judge_risk: bool
    cost_mode: str
    reproducibility_metadata: str
    weakest_criterion: str
    weakest_criterion_qualifier: str


# ---------------------------------------------------------------------------
# General text helpers
# ---------------------------------------------------------------------------


def strip_html(text: Any) -> str:
    if text is None:
        return ""
    text = str(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def safe_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(as_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(as_text(v) for v in value.values())
    return strip_html(str(value))


def clamp01(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(0.0, min(1.0, value))


def has_any_pattern(text: str, patterns: Sequence[str]) -> bool:
    text = text.lower()
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def extract_urls(text: str) -> List[str]:
    return URL_PATTERN.findall(text or "")


def count_syllables(word: str) -> int:
    word = word.lower()
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 1
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def flesch_reading_ease_normalized(text: str) -> float:
    """Return Flesch reading ease normalized to 0..1.

    Higher = easier to read. Non-English text and very short text may not be
    accurately represented, but the score is useful as a quick screening signal.
    """
    text = strip_html(text)
    sentences = [s for s in re.split(r"[.!?。！？]+", text) if s.strip()]
    words = re.findall(r"\b[A-Za-z]+\b", text)
    if len(words) < 5 or not sentences:
        return 0.50
    syllables = sum(count_syllables(w) for w in words)
    raw = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syllables / len(words))
    return clamp01(raw / 100.0)


# ---------------------------------------------------------------------------
# Scenario parsing helpers
# ---------------------------------------------------------------------------


def merge_wrapper_and_content(wrapper: Dict[str, Any], channel: str) -> Dict[str, Any]:
    """Return one flat scenario object.

    Some older pools store channel-specific content in sms_content, email_content,
    or voice_content, while metadata lives in the wrapper. This function merges
    them so that validation and scoring work on both old and new schemas.
    """
    if not isinstance(wrapper, dict):
        return {}

    nested_key = f"{channel}_content"
    nested = wrapper.get(nested_key)
    if isinstance(nested, dict):
        merged = dict(nested)
        for key, value in wrapper.items():
            if key not in ("sms_content", "email_content", "voice_content"):
                merged.setdefault(key, value)
        # Normalise missing fields
        merged.setdefault("channel", channel)
        merged.setdefault("variant", wrapper.get("variant"))
        merged.setdefault("scenario_id", wrapper.get("scenario_id"))
        merged.setdefault("persona_path_id", wrapper.get("persona_path_id"))
        merged.setdefault("llm_source", wrapper.get("llm_source"))
        merged.setdefault("quality_score", wrapper.get("quality_score"))
        return merged

    return dict(wrapper)


def scenario_text(fields: Dict[str, Any]) -> str:
    parts = [
        fields.get("title"),
        fields.get("opening_hook"),
        fields.get("subject"),
        fields.get("body_html"),
        fields.get("body"),
        fields.get("messages"),
        fields.get("dialogue"),
        fields.get("correct_action"),
        fields.get("hint_text"),
    ]
    return " \n ".join(as_text(p) for p in parts if p)


def get_role_stage(scenario: Dict[str, Any], fields: Dict[str, Any]) -> Tuple[str, str]:
    profile = scenario.get("_profile", {}) if isinstance(scenario, dict) else {}
    learning = scenario.get("_learning", {}) if isinstance(scenario, dict) else {}
    role = fields.get("role") or profile.get("role") or ""
    stage_id = fields.get("stage_id") or profile.get("stage_id") or learning.get("stage_id") or ""
    return str(role), str(stage_id)


def get_classification_metadata(scenario: Dict[str, Any], fields: Dict[str, Any]) -> Dict[str, str]:
    profile = scenario.get("_profile", {}) if isinstance(scenario, dict) else {}
    learning = scenario.get("_learning", {}) if isinstance(scenario, dict) else {}
    macro_stage = fields.get("macro_stage") or profile.get("macro_stage") or learning.get("macro_stage") or ""
    micro_stage = fields.get("micro_stage") or profile.get("micro_stage") or learning.get("micro_stage") or ""
    age_group = (
        fields.get("age_group_code")
        or fields.get("age_group")
        or profile.get("age_group_code")
        or profile.get("age_group")
        or learning.get("age_group")
        or ""
    )
    return {
        "macro_stage": str(macro_stage),
        "micro_stage": str(micro_stage),
        "age_group": str(age_group),
    }


def dumps_for_csv(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def iter_scenarios_from_pool(source_file: Path, pool: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any], str, str, str, int, Dict[str, Any]]]:
    """Yield parsed scenario items.

    Yields:
        scenario_key, scenario_obj, channel, variant, model_name, item_index, fields
    """
    for scenario_key, scenario in pool.items():
        if str(scenario_key).startswith("_"):
            continue
        if not isinstance(scenario, dict):
            continue

        for channel in CHANNELS:
            channel_obj = scenario.get(channel)
            if not isinstance(channel_obj, dict):
                continue
            for variant in VARIANTS:
                variant_obj = channel_obj.get(variant)
                if not isinstance(variant_obj, dict):
                    continue
                for model_name, model_payload in variant_obj.items():
                    items = model_payload if isinstance(model_payload, list) else [model_payload]
                    for index, item in enumerate(items):
                        if not isinstance(item, dict):
                            continue
                        fields = merge_wrapper_and_content(item, channel)
                        yield scenario_key, scenario, channel, variant, str(model_name), index, fields


# ---------------------------------------------------------------------------
# Layer 1: deterministic rule-based tests
# ---------------------------------------------------------------------------


def validate_layer1(
    scenario_key: str,
    scenario: Dict[str, Any],
    channel: str,
    expected_variant: str,
    model_name: str,
    fields: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    # Top-level validation. Some older files may not include v4 metadata.
    missing_top = [key for key in TOP_REQUIRED_KEYS if key not in scenario]
    if missing_top:
        warnings.append("Missing top-level v4 metadata keys: " + ", ".join(missing_top))

    # Channel and variant consistency
    actual_channel = str(fields.get("channel", channel)).lower()
    actual_variant = str(fields.get("variant", expected_variant)).lower()

    if actual_channel != channel:
        errors.append(f"Channel mismatch: expected {channel}, found {actual_channel}")
    if actual_variant != expected_variant:
        errors.append(f"Variant mismatch: expected {expected_variant}, found {actual_variant}")

    # Common required fields
    for key in COMMON_REQUIRED_FIELDS:
        if not fields.get(key):
            errors.append(f"Missing required field: {key}")

    # Scenario ID should exist. We do not force exact pattern across all generators,
    # but v4 IDs should end with channel_variant.
    sid = str(fields.get("scenario_id", ""))
    if sid and scenario_key.upper() in sid.upper():
        expected_suffix = f"_{channel}_{expected_variant}".lower()
        if not sid.lower().endswith(expected_suffix):
            warnings.append(f"scenario_id does not end with expected suffix {expected_suffix}: {sid}")

    # Text/content presence by channel
    if channel == "sms":
        if not fields.get("messages"):
            errors.append("SMS scenario missing messages")
    elif channel == "email":
        if not fields.get("body_html") and not fields.get("body"):
            errors.append("Email scenario missing body_html/body")
        if not fields.get("subject"):
            warnings.append("Email scenario missing subject")
    elif channel == "voice":
        if not fields.get("dialogue") and not fields.get("messages"):
            errors.append("Voice scenario missing dialogue/messages")

    # Correct action minimum quality
    correct_action = as_text(fields.get("correct_action"))
    if len(correct_action) < 15:
        errors.append("correct_action is too short or missing")

    # Choice logic: v4 pools require game_choices; older pools often don't have them.
    choices = safe_list(fields.get("game_choices"))
    if choices:
        correct_count = 0
        unsafe_count = 0
        missing_feedback = 0
        for choice in choices:
            if not isinstance(choice, dict):
                errors.append("game_choices contains non-object item")
                continue
            if choice.get("is_correct") is True or str(choice.get("outcome", "")).lower() in SAFE_OUTCOMES:
                correct_count += 1
            else:
                unsafe_count += 1
            if not choice.get("feedback"):
                missing_feedback += 1
        if correct_count < 1:
            errors.append("game_choices has no correct/safe option")
        if unsafe_count < 1 and len(choices) > 1:
            errors.append("game_choices has no distractor/unsafe option")
        if missing_feedback:
            warnings.append(f"{missing_feedback} game choice(s) missing feedback")
    else:
        warnings.append("Missing game_choices; usable for static evaluation but not full game validation")

    # Fake/real separation
    malicious_url = fields.get("malicious_url")
    red_flags = safe_list(fields.get("red_flags"))
    safe_indicators = safe_list(fields.get("safe_indicators"))
    attack_tactics = safe_list(fields.get("attack_tactics"))
    psych_triggers = safe_list(fields.get("psych_triggers"))
    attack_type = str(fields.get("attack_type", "")).lower()

    if expected_variant == "fake":
        if attack_type in ("legitimate", "real", "benign"):
            errors.append(f"Fake scenario has legitimate attack_type: {attack_type}")
        if not (malicious_url or red_flags or attack_tactics or psych_triggers):
            errors.append("Fake scenario lacks malicious_url/red_flags/attack_tactics/psych_triggers")
        if safe_indicators and not red_flags:
            warnings.append("Fake scenario has safe_indicators but no red_flags")
    else:
        if malicious_url:
            errors.append("Real scenario has malicious_url")
        if attack_tactics:
            warnings.append("Real scenario has attack_tactics; confirm it is not mixed with fake content")
        if psych_triggers:
            warnings.append("Real scenario has psych_triggers; confirm it is not mixed with fake content")
        if red_flags:
            warnings.append("Real scenario has red_flags; verify whether this is intended as cautious verification")
        if not safe_indicators:
            warnings.append("Real scenario has no safe_indicators")

    # Score and hint validation
    for numeric_key in ("score_reward", "score_penalty", "hint_cost", "quality_score"):
        if numeric_key in fields and fields.get(numeric_key) is not None:
            try:
                float(fields[numeric_key])
            except (TypeError, ValueError):
                errors.append(f"{numeric_key} is not numeric")

    if fields.get("show_hint") is True and not fields.get("hint_text"):
        warnings.append("show_hint is true but hint_text is missing")

    return errors, warnings


# ---------------------------------------------------------------------------
# Layer 2: heuristic judge scoring
# ---------------------------------------------------------------------------


def learning_alignment_score(fields: Dict[str, Any], scenario: Dict[str, Any]) -> float:
    text = scenario_text(fields).lower()
    objectives = safe_list(fields.get("learning_focus"))
    if not objectives:
        learning = scenario.get("_learning", {}) if isinstance(scenario, dict) else {}
        objectives = safe_list(learning.get("learning_objectives"))

    if not objectives:
        return 0.50

    # Score based on keyword overlap, not exact sentence matching.
    scores = []
    for obj in objectives:
        words = [w for w in re.findall(r"[a-zA-Z]{4,}", as_text(obj).lower()) if w not in {
            "with", "that", "this", "from", "through", "before", "after", "into", "when", "then", "they", "them", "your"
        }]
        if not words:
            scores.append(0.0)
            continue
        hit = sum(1 for w in set(words) if w in text)
        scores.append(hit / max(1, len(set(words))))
    return clamp01(mean(scores))


def choice_quality_score(fields: Dict[str, Any]) -> float:
    choices = [c for c in safe_list(fields.get("game_choices")) if isinstance(c, dict)]
    if not choices:
        return 0.0
    correct = sum(1 for c in choices if c.get("is_correct") is True or str(c.get("outcome", "")).lower() in SAFE_OUTCOMES)
    unsafe = len(choices) - correct
    has_labels = sum(1 for c in choices if as_text(c.get("label"))) / len(choices)
    has_feedback = sum(1 for c in choices if as_text(c.get("feedback"))) / len(choices)
    return clamp01(0.25 * min(len(choices) / 3, 1) + 0.25 * min(correct, 1) + 0.20 * min(unsafe, 1) + 0.15 * has_labels + 0.15 * has_feedback)


def feedback_quality_score(fields: Dict[str, Any]) -> float:
    feedbacks = []
    for choice in safe_list(fields.get("game_choices")):
        if isinstance(choice, dict):
            feedbacks.append(as_text(choice.get("feedback")))
    hint = as_text(fields.get("hint_text"))
    correct = as_text(fields.get("correct_action"))
    text = " ".join(feedbacks + [hint, correct])
    if not text.strip():
        return 0.0
    # Reward explanation, verification language, and actionability.
    score = 0.0
    if len(text) >= 80:
        score += 0.25
    if re.search(r"\bverify|check|confirm|portal|official|approved|trusted|report|escalate\b", text, re.I):
        score += 0.35
    if re.search(r"\bwhy|because|risk|instead|before|after\b", text, re.I):
        score += 0.20
    if len(feedbacks) >= 2:
        score += 0.20
    return clamp01(score)


def fake_real_consistency_score(fields: Dict[str, Any], variant: str) -> float:
    text = scenario_text(fields)
    red_flags = safe_list(fields.get("red_flags"))
    safe_indicators = safe_list(fields.get("safe_indicators"))
    malicious_url = fields.get("malicious_url")
    attack_tactics = safe_list(fields.get("attack_tactics"))
    psych_triggers = safe_list(fields.get("psych_triggers"))
    urgency = has_any_pattern(text, URGENCY_PATTERNS)
    sensitive = has_any_pattern(text, SENSITIVE_REQUEST_PATTERNS)

    if variant == "fake":
        score = 0.0
        if red_flags:
            score += 0.25
        if malicious_url or extract_urls(text):
            score += 0.20
        if attack_tactics:
            score += 0.15
        if psych_triggers or urgency:
            score += 0.20
        if sensitive:
            score += 0.10
        if not safe_indicators or len(red_flags) >= len(safe_indicators):
            score += 0.10
        return clamp01(score)

    # Real scenario: reward absence of suspicious markers and presence of safe indicators.
    score = 0.0
    if not malicious_url:
        score += 0.25
    if not attack_tactics:
        score += 0.15
    if not psych_triggers:
        score += 0.15
    if not red_flags:
        score += 0.15
    if safe_indicators:
        score += 0.20
    if not sensitive or re.search(r"\bofficial|portal|directly|app|verified|approved\b", text, re.I):
        score += 0.10
    return clamp01(score)


def cybersecurity_realism_score(fields: Dict[str, Any], variant: str, role: str) -> float:
    text = scenario_text(fields)
    red_flags = safe_list(fields.get("red_flags"))
    attack_tactics = safe_list(fields.get("attack_tactics"))
    psych_triggers = safe_list(fields.get("psych_triggers"))
    urls = extract_urls(text)
    has_urgency = has_any_pattern(text, URGENCY_PATTERNS)
    has_sensitive_request = has_any_pattern(text, SENSITIVE_REQUEST_PATTERNS)
    has_named_entity = bool(re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text))
    has_role_context = bool(role and role.lower() in text.lower()) or bool(re.search(r"finance|invoice|payroll|hr|it|manager|vendor|account|portal", text, re.I))

    if variant == "fake":
        score = 0.0
        if red_flags:
            score += 0.20
        if attack_tactics:
            score += 0.15
        if psych_triggers or has_urgency:
            score += 0.20
        if urls or fields.get("malicious_url"):
            score += 0.15
        if has_sensitive_request:
            score += 0.15
        if has_named_entity or has_role_context:
            score += 0.15
        return clamp01(score)

    # Real scenario realism: normal business context, clear safe indicators, no fake artifacts.
    score = 0.0
    if safe_list(fields.get("safe_indicators")):
        score += 0.25
    if has_role_context:
        score += 0.25
    if not fields.get("malicious_url"):
        score += 0.20
    if not red_flags:
        score += 0.15
    if len(text) >= 80:
        score += 0.15
    return clamp01(score)


def safety_score(fields: Dict[str, Any], variant: str) -> float:
    text = scenario_text(fields)
    correct = as_text(fields.get("correct_action"))
    choices = [c for c in safe_list(fields.get("game_choices")) if isinstance(c, dict)]

    score = 0.0
    if re.search(r"\breport|verify|confirm|official|approved|trusted|escalate|do not click|do not share\b", correct, re.I):
        score += 0.35
    if not re.search(r"\benter your password|provide your password|share your otp|give your code\b", correct, re.I):
        score += 0.20
    if choices:
        safe_choices = [c for c in choices if c.get("is_correct") is True or str(c.get("outcome", "")).lower() in SAFE_OUTCOMES]
        if safe_choices:
            safe_labels = " ".join(as_text(c.get("label")) + " " + as_text(c.get("feedback")) for c in safe_choices)
            if re.search(r"\bverify|report|trusted|official|approved|pause|do not\b", safe_labels, re.I):
                score += 0.25
    else:
        score += 0.10
    if variant == "real" and fields.get("malicious_url"):
        score -= 0.40
    if variant == "fake" and not safe_list(fields.get("red_flags")):
        score -= 0.10
    return clamp01(score)


def game_usability_score(fields: Dict[str, Any]) -> float:
    choices = [c for c in safe_list(fields.get("game_choices")) if isinstance(c, dict)]
    text = scenario_text(fields)
    q_breakdown = fields.get("quality_breakdown") if isinstance(fields.get("quality_breakdown"), dict) else {}

    score = 0.0
    if as_text(fields.get("opening_hook")):
        score += 0.15
    if choices:
        score += 0.30 * choice_quality_score(fields)
        score += 0.20 * feedback_quality_score(fields)
    if as_text(fields.get("hint_text")):
        score += 0.10
    if len(text) >= 50:
        score += 0.10
    if fields.get("score_reward") is not None or fields.get("score_penalty") is not None:
        score += 0.10
    if q_breakdown:
        numeric_values = [float(v) for v in q_breakdown.values() if isinstance(v, (int, float))]
        if numeric_values:
            score += 0.15 * clamp01(mean(numeric_values))
    return clamp01(score)


def quality_band(score: float) -> str:
    if score >= 0.85:
        return "excellent"
    if score >= 0.70:
        return "good"
    if score >= 0.55:
        return "needs_review"
    return "high_risk"


def evaluate_layer2(fields: Dict[str, Any], scenario: Dict[str, Any], variant: str, role: str) -> Dict[str, float | str | int]:
    text = scenario_text(fields)
    readability = flesch_reading_ease_normalized(text)
    learning = learning_alignment_score(fields, scenario)
    choice = choice_quality_score(fields)
    feedback = feedback_quality_score(fields)
    consistency = fake_real_consistency_score(fields, variant)
    realism = cybersecurity_realism_score(fields, variant, role)
    safety = safety_score(fields, variant)
    game = game_usability_score(fields)

    # Composite judge scores:
    # OpenAI: pedagogy + overall quality
    openai = clamp01(0.25 * readability + 0.30 * learning + 0.20 * feedback + 0.15 * choice + 0.10 * consistency)
    # Claude: cyber realism + safety
    claude = clamp01(0.35 * realism + 0.35 * safety + 0.20 * consistency + 0.10 * feedback)
    # Gemini: game usability + cross-channel consistency
    gemini = clamp01(0.50 * game + 0.20 * choice + 0.15 * readability + 0.15 * consistency)
    combined = clamp01(0.34 * openai + 0.33 * claude + 0.33 * gemini)

    return {
        "text_chars": len(text),
        "readability_score": readability,
        "learning_alignment_score": learning,
        "choice_quality_score": choice,
        "feedback_quality_score": feedback,
        "fake_real_consistency_score": consistency,
        "cybersecurity_realism_score": realism,
        "safety_score": safety,
        "game_usability_score": game,
        "openai_pedagogy_quality_score": openai,
        "claude_cybersecurity_safety_score": claude,
        "gemini_game_usability_score": gemini,
        "combined_layer2_score": combined,
        "quality_band": quality_band(combined),
    }


# ---------------------------------------------------------------------------
# Main evaluation pipeline
# ---------------------------------------------------------------------------


def evaluate_files(
    json_files: Sequence[Path],
    judges: Optional[Sequence[JudgeConfig]] = None,
    judge_profile: str = DEFAULT_PROFILE_NAME,
    weighting_metadata: Optional[Dict[str, Any]] = None,
    run_live_judges: bool = False,
) -> pd.DataFrame:
    rows: List[EvaluationRow] = []
    selected_judges = list(judges or select_judges(DEFAULT_PROFILE_NAME, disable_paid_judges=True))
    weight_info = weighting_metadata or phase_1_weight_metadata()
    weights_used = weight_info.get("weights_used") or weight_info.get("normalized_weights") or DEFAULT_BASELINE_WEIGHTS
    run_reproducibility = reproducibility_metadata(selected_judges)
    run_cost_modes = ",".join(sorted({judge.cost_mode for judge in selected_judges}))

    for source_file in json_files:
        with source_file.open("r", encoding="utf-8") as f:
            pool = json.load(f)

        if not isinstance(pool, dict):
            raise ValueError(f"{source_file} is not a JSON object at top level")

        for scenario_key, scenario, channel, variant, model_name, index, fields in iter_scenarios_from_pool(source_file, pool):
            role, stage_id = get_role_stage(scenario, fields)
            classification = get_classification_metadata(scenario, fields)
            persona_path_id = str(fields.get("persona_path_id") or scenario_key)
            sid = str(fields.get("scenario_id") or "")

            errors, warnings = validate_layer1(scenario_key, scenario, channel, variant, model_name, fields)
            layer2 = evaluate_layer2(fields, scenario, variant, role)
            scenario_for_judging = dict(fields)
            scenario_for_judging.setdefault("model_name", model_name)
            if run_live_judges:
                judge_scores = run_live_judges_with_proxy_fallback(
                    selected_judges,
                    scenario_for_judging,
                    scenario_text(fields),
                    channel,
                    variant,
                    layer2,
                )
                score_source = "live_local_or_open_access_with_proxy_fallback"
            else:
                judge_scores = proxy_judge_scores_from_layer2(layer2, selected_judges, scenario_for_judging)
                score_source = "heuristic_proxy_no_live_api_call"
            consensus = aggregate_judge_scores(judge_scores)
            criterion_scores = consensus.aggregated_scores
            criterion_qualifiers = qualify_scores(criterion_scores)
            decision = determine_final_decision(
                criterion_scores,
                weights=weights_used,
                judge_disagreement=consensus.judge_disagreement,
            )
            overall_qualifier = qualify_score(decision.final_weighted_score)
            revision_guidance = generate_revision_guidance(fields, criterion_scores, criterion_qualifiers)
            weakest_criterion = min(criterion_scores, key=lambda key: criterion_scores[key])
            weakest_qualifier = criterion_qualifiers[weakest_criterion]["qualifier"]
            judge_metadata = {
                "judge_profile": judge_profile,
                "criterion_stats": consensus.criterion_stats,
                "high_disagreement_criteria": consensus.high_disagreement_criteria,
                "self_judge_risk": consensus.self_judge_risk,
                "score_source": score_source,
            }
            disagreement_reason = (
                "High judge disagreement for: " + ", ".join(consensus.high_disagreement_criteria)
                if consensus.high_disagreement_criteria
                else ""
            )

            rows.append(
                EvaluationRow(
                    source_file=source_file.name,
                    persona_path_id=persona_path_id,
                    scenario_key=scenario_key,
                    scenario_id=sid,
                    role=role,
                    stage_id=stage_id,
                    macro_stage=classification["macro_stage"],
                    micro_stage=classification["micro_stage"],
                    age_group=classification["age_group"],
                    channel=channel,
                    variant=variant,
                    model_name=model_name,
                    item_index=index,
                    layer1_pass=len(errors) == 0,
                    layer1_error_count=len(errors),
                    layer1_warning_count=len(warnings),
                    layer1_errors=" | ".join(errors),
                    layer1_warnings=" | ".join(warnings),
                    text_chars=int(layer2["text_chars"]),
                    readability_score=float(layer2["readability_score"]),
                    learning_alignment_score=float(layer2["learning_alignment_score"]),
                    choice_quality_score=float(layer2["choice_quality_score"]),
                    feedback_quality_score=float(layer2["feedback_quality_score"]),
                    fake_real_consistency_score=float(layer2["fake_real_consistency_score"]),
                    cybersecurity_realism_score=float(layer2["cybersecurity_realism_score"]),
                    safety_score=float(layer2["safety_score"]),
                    game_usability_score=float(layer2["game_usability_score"]),
                    openai_pedagogy_quality_score=float(layer2["openai_pedagogy_quality_score"]),
                    claude_cybersecurity_safety_score=float(layer2["claude_cybersecurity_safety_score"]),
                    gemini_game_usability_score=float(layer2["gemini_game_usability_score"]),
                    combined_layer2_score=float(layer2["combined_layer2_score"]),
                    quality_band=str(layer2["quality_band"]),
                    pedagogical_quality_score=float(criterion_scores["pedagogical_quality"]),
                    cybersecurity_realism_pc_score=float(criterion_scores["cybersecurity_realism"]),
                    usability_game_clarity_score=float(criterion_scores["usability_game_clarity"]),
                    ethical_safety_score=float(criterion_scores["ethical_safety"]),
                    qualifier=overall_qualifier.qualifier,
                    criterion_qualifiers=dumps_for_csv(criterion_qualifiers),
                    final_weighted_score=decision.final_weighted_score,
                    final_decision=decision.final_decision,
                    decision_action=decision.decision_action,
                    revision_guidance=dumps_for_csv(revision_guidance),
                    weighting_phase=str(weight_info.get("weighting_phase") or weight_info.get("phase") or PHASE_1),
                    weights_used=dumps_for_csv(weights_used),
                    veto_applied=decision.veto_applied,
                    veto_reason=decision.veto_reason or "",
                    judge_metadata=dumps_for_csv(judge_metadata),
                    judge_scores_json=dumps_for_csv([score.as_dict() for score in consensus.judge_scores]),
                    judge_profile=judge_profile,
                    judge_disagreement=consensus.judge_disagreement,
                    judge_disagreement_reason=disagreement_reason,
                    needs_human_review=decision.needs_human_review,
                    self_judge_risk=consensus.self_judge_risk,
                    cost_mode=run_cost_modes,
                    reproducibility_metadata=dumps_for_csv(run_reproducibility),
                    weakest_criterion=weakest_criterion,
                    weakest_criterion_qualifier=str(weakest_qualifier),
                )
            )

    return pd.DataFrame([asdict(r) for r in rows])


def make_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    grouped = df.groupby(["source_file", "model_name", "channel", "variant"], dropna=False)
    summary = grouped.agg(
        rows=("scenario_id", "count"),
        layer1_pass_rate=("layer1_pass", "mean"),
        avg_layer1_errors=("layer1_error_count", "mean"),
        avg_readability=("readability_score", "mean"),
        avg_learning_alignment=("learning_alignment_score", "mean"),
        avg_cyber_realism=("cybersecurity_realism_score", "mean"),
        avg_safety=("safety_score", "mean"),
        avg_game_usability=("game_usability_score", "mean"),
        avg_openai_score=("openai_pedagogy_quality_score", "mean"),
        avg_claude_score=("claude_cybersecurity_safety_score", "mean"),
        avg_gemini_score=("gemini_game_usability_score", "mean"),
        avg_combined_score=("combined_layer2_score", "mean"),
        avg_final_weighted_score=("final_weighted_score", "mean"),
        accepted_rate=("final_decision", lambda values: (values == "ACCEPTED").mean()),
        minor_revision_rate=("final_decision", lambda values: (values == "MINOR_REVISION").mean()),
        major_revision_rate=("final_decision", lambda values: (values == "MAJOR_REVISION").mean()),
        reject_regenerate_rate=("final_decision", lambda values: (values == "REJECT_REGENERATE").mean()),
        needs_human_review_rate=("needs_human_review", "mean"),
        veto_applied_rate=("veto_applied", "mean"),
    ).reset_index()

    return summary


def make_issue_report(df: pd.DataFrame, threshold: float = 0.55) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df[
        (~df["layer1_pass"])
        | (df["combined_layer2_score"] < threshold)
        | (df["final_decision"] != "ACCEPTED")
        | (df["needs_human_review"])
    ].copy()


def write_outputs(
    df: pd.DataFrame,
    out_dir: Path,
    excel: bool,
    issue_threshold: float,
    judge_profile: str = DEFAULT_PROFILE_NAME,
    judges: Optional[Sequence[JudgeConfig]] = None,
    weighting_metadata: Optional[Dict[str, Any]] = None,
    paid_judges_enabled: bool = False,
    hardware_warning_messages: Optional[List[str]] = None,
) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    detailed_path = out_dir / "layer1_layer2_detailed_results.csv"
    summary_path = out_dir / "layer1_layer2_summary.csv"
    issues_path = out_dir / "layer1_layer2_issues_to_review.csv"

    summary = make_summary(df)
    issues = make_issue_report(df, issue_threshold)

    df.to_csv(detailed_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    issues.to_csv(issues_path, index=False, encoding="utf-8-sig")

    outputs = {
        "detailed_csv": detailed_path,
        "summary_csv": summary_path,
        "issues_csv": issues_path,
    }
    selected_judges = list(judges or [])
    if selected_judges:
        outputs.update(export_judge_score_tables(df, out_dir))
        report = build_research_report(
            df,
            judge_profile=judge_profile,
            judges=selected_judges,
            weighting_metadata=weighting_metadata or phase_1_weight_metadata(),
            paid_judges_enabled=paid_judges_enabled,
            hardware_warning_messages=hardware_warning_messages,
        )
        outputs.update(write_research_report(report, out_dir))

    if excel:
        excel_path = out_dir / "layer1_layer2_evaluation_workbook.xlsx"
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Detailed", index=False)
            summary.to_excel(writer, sheet_name="Summary", index=False)
            issues.to_excel(writer, sheet_name="Issues_To_Review", index=False)
            if "judge_scores_long_csv" in outputs and not df.empty:
                judge_long = pd.read_csv(outputs["judge_scores_long_csv"])
                judge_long.to_excel(writer, sheet_name="Judge_Scores_Long", index=False)
        outputs["excel_workbook"] = excel_path

    return outputs


JUDGE_PROMPT_TEMPLATE = """
You are an expert evaluator for PersonaShield Quest, a gamified cybersecurity-awareness scenario system.
Evaluate the scenario below using a 1-5 scale for each criterion.
Return strict JSON only.

Judge role: {judge_role}
Scenario channel: {channel}
Scenario variant: {variant}
Scenario content:
{scenario_content}

Criteria:
1. accuracy
2. completeness
3. appropriateness
4. insight_or_reasoning
5. consistency
6. safety
7. phishing_realism
8. game_usability
9. feedback_quality

JSON schema:
{{
  "accuracy": 1,
  "completeness": 1,
  "appropriateness": 1,
  "insight_or_reasoning": 1,
  "consistency": 1,
  "safety": 1,
  "phishing_realism": 1,
  "game_usability": 1,
  "feedback_quality": 1,
  "overall_score": 1,
  "major_strengths": [],
  "major_issues": [],
  "recommended_fix": ""
}}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate PersonaShield Quest scenario pools using Layer 1 and Layer 2 checks.")
    parser.add_argument("json_files", nargs="*", type=Path, help="One or more scenario_pool JSON files")
    parser.add_argument("--scenario-pool", action="append", type=Path, default=[], help="Scenario pool JSON file; may be repeated")
    parser.add_argument("--out-dir", type=Path, default=Path("evaluation_output"), help="Output directory")
    parser.add_argument("--excel", action="store_true", help="Also export an Excel workbook")
    parser.add_argument("--issue-threshold", type=float, default=0.55, help="Layer 2 combined score threshold for issue report")
    parser.add_argument(
        "--judge-profile",
        choices=sorted(JUDGE_PROFILES.keys()),
        default=DEFAULT_PROFILE_NAME,
        help="Open-weight/local judge profile to record and use for deterministic judge-shaped scoring",
    )
    parser.add_argument("--judge-config", type=Path, help="Path to YAML/JSON judge configuration")
    parser.add_argument("--disable-paid-judges", action="store_true", help="Reject paid API provider types")
    parser.add_argument("--allow-paid-baseline", action="store_true", help="Allow paid judges only as optional comparison baselines")
    parser.add_argument("--dry-run-judges", action="store_true", help="Print selected judges without evaluating scenarios")
    parser.add_argument("--run-live-judges", action="store_true", help="Call configured local/open-access judge endpoints; falls back to proxy scores per failed judge")
    parser.add_argument(
        "--weighting-phase",
        choices=[PHASE_1, PHASE_2],
        default=PHASE_1,
        help="Weighting method for final PCUE weighted score",
    )
    parser.add_argument("--playtest-outcomes", type=Path, help="CSV/JSONL/JSON play-testing data for Phase 2 weights")
    parser.add_argument("--learned-weights-out", type=Path, help="Where to write Phase 2 learned-weight metadata")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    json_files = list(args.json_files) + list(args.scenario_pool or [])
    if not json_files:
        raise SystemExit("No scenario pool JSON file supplied. Use a positional file or --scenario-pool.")

    disable_paid = args.disable_paid_judges or not args.allow_paid_baseline
    try:
        judges = select_judges(
            profile_name=args.judge_profile,
            judge_config=args.judge_config,
            disable_paid_judges=disable_paid,
            allow_paid_baseline=args.allow_paid_baseline,
        )
    except JudgeConfigError as exc:
        raise SystemExit(str(exc)) from exc

    warnings_for_hardware = hardware_warnings(judges)
    if args.dry_run_judges:
        print(f"Judge profile: {args.judge_profile}")
        print(f"Paid judges enabled: {bool(args.allow_paid_baseline and not args.disable_paid_judges)}")
        print(f"Live judge calls enabled: {bool(args.run_live_judges)}")
        for judge in judges:
            print(
                f"- {judge.judge_id}: {judge.model_name} | provider={judge.provider_type} | "
                f"runtime={judge.local_runtime} | cost_mode={judge.cost_mode} | size={judge.model_size_class}"
            )
        for warning in warnings_for_hardware:
            print(f"WARNING: {warning}")
        return

    missing = [str(p) for p in json_files if not p.exists()]
    if missing:
        raise SystemExit("Missing input file(s): " + ", ".join(missing))

    if args.weighting_phase == PHASE_2:
        if not args.playtest_outcomes:
            result = estimate_regression_derived_weights([], min_n=30)
        else:
            result = estimate_regression_derived_weights(load_playtesting_rows(args.playtest_outcomes), min_n=30)
        learned_path = args.learned_weights_out or (args.out_dir / "learned_weights.json")
        write_learned_weights(result, learned_path)
        weighting_metadata = {
            "weighting_phase": result.phase,
            "weights_used": result.normalized_weights,
            "rationale": "Regression-derived empirical weights estimated from play-testing data when stable; otherwise Phase 1 fallback.",
            "learned_weights_used": not result.fallback_used,
            "sample_size": result.sample_size,
            "raw_coefficients": result.raw_coefficients,
            "adjusted_r2": result.adjusted_r2,
            "p_values": result.p_values,
            "fallback_reason": result.fallback_reason,
            "learned_weights_file": str(learned_path),
        }
    else:
        weighting_metadata = phase_1_weight_metadata()

    df = evaluate_files(
        json_files,
        judges=judges,
        judge_profile=args.judge_profile,
        weighting_metadata=weighting_metadata,
        run_live_judges=args.run_live_judges,
    )
    outputs = write_outputs(
        df,
        args.out_dir,
        args.excel,
        args.issue_threshold,
        judge_profile=args.judge_profile,
        judges=judges,
        weighting_metadata=weighting_metadata,
        paid_judges_enabled=bool(args.allow_paid_baseline and not args.disable_paid_judges),
        hardware_warning_messages=warnings_for_hardware,
    )

    print("Evaluation complete")
    print(f"Rows evaluated: {len(df)}")
    if not df.empty:
        print(f"Layer 1 pass rate: {df['layer1_pass'].mean():.2%}")
        print(f"Average combined Layer 2 score: {df['combined_layer2_score'].mean():.3f}")
        print(f"Average final PCUE weighted score: {df['final_weighted_score'].mean():.3f}")
        print("Final decisions:")
        for decision, count in df["final_decision"].value_counts().items():
            print(f"  {decision}: {count}")
    for warning in warnings_for_hardware:
        print(f"WARNING: {warning}")
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
