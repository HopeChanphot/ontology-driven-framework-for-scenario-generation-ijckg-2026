"""BERTScore-based semantic alignment for generated scenarios."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Sequence, Tuple

from .models import METHOD_ORDER, ScenarioScore
from .scenario_checks import expected_controls, required_concepts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPENDENCY_DIR = PROJECT_ROOT / ".codex_pydeps"
LOCAL_MPL_CONFIG_DIR = PROJECT_ROOT / ".matplotlib_cache"

if LOCAL_DEPENDENCY_DIR.exists() and str(LOCAL_DEPENDENCY_DIR) not in sys.path:
    sys.path.insert(0, str(LOCAL_DEPENDENCY_DIR))
LOCAL_MPL_CONFIG_DIR.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(LOCAL_MPL_CONFIG_DIR))


def bertscore_alignment_analysis(
    scores: Sequence[ScenarioScore],
    *,
    model_type: str = "distilbert-base-uncased",
    lang: str = "en",
    batch_size: int = 8,
    max_chars: int = 1800,
    enabled: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Compute case-reference BERTScore for generated scenarios.

    The reference is not a human-written target scenario. It is an automatic
    reference built from the frozen case specification and required concepts.
    This makes the metric a semantic-alignment proxy rather than a human-quality
    ground truth.
    """

    if not enabled:
        return [], []
    candidates: List[str] = []
    references: List[str] = []
    metadata: List[Dict[str, Any]] = []
    for score in scores:
        raw = _raw_for_score(score)
        scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
        case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
        candidate = _scenario_text(scenario)[:max_chars]
        reference = _case_reference_text(raw, scenario, case)[:max_chars]
        if not candidate.strip() or not reference.strip():
            continue
        candidates.append(candidate)
        references.append(reference)
        metadata.append(
            {
                "case_id": score.case_id,
                "scenario_id": score.scenario_id,
                "model_key": score.model_key,
                "method": score.method,
                "role": score.role,
                "stage_id": score.stage_id,
                "age_group_code": score.age_group_code,
                "channel": score.channel,
                "variant": score.variant,
                "reference_kind": "automatic_case_reference",
                "candidate_chars": len(candidate),
                "reference_chars": len(reference),
            }
        )

    if not candidates:
        return [], []

    precision, recall, f1, backend = _compute_bertscore(
        candidates,
        references,
        model_type=model_type,
        lang=lang,
        batch_size=batch_size,
    )
    rows: List[Dict[str, Any]] = []
    for meta, p_value, r_value, f_value in zip(metadata, precision, recall, f1):
        row = dict(meta)
        row.update(
            {
                "bertscore_precision": p_value,
                "bertscore_recall": r_value,
                "bertscore_f1": f_value,
                "bertscore_model": model_type,
                "bertscore_backend": backend,
                "bertscore_lang": lang,
            }
        )
        rows.append(row)

    return rows, bertscore_method_summary(rows)


