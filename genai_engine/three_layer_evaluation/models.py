"""Shared dataclasses and constants for the three-layer evaluator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


METHOD_ORDER = ("prompt_only", "prompt_rag", "ontology_prompt_rag", "ontology_text_rag")
METHOD_CONDITION_NUMBERS = {
    "prompt_only": 1,
    "prompt_rag": 2,
    "ontology_prompt_rag": 3,
    "ontology_text_rag": 4,
}
METHOD_LABELS = {
    "prompt_only": "Prompt-Only Generation",
    "prompt_rag": "Text-RAG Generation",
    "ontology_prompt_rag": "Ontology-Derived Structured Prompting RAG",
    "ontology_text_rag": "Ontology-to-Text Vector RAG",
}
METHOD_IMPLEMENTATION_NOTES = {
    "prompt_only": "No external retrieval and no ontology-derived context.",
    "prompt_rag": "Attempts external Chroma vector retrieval; actual context exposure is audited per row.",
    "ontology_prompt_rag": "Attempts external RAG and adds a directly serialized PSQ-SCO semantic packet.",
    "ontology_text_rag": (
        "Attempts external Chroma vector retrieval and adds ontology-derived text selected by a deterministic "
        "lexical ranker; actual external-context exposure is audited per row, and the ontology-derived records "
        "are not embedded by the current implementation."
    ),
}

ATTACK_BY_CHANNEL = {
    "email": "phishing",
    "sms": "smishing",
    "voice": "vishing",
}

CONTROL_FIELDS = (
    "role",
    "age_group_code",
    "stage_id",
    "channel",
    "variant",
    "difficulty_band",
    "attack_type",
    "safe_response",
)

SCENARIO_REQUIRED_FIELDS = (
    "scenario_id",
    "channel",
    "variant",
    "game_choices",
    "correct_action",
)

GROUNDING_FIELDS = (
    "source_id",
    "source_title",
    "evidence_role",
    "provenance_record",
    "retrieval_mode",
    "source_record_id",
)

CONFORMANCE_WEIGHTS = {
    "json_validity": 0.20,
    "control_adherence": 0.25,
    "required_concept_f1": 0.25,
    "grounding_completeness": 0.20,
    "non_contradiction": 0.10,
}


@dataclass
class ScenarioRecord:
    """One generated scenario row loaded from JSONL output."""

    source_file: str
    line_number: int
    raw: Dict[str, Any]
    parse_error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioScore:
    """Scenario-level validation metrics."""

    source_file: str
    line_number: int
    case_id: str
    scenario_id: str
    model_key: str
    model_name: str
    method: str
    role: str
    stage_id: str
    age_group_code: str
    channel: str
    variant: str
    json_validity: float
    control_adherence: float
    required_concept_precision: float
    required_concept_recall: float
    required_concept_f1: float
    grounding_completeness: float
    contradiction: int
    condition_number: int = 0
    condition_name: str = ""
    game_schema_completeness: float = 0.0
    game_schema_complete_pass: int = 0
    automated_decision: str = ""
    decision_scope: str = "automated_technical_triage_only"
    decision_policy_version: str = "technical_gate_v1"
    final_human_review_required: bool = True
    common_case_concept_precision: float = 0.0
    common_case_concept_recall: float = 0.0
    common_case_concept_f1: float = 0.0
    json_parse_pass: int = 0
    schema_complete_pass: int = 0
    all_controls_exact_match: int = 0
    trace_complete_pass: int = 0
    contradiction_free_pass: int = 0
    schema_completeness: float = 0.0
    ontology_semantic_scope: float = 0.0
    used_live_llm: bool = False
    used_fallback: bool = False
    schema_safe_repair_used: bool = False
    live_model_content_retained: bool = False
    generation_integrity_status: str = ""
    engine_validation_passed: Optional[bool] = None
    engine_validation_issue_count: int = 0
    generation_seconds: Optional[float] = None
    observed_interarrival_seconds: Optional[float] = None
    raw_text_chars: Optional[int] = None
    parse_retry_count: int = 0
    contradiction_reasons: List[str] = field(default_factory=list)
    overall_conformance: float = 0.0
    missing_required_fields: List[str] = field(default_factory=list)
    failed_control_fields: List[str] = field(default_factory=list)
    matched_required_concepts: List[str] = field(default_factory=list)
    missing_required_concepts: List[str] = field(default_factory=list)
    grounding_fields_present: List[str] = field(default_factory=list)
    grounding_fields_missing: List[str] = field(default_factory=list)
    common_case_concepts_matched: List[str] = field(default_factory=list)
    common_case_concepts_missing: List[str] = field(default_factory=list)
    decision_reason_codes: List[str] = field(default_factory=list)
    revision_guidance: List[str] = field(default_factory=list)
    engine_validation_issues: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for key in (
            "contradiction_reasons",
            "missing_required_fields",
            "failed_control_fields",
            "matched_required_concepts",
            "missing_required_concepts",
            "grounding_fields_present",
            "grounding_fields_missing",
            "common_case_concepts_matched",
            "common_case_concepts_missing",
            "decision_reason_codes",
            "revision_guidance",
            "engine_validation_issues",
        ):
            payload[key] = "; ".join(payload[key])
        return payload


@dataclass
class OntologyValidationResult:
    """Ontology-level validation metrics."""

    ontology_path: str
    query_dir: str
    reasoner_consistency: Optional[bool]
    reasoner_status: str
    unsatisfiable_class_count: Optional[int]
    cq_passed: int
    cq_total: int
    mapping_passed: int
    mapping_total: int
    runtime_records_preserved: int
    class_count: int
    named_individual_count: int
    object_property_count: int
    datatype_property_count: int
    notes: List[str] = field(default_factory=list)

    @property
    def cq_pass_rate(self) -> Optional[float]:
        return self.cq_passed / self.cq_total if self.cq_total else None

    @property
    def mapping_pass_rate(self) -> Optional[float]:
        return self.mapping_passed / self.mapping_total if self.mapping_total else None

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["cq_pass_rate"] = self.cq_pass_rate
        payload["mapping_pass_rate"] = self.mapping_pass_rate
        return payload
