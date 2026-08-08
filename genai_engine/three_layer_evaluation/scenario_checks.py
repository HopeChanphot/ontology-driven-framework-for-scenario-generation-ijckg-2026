"""Scenario-layer checks for PSQ-SCO generated game content."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from .models import (
    ATTACK_BY_CHANNEL,
    CONFORMANCE_WEIGHTS,
    CONTROL_FIELDS,
    GROUNDING_FIELDS,
    METHOD_CONDITION_NUMBERS,
    METHOD_LABELS,
    SCENARIO_REQUIRED_FIELDS,
    ScenarioRecord,
    ScenarioScore,
)
from .technical_decisions import determine_technical_decision


SAFE_ACTION_TERMS = (
    "verify",
    "verification",
    "check",
    "confirm",
    "validate",
    "review",
    "inspect",
    "contact",
    "call back",
    "call directly",
    "report",
    "pause",
    "escalate",
    "trusted",
    "approved",
    "official",
    "separate channel",
    "portal",
    "directory",
    "admin center",
)
VERIFICATION_TERMS = (
    "verify",
    "verification",
    "check",
    "confirm",
    "validate",
    "review",
    "inspect",
    "cross-check",
    "contact",
    "call back",
    "call directly",
    "trusted",
    "approved",
    "official",
    "separate channel",
    "portal",
    "directory",
    "admin center",
)
UNSAFE_ACTION_TERMS = (
    "click the link",
    "reply immediately",
    "provide password",
    "share password",
    "provide otp",
    "share otp",
    "send otp",
    "disable mfa",
    "ignore verification",
)
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+\-.]*", re.IGNORECASE)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def score_records(records: Iterable[ScenarioRecord]) -> List[ScenarioScore]:
    """Compute scenario-validation metrics for loaded generated outputs."""

    scores = [score_record(record) for record in records]
    _attach_observed_interarrival_seconds(scores)
    return scores


def score_record(record: ScenarioRecord) -> ScenarioScore:
    raw = record.raw or {}
    scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
    case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
    model = raw.get("model") if isinstance(raw.get("model"), dict) else {}
    method = infer_method(raw, scenario)
    condition_number = METHOD_CONDITION_NUMBERS.get(method, 0)
    condition_name = METHOD_LABELS.get(method, method)

    if record.parse_error:
        decision = determine_technical_decision(
            json_parse_pass=False,
            game_schema_missing=SCENARIO_REQUIRED_FIELDS,
            failed_controls=CONTROL_FIELDS,
            common_case_concepts_missing=(),
            contradiction_reasons=(record.parse_error,),
        )
        return ScenarioScore(
            source_file=record.source_file,
            line_number=record.line_number,
            case_id="PARSE_ERROR",
            scenario_id="",
            model_key=str(raw.get("llm_key", "")),
            model_name=str(model.get("model_name", "")),
            method=method,
            role=str(case.get("role", "")),
            stage_id=str(case.get("stage_id", "")),
            age_group_code=str(case.get("age_group_code", "")),
            channel=str(case.get("channel", "")),
            variant=str(case.get("variant", "")),
            json_validity=0.0,
            schema_completeness=0.0,
            control_adherence=0.0,
            required_concept_precision=0.0,
            required_concept_recall=0.0,
            required_concept_f1=0.0,
            grounding_completeness=0.0,
            condition_number=condition_number,
            condition_name=condition_name,
            game_schema_completeness=0.0,
            game_schema_complete_pass=0,
            automated_decision=decision.decision,
            decision_scope=decision.scope,
            decision_policy_version=decision.policy_version,
            final_human_review_required=decision.final_human_review_required,
            common_case_concept_precision=0.0,
            common_case_concept_recall=0.0,
            common_case_concept_f1=0.0,
            json_parse_pass=0,
            schema_complete_pass=0,
            all_controls_exact_match=0,
            trace_complete_pass=0,
            contradiction_free_pass=0,
            ontology_semantic_scope=0.0,
            contradiction=1,
            generation_integrity_status="PARSE_ERROR",
            contradiction_reasons=[record.parse_error],
            overall_conformance=0.0,
            missing_required_fields=list(SCENARIO_REQUIRED_FIELDS),
            decision_reason_codes=decision.reason_codes,
            revision_guidance=decision.revision_guidance,
        )

    json_validity = 1.0 if scenario else 0.0
    schema_completeness, missing_fields = schema_completeness_score(raw, scenario)
    game_schema_completeness, missing_game_fields = game_schema_completeness_score(scenario)
    control_score, failed_controls = control_adherence_score(scenario, case)
    precision, recall, f1, matched, missing = concept_f1_score(raw, scenario, case)
    common_precision, common_recall, common_f1, common_matched, common_missing = common_case_concept_score(
        scenario, case
    )
    grounding, present_grounding, missing_grounding = grounding_completeness_score(raw, scenario)
    ontology_scope = ontology_semantic_scope_score(raw, scenario, case)
    contradiction, contradiction_reasons = contradiction_check(scenario, case)
    integrity = generation_integrity(raw, scenario)
    engine_validation_value = raw.get("validation_passed")
    engine_validation_passed = (
        bool(engine_validation_value) if isinstance(engine_validation_value, bool) else None
    )
    engine_validation_issues = list(
        dict.fromkeys(
            str(issue)
            for issue in (raw.get("validation_issues") or [])
            if str(issue).strip()
        )
    )
    decision = determine_technical_decision(
        json_parse_pass=bool(json_validity == 1.0),
        game_schema_missing=missing_game_fields,
        failed_controls=failed_controls,
        common_case_concepts_missing=common_missing,
        contradiction_reasons=contradiction_reasons,
    )
    timing = generation_timing(raw, scenario)
    overall = overall_conformance(
        json_validity=json_validity,
        control_adherence=control_score,
        required_concept_f1=f1,
        grounding_completeness=grounding,
        contradiction=contradiction,
    )

    return ScenarioScore(
        source_file=record.source_file,
        line_number=record.line_number,
        case_id=str(case.get("case_id", raw.get("result_key", ""))),
        scenario_id=str(scenario.get("scenario_id", "")),
        model_key=str(raw.get("llm_key", model.get("key", ""))),
        model_name=str(model.get("model_name", "")),
        method=method,
        role=str(case.get("role", scenario.get("role", ""))),
        stage_id=str(case.get("stage_id", scenario.get("stage_id", ""))),
        age_group_code=str(case.get("age_group_code", scenario.get("age_group_code", ""))),
        channel=str(case.get("channel", scenario.get("channel", ""))),
        variant=str(case.get("variant", scenario.get("variant", ""))),
        json_validity=json_validity,
        schema_completeness=schema_completeness,
        control_adherence=control_score,
        required_concept_precision=precision,
        required_concept_recall=recall,
        required_concept_f1=f1,
        grounding_completeness=grounding,
        condition_number=condition_number,
        condition_name=condition_name,
        game_schema_completeness=game_schema_completeness,
        game_schema_complete_pass=int(not missing_game_fields),
        automated_decision=decision.decision,
        decision_scope=decision.scope,
        decision_policy_version=decision.policy_version,
        final_human_review_required=decision.final_human_review_required,
        common_case_concept_precision=common_precision,
        common_case_concept_recall=common_recall,
        common_case_concept_f1=common_f1,
        json_parse_pass=int(json_validity == 1.0),
        schema_complete_pass=int(not missing_fields),
        all_controls_exact_match=int(not failed_controls),
        trace_complete_pass=int(not missing_grounding),
        contradiction_free_pass=int(contradiction == 0),
        ontology_semantic_scope=ontology_scope,
        contradiction=contradiction,
        used_live_llm=bool(raw.get("used_live_llm")),
        used_fallback=bool(raw.get("used_fallback")),
        schema_safe_repair_used=integrity["schema_safe_repair_used"],
        live_model_content_retained=integrity["live_model_content_retained"],
        generation_integrity_status=integrity["generation_integrity_status"],
        engine_validation_passed=engine_validation_passed,
        engine_validation_issue_count=len(engine_validation_issues),
        generation_seconds=timing.get("generation_seconds"),
        raw_text_chars=timing.get("raw_text_chars"),
        parse_retry_count=int(timing.get("parse_retry_count") or 0),
        contradiction_reasons=contradiction_reasons,
        overall_conformance=overall,
        missing_required_fields=missing_fields,
        failed_control_fields=failed_controls,
        matched_required_concepts=matched,
        missing_required_concepts=missing,
        grounding_fields_present=present_grounding,
        grounding_fields_missing=missing_grounding,
        common_case_concepts_matched=common_matched,
        common_case_concepts_missing=common_missing,
        decision_reason_codes=decision.reason_codes,
        revision_guidance=decision.revision_guidance,
        engine_validation_issues=engine_validation_issues,
    )


def generation_integrity(raw: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Classify whether finalized content still represents the successful live response.

    A live HTTP/model call and a live-model-derived finalized scenario are not
    equivalent.  The generation engine can replace an unrepairable response
    with its deterministic schema-safe object while retaining
    ``used_live_llm=true``.  This audit keeps both facts visible.
    """

    meta = scenario.get("generation_meta") if isinstance(scenario.get("generation_meta"), dict) else {}
    repair_note = str(meta.get("repair_note", "")).lower()
    llm_source = str(scenario.get("llm_source", "")).lower()
    used_live_llm = bool(raw.get("used_live_llm"))
    used_fallback = bool(raw.get("used_fallback"))
    schema_safe_repair_used = (
        "schema-safe fallback used" in repair_note
        or llm_source == "offline_fallback"
    )
    live_model_content_retained = (
        used_live_llm and not used_fallback and not schema_safe_repair_used
    )
    if schema_safe_repair_used and used_live_llm:
        status = "LIVE_CALL_SCHEMA_SAFE_REPAIR"
    elif used_fallback:
        status = "NONLIVE_FALLBACK"
    elif live_model_content_retained:
        status = "LIVE_MODEL_CONTENT_RETAINED"
    elif used_live_llm:
        status = "LIVE_CALL_CONTENT_STATUS_UNCLEAR"
    else:
        status = "NO_LIVE_CALL_RECORDED"
    return {
        "schema_safe_repair_used": schema_safe_repair_used,
        "live_model_content_retained": live_model_content_retained,
        "generation_integrity_status": status,
    }