def bertscore_method_summary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate BERTScore rows by method."""

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("method", ""))].append(row)
    summary: List[Dict[str, Any]] = []
    for method in METHOD_ORDER:
        method_rows = grouped.get(method, [])
        if not method_rows:
            continue
        summary.append(
            {
                "method": method,
                "n": len(method_rows),
                "bertscore_precision_mean": _safe_mean([row.get("bertscore_precision") for row in method_rows]),
                "bertscore_recall_mean": _safe_mean([row.get("bertscore_recall") for row in method_rows]),
                "bertscore_f1_mean": _safe_mean([row.get("bertscore_f1") for row in method_rows]),
                "bertscore_model": "; ".join(sorted({str(row.get("bertscore_model")) for row in method_rows})),
                "bertscore_backend": "; ".join(sorted({str(row.get("bertscore_backend")) for row in method_rows})),
                "reference_kind": "; ".join(sorted({str(row.get("reference_kind")) for row in method_rows})),
            }
        )
    return summary


def _compute_bertscore(
    candidates: Sequence[str],
    references: Sequence[str],
    *,
    model_type: str,
    lang: str,
    batch_size: int,
) -> Tuple[List[float], List[float], List[float], str]:
    try:
        from bert_score import score as bert_score  # type: ignore
    except Exception:
        return _embedding_cosine_fallback(candidates, references, model_type=model_type)

    try:
        p_tensor, r_tensor, f_tensor = bert_score(
            list(candidates),
            list(references),
            model_type=model_type,
            lang=lang,
            batch_size=batch_size,
            device="cpu",
            verbose=False,
            rescale_with_baseline=False,
        )
        return (
            [float(value) for value in p_tensor.tolist()],
            [float(value) for value in r_tensor.tolist()],
            [float(value) for value in f_tensor.tolist()],
            "bert_score_package",
        )
    except Exception:
        return _embedding_cosine_fallback(candidates, references, model_type=model_type)


def _embedding_cosine_fallback(
    candidates: Sequence[str],
    references: Sequence[str],
    *,
    model_type: str,
) -> Tuple[List[float], List[float], List[float], str]:
    """Fallback when BERTScore package/model fails; returns symmetric cosine."""

    try:
        from .diversity_metrics import embed_texts

        candidate_embeddings, backend, model_used = embed_texts(candidates, backend="sentence_transformers", model_name=None)
        reference_embeddings, _backend, _model_used = embed_texts(references, backend="sentence_transformers", model_name=None)
        values: List[float] = []
        for candidate_vector, reference_vector in zip(candidate_embeddings, reference_embeddings):
            values.append(sum(a * b for a, b in zip(candidate_vector, reference_vector)))
        return values, values, values, f"embedding_cosine_fallback:{backend}:{model_used}:requested={model_type}"
    except Exception:
        zeros = [0.0 for _ in candidates]
        return zeros, zeros, zeros, f"failed:{model_type}"


def _case_reference_text(raw: Dict[str, Any], scenario: Dict[str, Any], case: Dict[str, Any]) -> str:
    controls = expected_controls(case, scenario)
    concepts = required_concepts(raw, scenario, case)
    parts = [
        f"Role: {controls.get('role') or case.get('role')}",
        f"Stage: {case.get('stage_id') or scenario.get('stage_id')}",
        f"Age group: {case.get('age_group_code') or scenario.get('age_group_code')}",
        f"Channel: {controls.get('channel')}",
        f"Variant: {controls.get('variant')}",
        f"Attack type: {controls.get('attack_type')}",
        f"Difficulty: {case.get('difficulty_condition') or case.get('difficulty_band') or scenario.get('difficulty_band')}",
        "Safe response: pause, verify through a trusted approved channel, report suspicious activity if needed.",
        "Required concepts: " + "; ".join(concepts),
    ]
    if controls.get("variant") == "fake":
        parts.append("Expected scenario includes suspicious cues, red flags, social engineering pressure, and defensive verification.")
    else:
        parts.append("Expected scenario includes legitimate workflow indicators, safe verification, and normal approved process continuation.")
    return " ".join(str(part) for part in parts if part)


def _scenario_text(scenario: Dict[str, Any]) -> str:
    parts: List[str] = []
    for field in (
        "title",
        "opening_hook",
        "sender_or_caller",
        "from_address",
        "subject",
        "body_html",
        "correct_action",
        "hint_text",
        "attack_type",
        "channel",
        "variant",
        "role",
        "stage_id",
    ):
        if scenario.get(field):
            parts.append(str(scenario[field]))
    for list_field in (
        "messages",
        "dialogue",
        "red_flags",
        "safe_indicators",
        "attack_tactics",
        "psych_triggers",
        "learning_focus",
        "referenced_entities",
    ):
        values = scenario.get(list_field) or []
        if isinstance(values, list):
            parts.extend(str(value) for value in values if value)
    for choice in scenario.get("game_choices") or []:
        if isinstance(choice, dict):
            for key in ("label", "outcome", "feedback"):
                if choice.get(key):
                    parts.append(str(choice[key]))
    return " ".join(parts)


def _raw_for_score(score: ScenarioScore) -> Dict[str, Any]:
    try:
        with open(score.source_file, "r", encoding="utf-8") as handle:
            for current_line, line in enumerate(handle, start=1):
                if current_line == score.line_number:
                    return json.loads(line)
    except Exception:
        return {}
    return {}


def _safe_mean(values: Sequence[Any]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None
