
"""
PersonaShield Quest — Pydantic Schemas (v4.3)
=============================================
Stage-aware multilingual bundle architecture plus formal game-system config.
Adds quality, repair, and evaluation metadata for generated scenarios.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

RoleType = Literal["IT", "FINANCE", "HR", "MANAGEMENT", "OTHER"]
ChannelType = Literal["sms", "email", "voice"]
VariantType = Literal["fake", "real"]
KnowledgeType = Literal["factual", "conceptual", "procedural", "metacognitive"]
RetrievalModeType = Literal["THAI_LOCAL", "ENGLISH_GLOBAL", "HYBRID_COMPARE"]
LanguageType = Literal["en", "th"]
PromptMethodType = Literal["zero_shot", "few_shot", "cot", "tot", "scot"]


class PlacementOption(BaseModel):
    key: str
    label: str
    points: int = Field(..., ge=0, le=4)


class PlacementQuestion(BaseModel):
    question_id: str
    prompt: str
    dimension: str
    options: List[PlacementOption] = Field(default_factory=list)


class PlacementStageBand(BaseModel):
    min_score: int
    max_score: int
    stage_id: str


class PlacementTestConfig(BaseModel):
    questions: List[PlacementQuestion] = Field(default_factory=list)
    stage_bands: List[PlacementStageBand] = Field(default_factory=list)
    scoring_note: str


class LoopGate(BaseModel):
    accuracy_min: float = Field(..., ge=0.0, le=1.0)
    behavior_min: float = Field(..., ge=0.0, le=1.0)
    speed_min: float = Field(..., ge=0.0, le=1.0)
    safe_choice_rate_min: float = Field(..., ge=0.0, le=1.0)


class LoopPolicy(BaseModel):
    loop_name: str
    window_scenarios: int = Field(..., ge=1)
    goal: str
    promotion_gate: LoopGate
    failure_response: Dict[str, Any] = Field(default_factory=dict)
    completion_rule: Optional[str] = None


class GameSystemConfig(BaseModel):
    version: str = "v4.1"
    placement_test: PlacementTestConfig
    training_loop: LoopPolicy
    mastery_loop: LoopPolicy
    regression_policy: Dict[str, Any] = Field(default_factory=dict)
    stage_order: List[str] = Field(default_factory=list)
    next_stage_map: Dict[str, Optional[str]] = Field(default_factory=dict)
    previous_stage_map: Dict[str, Optional[str]] = Field(default_factory=dict)
    path_formula: str


class GSDLDescriptor(BaseModel):
    persona_id: str
    persona_path_id: str
    role: RoleType
    stage_id: str
    macro_stage: str
    micro_stage: str
    stage_index: int = Field(..., ge=1, le=9)
    age_group: str
    age_group_code: str
    language_mode: LanguageType
    retrieval_mode: RetrievalModeType
    vocabulary_band: str
    knowledge_type: KnowledgeType
    interaction_pattern: str
    difficulty_label: str
    difficulty_band: str
    time_pressure: str
    pressure_level: str
    deception_depth: str
    red_flags_visible: str
    hint_policy: str
    suitable_channels: List[ChannelType] = Field(default_factory=lambda: ["sms", "email", "voice"])
    attack_tactics: List[str] = Field(default_factory=list)
    psych_triggers: List[str] = Field(default_factory=list)
    regression_policy: Dict[str, Any] = Field(default_factory=dict)


class PersonaProfile(BaseModel):
    persona_id: str
    persona_path_id: str
    role: RoleType
    stage_id: str
    macro_stage: str
    micro_stage: str
    stage_index: int = Field(..., ge=1, le=9)
    age_group: str
    age_group_code: str
    age_group_name: str
    language_mode: LanguageType
    retrieval_mode: RetrievalModeType
    vocabulary_band: str
    knowledge_type: KnowledgeType
    digital_familiarity_profile: Optional[str] = None
    full_name: str = Field(..., min_length=2)
    job_title: str = Field(..., min_length=2)
    department: str = Field(..., min_length=2)
    company_name: str = Field(..., min_length=2)
    company_domain: str = Field(..., min_length=4)
    company_email: str
    manager_name: str = Field(..., min_length=2)
    manager_title: str = Field(..., min_length=2)
    manager_email: str
    tools: List[str] = Field(..., min_length=2)
    daily_tasks: List[str] = Field(..., min_length=2)
    trusted_contacts: List[str] = Field(default_factory=list)
    trusted_numbers: List[str] = Field(default_factory=list)
    policy_rules: List[str] = Field(default_factory=list)
    story_summary: str = Field(..., min_length=20)
    work_context: str = Field(..., min_length=20)
    age_context_notes: str = Field(..., min_length=10)

    @field_validator("company_email", "manager_email")
    @classmethod
    def validate_email_shape(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("must look like an email address")
        return v.lower().strip()

    @field_validator("tools", "daily_tasks", "trusted_contacts", "trusted_numbers", "policy_rules", mode="before")
    @classmethod
    def split_single_csv_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, list) and len(v) == 1 and isinstance(v[0], str) and "," in v[0]:
            return [x.strip() for x in v[0].split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def domain_match(self) -> "PersonaProfile":
        if self.company_domain not in self.company_email:
            raise ValueError("company_email must use company_domain")
        if self.company_domain not in self.manager_email:
            raise ValueError("manager_email must use company_domain")
        return self


class LearningCriteria(BaseModel):
    stage_id: str
    macro_stage: str
    micro_stage: str
    age_group: str
    language_mode: LanguageType
    retrieval_mode: RetrievalModeType
    vocabulary_band: str
    knowledge_type: KnowledgeType
    interaction_pattern: str
    learning_objectives: List[str] = Field(default_factory=list)
    teach_red_flags: List[str] = Field(default_factory=list)
    teach_safe_indicators: List[str] = Field(default_factory=list)
    development_focus: str
    difficulty_label: str
    difficulty_band: str
    gameplay_style: str
    hint_policy: str
    time_pressure_label: str
    pressure_level: str
    prompt_method: PromptMethodType


class ChoiceOption(BaseModel):
    key: str
    label: str
    is_correct: bool = False
    outcome: Literal["safe", "unsafe", "neutral"]
    feedback: str = Field(..., min_length=5)


class ScenarioContent(BaseModel):
    scenario_id: str
    persona_id: str
    persona_path_id: str
    role: RoleType
    stage_id: str
    macro_stage: str
    micro_stage: str
    stage_index: int = Field(..., ge=1, le=9)
    age_group: str
    age_group_code: str
    language_mode: LanguageType
    retrieval_mode: RetrievalModeType
    vocabulary_band: str
    knowledge_type: KnowledgeType
    interaction_pattern: str
    prompt_method: PromptMethodType
    channel: ChannelType
    attack_type: str
    variant: VariantType
    title: str = Field(..., min_length=3)
    opening_hook: str = Field(..., min_length=10)
    sender_or_caller: str = Field(..., min_length=2)
    messages: List[str] = Field(default_factory=list)
    malicious_url: Optional[str] = None
    from_address: Optional[str] = None
    from_display_name: Optional[str] = None
    to_role_hint: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    has_attachment: bool = False
    attachment_name: Optional[str] = None
    legitimate_url: Optional[str] = None
    caller_id: Optional[str] = None
    caller_persona: Optional[str] = None
    dialogue: List[Dict[str, str]] = Field(default_factory=list)
    attack_tactics: List[str] = Field(default_factory=list)
    psych_triggers: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    safe_indicators: List[str] = Field(default_factory=list)
    correct_action: str = Field(..., min_length=10)
    learning_focus: List[str] = Field(default_factory=list)
    referenced_entities: List[str] = Field(default_factory=list)
    game_choices: List[ChoiceOption] = Field(default_factory=list)
    difficulty_band: Optional[str] = None
    pressure_band: Optional[str] = None
    regression_reason: Optional[str] = None
    score_reward: int = 10
    score_penalty: int = -5
    show_hint: bool = True
    hint_text: Optional[str] = None
    quality_score: float = 0.0
    quality_breakdown: Dict[str, float] = Field(default_factory=dict)
    quality_flags: List[str] = Field(default_factory=list)
    repair_actions: List[str] = Field(default_factory=list)
    diversity_fingerprint: Optional[str] = None
    llm_source: str = ""
    generation_meta: Dict[str, Any] = Field(default_factory=dict)
    generation_timestamp: str = Field(default_factory=lambda: _dt.datetime.now().isoformat())

    @field_validator(
        "messages",
        "attack_tactics",
        "psych_triggers",
        "red_flags",
        "safe_indicators",
        "learning_focus",
        "referenced_entities",
        "quality_flags",
        "repair_actions",
        mode="before",
    )
    @classmethod
    def listify_strings(cls, v: Any) -> Any:
        return [v] if isinstance(v, str) else v

    @field_validator("game_choices", mode="before")
    @classmethod
    def coerce_game_choices(cls, v: Any) -> Any:
        if v is None:
            return []
        result = []
        for item in v:
            if isinstance(item, ChoiceOption):
                result.append(item.model_dump())
            elif isinstance(item, dict):
                result.append(item)
        return result

    @model_validator(mode="after")
    def validate_channel_specific_fields(self) -> "ScenarioContent":
        if self.channel == "sms" and not self.messages:
            raise ValueError("sms scenario requires messages")
        if self.channel == "email" and (not self.subject or not self.body_html or not self.from_address):
            raise ValueError("email scenario requires from_address, subject, and body_html")
        if self.channel == "voice" and len(self.dialogue) < 2:
            raise ValueError("voice scenario requires at least two dialogue turns")
        if self.variant == "fake" and not self.red_flags:
            raise ValueError("fake scenario should include red_flags")
        if self.variant == "real" and not self.safe_indicators:
            raise ValueError("real scenario should include safe_indicators")
        if len(self.game_choices) < 2:
            raise ValueError("scenario requires at least two game_choices")
        return self


class GameplayRules(BaseModel):
    stage_id: str
    macro_stage: str
    micro_stage: str
    vocabulary_band: str
    hint_policy: str
    time_pressure_label: str
    pressure_level: str
    score_reward_correct: int = 10
    score_penalty_incorrect: int = -5
    hint_cost: int = 2
    max_attempts: int = 1
    show_hints: bool = True
    regression_policy: Dict[str, Any] = Field(default_factory=dict)
    training_loop: Dict[str, Any] = Field(default_factory=dict)
    mastery_loop: Dict[str, Any] = Field(default_factory=dict)


class ContentBundle(BaseModel):
    engine_version: str = "v4.3"
    persona_id: str
    persona_path_id: str
    llm_key: str
    llm_description: str
    persona_profile: PersonaProfile
    gsdl_descriptor: GSDLDescriptor
    learning_criteria: LearningCriteria
    gameplay_rules: GameplayRules
    game_system: Optional[GameSystemConfig] = None
    scenario_pool: List[ScenarioContent] = Field(default_factory=list)
    generation_notes: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: _dt.datetime.now().isoformat())

    def is_complete(self) -> bool:
        required = {
            ("sms", "fake"),
            ("sms", "real"),
            ("email", "fake"),
            ("email", "real"),
            ("voice", "fake"),
            ("voice", "real"),
        }
        present = {(s.channel, s.variant) for s in self.scenario_pool}
        return required.issubset(present)

    def missing_slots(self) -> List[tuple]:
        required = [
            ("sms", "fake"),
            ("sms", "real"),
            ("email", "fake"),
            ("email", "real"),
            ("voice", "fake"),
            ("voice", "real"),
        ]
        present = {(s.channel, s.variant) for s in self.scenario_pool}
        return [(ch, var) for ch, var in required if (ch, var) not in present]

    def get_scenario(self, channel: str, variant: str) -> Optional[ScenarioContent]:
        for scenario in self.scenario_pool:
            if scenario.channel == channel and scenario.variant == variant:
                return scenario
        return None


class ScenarioPoolEntry(BaseModel):
    scenario_id: str
    persona_id: str
    persona_path_id: str
    llm_key: str
    channel: ChannelType
    variant: VariantType
    payload: ScenarioContent