def infer_method(raw: Dict[str, Any], scenario: Dict[str, Any]) -> str:
    """Normalize generation-engine modes into the paper methods."""

    mode = str(raw.get("mode") or scenario.get("generation_meta", {}).get("mode") or "").lower()
    grounding = str(scenario.get("generation_meta", {}).get("grounding_mode", "")).lower()
    if "ontology_text_rag" in mode or "ontology_text_rag" in grounding:
        return "ontology_text_rag"
    if "ontology_prompt_rag" in mode:
        return "ontology_prompt_rag"
    if "prompt_rag" in mode:
        return "prompt_rag"
    if "prompt_only" in mode or "default_template" in mode or "prompt_only" in grounding:
        return "prompt_only"
    if scenario.get("generation_meta", {}).get("ontology_trace"):
        return "ontology_prompt_rag"
    if scenario.get("generation_meta", {}).get("ontology_text_trace"):
        return "ontology_text_rag"
    if scenario.get("generation_meta", {}).get("rag_trace"):
        return "prompt_rag"
    return "prompt_only"


def schema_completeness_score(raw: Dict[str, Any], scenario: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Return executable schema/provenance completeness, separate from parse validity."""

    missing: List[str] = []
    if not scenario:
        return 0.0, list(SCENARIO_REQUIRED_FIELDS)
    for field in SCENARIO_REQUIRED_FIELDS:
        if not scenario.get(field):
            missing.append(field)
    if not scenario.get("difficulty_band") and not scenario.get("difficulty"):
        missing.append("difficulty")
    if not scenario.get("red_flags") and not scenario.get("safe_indicators"):
        missing.append("red_flags_or_safe_indicators")
    evidence_present = _has_evidence(raw, scenario)
    if not evidence_present:
        missing.append("evidence_id_or_source_id")
    score = max(0.0, 1.0 - len(missing) / 8.0)
    return score, missing


def game_schema_completeness_score(scenario: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Return game-executable field completeness without provenance confounding."""

    checks = list(SCENARIO_REQUIRED_FIELDS) + ["difficulty", "red_flags_or_safe_indicators"]
    if not scenario:
        return 0.0, checks
    missing: List[str] = []
    for field in SCENARIO_REQUIRED_FIELDS:
        if not scenario.get(field):
            missing.append(field)
    if not scenario.get("difficulty_band") and not scenario.get("difficulty"):
        missing.append("difficulty")
    if not scenario.get("red_flags") and not scenario.get("safe_indicators"):
        missing.append("red_flags_or_safe_indicators")
    return (len(checks) - len(missing)) / len(checks), missing


def control_adherence_score(scenario: Dict[str, Any], case: Dict[str, Any]) -> Tuple[float, List[str]]:
    failed: List[str] = []
    expected = expected_controls(case, scenario)
    for field in CONTROL_FIELDS:
        if not _control_matches(field, expected.get(field), scenario, case):
            failed.append(field)
    matched = len(CONTROL_FIELDS) - len(failed)
    return matched / len(CONTROL_FIELDS), failed


def expected_controls(case: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    channel = str(case.get("channel", scenario.get("channel", ""))).lower()
    variant = str(case.get("variant", scenario.get("variant", ""))).lower()
    return {
        "role": case.get("role", scenario.get("role")),
        "age_group_code": case.get("age_group_code", scenario.get("age_group_code")),
        "stage_id": case.get("stage_id", scenario.get("stage_id")),
        "channel": channel,
        "variant": variant,
        "difficulty_band": case.get("difficulty_band", scenario.get("difficulty_band")),
        "attack_type": "legitimate" if variant == "real" else ATTACK_BY_CHANNEL.get(channel, channel),
        "safe_response": True,
    }


def _control_matches(field: str, expected: Any, scenario: Dict[str, Any], case: Dict[str, Any]) -> bool:
    if field == "attack_type":
        actual = str(scenario.get("attack_type", "")).lower()
        return actual == str(expected).lower()
    if field == "safe_response":
        return _has_safe_response(scenario)
    actual = scenario.get(field)
    if actual is None and field == "difficulty_band":
        actual = scenario.get("difficulty")
    return str(actual).lower() == str(expected).lower()


def concept_f1_score(raw: Dict[str, Any], scenario: Dict[str, Any], case: Dict[str, Any]) -> Tuple[float, float, float, List[str], List[str]]:
    """Return the legacy method-conditioned concept diagnostic.

    This function is retained for backward compatibility. Its reference set may
    include ontology-packet concepts and its generated set may include provenance
    traces. It must therefore not be used as the primary cross-method F1.
    """

    required = required_concepts(raw, scenario, case)
    generated = generated_concepts(scenario)
    return _concept_prf(required, generated)


def common_case_concept_score(
    scenario: Dict[str, Any], case: Dict[str, Any]
) -> Tuple[float, float, float, List[str], List[str]]:
    """Score every method against the same case-derived concept oracle.

    The reference set is fixed by the frozen case controls and variant for all
    four methods. Only player-facing scenario fields are scored; retrieval,
    ontology, and provenance traces are deliberately excluded. Precision,
    recall, and F1 use their standard formulas, while the oracle construction is
    a project-specific operationalization that must be reported as such.
    """

    required = common_case_required_concepts(scenario, case)
    generated = common_case_predicted_concepts(scenario)
    return _closed_label_prf(required, generated)


def _closed_label_prf(
    required: Sequence[str], generated: Sequence[str]
) -> Tuple[float, float, float, List[str], List[str]]:
    """Compute exact set-based P/R/F1 over the disclosed label vocabulary."""

    required_by_key = {str(value).strip().lower(): str(value) for value in required if str(value).strip()}
    generated_keys = {str(value).strip().lower() for value in generated if str(value).strip()}
    if not required_by_key:
        return 1.0, 1.0, 1.0, [], []
    true_positive_keys = set(required_by_key) & generated_keys
    matched = [required_by_key[key] for key in required_by_key if key in true_positive_keys]
    missing = [required_by_key[key] for key in required_by_key if key not in true_positive_keys]
    precision = len(true_positive_keys) / len(generated_keys) if generated_keys else 0.0
    recall = len(true_positive_keys) / len(required_by_key)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1, matched, missing


def _concept_prf(
    required: Sequence[str], generated: Sequence[str]
) -> Tuple[float, float, float, List[str], List[str]]:
    if not required:
        return 1.0, 1.0, 1.0, [], []
    matched: List[str] = []
    missing: List[str] = []
    generated_token_sets = [_tokenize(item) for item in generated]
    for concept in required:
        concept_tokens = _tokenize(concept)
        if not concept_tokens:
            continue
        if any(_concept_matches(concept_tokens, generated_tokens) for generated_tokens in generated_token_sets):
            matched.append(concept)
        else:
            missing.append(concept)
    recall = len(matched) / max(1, len(matched) + len(missing))
    generated_matched = 0
    required_token_sets = [_tokenize(item) for item in required]
    for generated_tokens in generated_token_sets:
        if generated_tokens and any(_concept_matches(required_tokens, generated_tokens) for required_tokens in required_token_sets):
            generated_matched += 1
    precision = generated_matched / max(1, len(generated_token_sets))
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1, matched, missing


def common_case_required_concepts(scenario: Dict[str, Any], case: Dict[str, Any]) -> List[str]:
    """Build the method-invariant oracle from the frozen case specification."""

    controls = expected_controls(case, scenario)
    concepts: List[str] = []
    for field in ("attack_type", "channel", "variant", "role"):
        value = controls.get(field)
        if value:
            concepts.append(str(value))
    if controls.get("variant") == "fake":
        concepts.extend(["red flag", "safe defensive action", "verification", "persuasion cue"])
    else:
        concepts.extend(["safe indicator", "legitimate workflow", "safe defensive action", "verification"])
    return _dedupe(concepts)


def common_case_predicted_concepts(scenario: Dict[str, Any]) -> List[str]:
    """Extract predictions in the same closed label vocabulary as the oracle.

    Values for attack type, channel, variant, and role come from their structured
    output fields. The four defensive/learning labels are derived through
    disclosed deterministic presence rules. Arbitrary prose chunks are not
    counted as false-positive concepts.
    """

    concepts: List[str] = []
    for field in ("attack_type", "channel", "variant", "role"):
        if scenario.get(field):
            concepts.append(str(scenario[field]))

    action, _structured_safe = _correct_action_evidence(scenario)
    red_flags = scenario.get("red_flags") or []
    safe_indicators = scenario.get("safe_indicators") or []
    attack_tactics = scenario.get("attack_tactics") or []
    psych_triggers = scenario.get("psych_triggers") or []
    if red_flags:
        concepts.append("red flag")
    if safe_indicators:
        concepts.append("safe indicator")
    if _has_safe_response(scenario):
        concepts.append("safe defensive action")
    if any(term in action for term in VERIFICATION_TERMS):
        concepts.append("verification")
    if attack_tactics or psych_triggers:
        concepts.append("persuasion cue")
    if str(scenario.get("variant", "")).lower() == "real" and str(scenario.get("attack_type", "")).lower() == "legitimate":
        concepts.append("legitimate workflow")
    return _dedupe(concepts)


def required_concepts(raw: Dict[str, Any], scenario: Dict[str, Any], case: Dict[str, Any]) -> List[str]:
    packet = raw.get("semantic_packet") or scenario.get("generation_meta", {}).get("ontology_trace") or {}
    concepts: List[str] = []
    controls = expected_controls(case, scenario)
    for field in ("attack_type", "channel", "variant", "role"):
        value = controls.get(field)
        if value:
            concepts.append(str(value))
    if controls.get("variant") == "fake":
        concepts.extend(["red flag", "safe defensive action", "verification", "persuasion cue"])
    else:
        concepts.extend(["safe indicator", "legitimate workflow", "verification"])
    for item in packet.get("must_include", []) if isinstance(packet, dict) else []:
        if isinstance(item, str):
            concepts.append(item.replace("=", " "))
    for item in packet.get("evidence_sources", []) if isinstance(packet, dict) else []:
        if isinstance(item, dict):
            concepts.extend(str(item.get(key, "")) for key in ("id", "label") if item.get(key))
    return _dedupe(concepts)


def generated_concepts(scenario: Dict[str, Any]) -> List[str]:
    """Return legacy generated concepts, including provenance traces."""

    concepts = player_facing_generated_concepts(scenario)
    meta = scenario.get("generation_meta") or {}
    for item in meta.get("rag_trace") or []:
        if isinstance(item, dict):
            concepts.extend(str(item.get(key, "")) for key in ("source_file", "source_dataset", "text_preview") if item.get(key))
    packet = meta.get("ontology_trace") or {}
    for item in packet.get("evidence_sources", []) if isinstance(packet, dict) else []:
        if isinstance(item, dict):
            concepts.extend(str(item.get(key, "")) for key in ("id", "label", "definition") if item.get(key))
    return _dedupe(concepts)


def player_facing_generated_concepts(scenario: Dict[str, Any]) -> List[str]:
    """Return scenario content visible to the learner, excluding method traces."""

    concepts: List[str] = []
    for field in (
        "attack_type",
        "channel",
        "variant",
        "role",
        "correct_action",
        "title",
        "opening_hook",
        "sender_or_caller",
    ):
        if scenario.get(field):
            concepts.append(str(scenario[field]))
    for list_field in (
        "red_flags",
        "safe_indicators",
        "attack_tactics",
        "psych_triggers",
        "learning_focus",
        "referenced_entities",
    ):
        values = scenario.get(list_field) or []
        if isinstance(values, list):
            concepts.extend(str(value) for value in values if value)
    for choice in scenario.get("game_choices") or []:
        if isinstance(choice, dict):
            concepts.extend(str(choice.get(key, "")) for key in ("label", "feedback", "outcome") if choice.get(key))
    return _dedupe(concepts)


def grounding_completeness_score(raw: Dict[str, Any], scenario: Dict[str, Any]) -> Tuple[float, List[str], List[str]]:
    present: List[str] = []
    missing: List[str] = []
    evidence = _evidence_payloads(raw, scenario)
    meta = scenario.get("generation_meta") if isinstance(scenario.get("generation_meta"), dict) else {}
    retrieval_mode = scenario.get("retrieval_mode") or raw.get("case", {}).get("retrieval_mode")
    checks = {
        "source_id": any(item.get("id") or item.get("source_file") for item in evidence),
        "source_title": any(item.get("label") or item.get("source_dataset") or item.get("source_file") for item in evidence),
        "evidence_role": bool(evidence) or bool(meta.get("grounding_mode")),
        "provenance_record": bool(meta) or bool(raw.get("semantic_packet", {}).get("provenance", {})),
        "retrieval_mode": bool(retrieval_mode),
        "source_record_id": any(item.get("source_file") or item.get("source_record_id") or item.get("id") for item in evidence),
    }
    for field in GROUNDING_FIELDS:
        if checks.get(field):
            present.append(field)
        else:
            missing.append(field)
    return len(present) / len(GROUNDING_FIELDS), present, missing


def ontology_semantic_scope_score(raw: Dict[str, Any], scenario: Dict[str, Any], case: Dict[str, Any]) -> float:
    """Return the project-defined ontology-trace and control-conformance diagnostic.

    This is not an ontology or knowledge-graph embedding, a learned representation,
    a reasoner score, or a universal semantic-quality metric. It combines trace-field
    presence, frozen-case control adherence, and a rule-based contradiction check.
    """

    meta = scenario.get("generation_meta") if isinstance(scenario.get("generation_meta"), dict) else {}
    text_trace = meta.get("ontology_text_trace") if isinstance(meta.get("ontology_text_trace"), dict) else {}
    packet = raw.get("semantic_packet") or meta.get("ontology_trace") or {}
    document_types = set(text_trace.get("graph_text_strategy", []))
    doc_type_values = {
        str(doc.get("document_type", ""))
        for doc in text_trace.get("documents", [])
        if isinstance(doc, dict)
    }
    source_ids = text_trace.get("source_ids") or []
    checks = [
        bool(packet or text_trace),
        bool(packet.get("selected_templates") if isinstance(packet, dict) else False) or "scenario_template" in doc_type_values,
        bool(packet.get("required_rules") if isinstance(packet, dict) else False) or "validation_rule" in doc_type_values,
        bool(packet.get("evidence_sources") if isinstance(packet, dict) else False) or "evidence_source" in doc_type_values,
        bool(source_ids) or bool(packet.get("evidence_sources") if isinstance(packet, dict) else False),
        "graph_chain_of_thought_reasoning_interaction_execution" in document_types or "graph_cot_trace" in doc_type_values,
    ]
    control_score, _ = control_adherence_score(scenario, case)
    non_contradiction = 1.0 if contradiction_check(scenario, case)[0] == 0 else 0.0
    structural_score = sum(1 for item in checks if item) / len(checks)
    return round(0.60 * structural_score + 0.25 * control_score + 0.15 * non_contradiction, 6)


def generation_timing(raw: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Extract direct LLM timing telemetry when available."""

    prompt_meta = raw.get("prompt_metadata") if isinstance(raw.get("prompt_metadata"), dict) else {}
    nested_prompt_meta = (
        scenario.get("generation_meta", {}).get("prompt_metadata", {})
        if isinstance(scenario.get("generation_meta"), dict)
        else {}
    )
    info = prompt_meta.get("live_llm_call_info") or nested_prompt_meta.get("live_llm_call_info") or {}
    attempts = info.get("attempts") if isinstance(info, dict) else None
    if isinstance(attempts, list) and attempts:
        duration = sum(float(item.get("duration_seconds") or 0.0) for item in attempts if isinstance(item, dict))
        raw_chars = attempts[-1].get("raw_text_chars") if isinstance(attempts[-1], dict) else None
        return {
            "generation_seconds": duration or None,
            "raw_text_chars": raw_chars,
            "parse_retry_count": max(0, len(attempts) - 1),
        }
    if isinstance(info, dict) and info.get("duration_seconds") is not None:
        return {
            "generation_seconds": float(info.get("duration_seconds")),
            "raw_text_chars": info.get("raw_text_chars"),
            "parse_retry_count": int(info.get("parse_retry_index") or 0),
        }
    return {"generation_seconds": None, "raw_text_chars": None, "parse_retry_count": 0}


def contradiction_check(scenario: Dict[str, Any], case: Dict[str, Any]) -> Tuple[int, List[str]]:
    reasons: List[str] = []
    channel = str(case.get("channel", scenario.get("channel", ""))).lower()
    variant = str(case.get("variant", scenario.get("variant", ""))).lower()
    attack_type = str(scenario.get("attack_type", "")).lower()
    expected_attack = "legitimate" if variant == "real" else ATTACK_BY_CHANNEL.get(channel, channel)
    if attack_type != expected_attack:
        reasons.append(f"wrong_attack_type expected={expected_attack} actual={attack_type}")
    red_flags = scenario.get("red_flags") or []
    safe_indicators = scenario.get("safe_indicators") or []
    attack_tactics = scenario.get("attack_tactics") or []
    psych_triggers = scenario.get("psych_triggers") or []
    if variant == "fake" and not red_flags and safe_indicators:
        reasons.append("fake_scenario_has_safe_indicators_only")
    if variant == "real" and (red_flags or attack_tactics or psych_triggers or scenario.get("malicious_url")):
        reasons.append("real_scenario_contains_malicious_or_red_flag_content")
    action, _structured_safe = _correct_action_evidence(scenario)
    if any(term in action for term in UNSAFE_ACTION_TERMS):
        reasons.append("unsafe_correct_action")
    if variant == "fake" and not _has_safe_response(scenario):
        reasons.append("missing_independent_verification_or_reporting")
    return (1 if reasons else 0), reasons


def _correct_action_evidence(scenario: Dict[str, Any]) -> Tuple[str, bool]:
    """Return text from the declared action and correct choice only."""

    parts = [str(scenario.get("correct_action", ""))]
    structured_safe = False
    for choice in scenario.get("game_choices") or []:
        if not isinstance(choice, dict) or not bool(choice.get("is_correct")):
            continue
        parts.extend(str(choice.get(field, "")) for field in ("label", "feedback", "outcome"))
        if str(choice.get("outcome", "")).strip().lower() == "safe":
            structured_safe = True
    return " ".join(parts).lower(), structured_safe


def _has_safe_response(scenario: Dict[str, Any]) -> bool:
    action, structured_safe = _correct_action_evidence(scenario)
    if any(term in action for term in UNSAFE_ACTION_TERMS):
        return False
    return structured_safe or any(term in action for term in SAFE_ACTION_TERMS)


def overall_conformance(
    *,
    json_validity: float,
    control_adherence: float,
    required_concept_f1: float,
    grounding_completeness: float,
    contradiction: int,
) -> float:
    return (
        CONFORMANCE_WEIGHTS["json_validity"] * json_validity
        + CONFORMANCE_WEIGHTS["control_adherence"] * control_adherence
        + CONFORMANCE_WEIGHTS["required_concept_f1"] * required_concept_f1
        + CONFORMANCE_WEIGHTS["grounding_completeness"] * grounding_completeness
        + CONFORMANCE_WEIGHTS["non_contradiction"] * (1 - contradiction)
    )


def _attach_observed_interarrival_seconds(scores: Sequence[ScenarioScore]) -> None:
    """Attach timestamp-delta timing estimates for older runs without per-call telemetry."""

    by_file: Dict[str, List[ScenarioScore]] = {}
    for score in scores:
        by_file.setdefault(score.source_file, []).append(score)
    # Timestamp values are embedded in scenario rows, so reload only the needed field.
    raw_by_key: Dict[Tuple[str, int], datetime] = {}
    # This function intentionally keeps missing timestamps as None; direct LLM telemetry
    # is preferred whenever available.
    for group in by_file.values():
        previous_time: datetime | None = None
        previous_score: ScenarioScore | None = None
        for score in sorted(group, key=lambda item: item.line_number):
            timestamp = _scenario_timestamp_from_score(score)
            if previous_time is not None and timestamp is not None and previous_score is not None:
                delta = (timestamp - previous_time).total_seconds()
                if 0 < delta <= 7200 and score.generation_seconds is None:
                    score.observed_interarrival_seconds = delta
            previous_time = timestamp
            previous_score = score


def _scenario_timestamp_from_score(score: ScenarioScore) -> datetime | None:
    # The score dataclass does not keep raw records. Re-open by source line for
    # older-format timing only.
    try:
        with open(score.source_file, "r", encoding="utf-8") as handle:
            for current_line, line in enumerate(handle, start=1):
                if current_line == score.line_number:
                    import json

                    raw = json.loads(line)
                    scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
                    stamp = scenario.get("generation_timestamp")
                    if stamp:
                        return datetime.fromisoformat(str(stamp))
                    return None
    except Exception:
        return None
    return None


def _has_evidence(raw: Dict[str, Any], scenario: Dict[str, Any]) -> bool:
    return bool(_evidence_payloads(raw, scenario))


def _evidence_payloads(raw: Dict[str, Any], scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []
    for item in raw.get("rag_examples") or []:
        if isinstance(item, dict):
            payloads.append(item)
    packet = raw.get("semantic_packet") or scenario.get("generation_meta", {}).get("ontology_trace") or {}
    if isinstance(packet, dict):
        for item in packet.get("evidence_sources") or []:
            if isinstance(item, dict):
                payloads.append(item)
    meta = scenario.get("generation_meta") or {}
    for item in meta.get("rag_trace") or []:
        if isinstance(item, dict):
            payloads.append(item)
    return payloads


def _tokenize(text: str) -> Set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text or "") if len(token) > 2 and token.lower() not in STOPWORDS}


def _concept_matches(required_tokens: Set[str], generated_tokens: Set[str]) -> bool:
    if not required_tokens or not generated_tokens:
        return False
    if required_tokens <= generated_tokens:
        return True
    overlap = required_tokens & generated_tokens
    return len(overlap) / len(required_tokens) >= 0.5


def _dedupe(values: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(text)
    return out
