
"""
PersonaShield Quest — Central Configuration (v4.1)
==================================================
Stage-aware multilingual generation engine with formal game-system metadata.

Key additions in v4.1
- Adds the 5th occupation role: HR
- Keeps the 9-stage progression ladder
- Formalizes placement-test scoring bands for start-stage assignment
- Formalizes training-loop and mastery-loop progression metadata
- Exposes exact content-count expectations:
  5 roles × 9 stages × 5 age groups × 3 channels × 2 variants = 1,350 scenarios
  per LLM per retrieval mode (Thai-local OR English-global)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
BUNDLE_DIR = PROJECT_ROOT / "content_bundles"
POOL_DIR = PROJECT_ROOT / "scenario_pool"
KB_DIR = Path(os.getenv("PSQ_KB_DIR", str(PROJECT_ROOT / "output")))
LOG_DIR = PROJECT_ROOT / "logs"
for _p in (BUNDLE_DIR, POOL_DIR, LOG_DIR):
    _p.mkdir(parents=True, exist_ok=True)

ROLES = ["IT", "FINANCE", "HR", "MANAGEMENT", "OTHER"]
CHANNELS = ["sms", "email", "voice"]
VARIANTS = ["fake", "real"]
SUPPORTED_LANGUAGES = ["en", "th"]

RETRIEVAL_MODES = ["THAI_LOCAL", "ENGLISH_GLOBAL", "HYBRID_COMPARE"]
PRODUCTION_RETRIEVAL_MODES = ["THAI_LOCAL", "ENGLISH_GLOBAL"]

PROMPT_METHODS = ["zero_shot", "few_shot", "cot", "tot", "scot"]
ATTACK_CHANNEL_MAP = {"sms": "smishing", "email": "phishing", "voice": "vishing"}

VOCAB_BANDS = {
    "V1_FOUNDATION": {
        "label": "V1 Foundation",
        "sentence_profile": "short",
        "jargon_density": "very_low",
        "explicitness": "high",
        "ambiguity": "low",
        "validator_min_avg_words": 0,
        "validator_max_avg_words": 22,
    },
    "V2_GUIDED": {
        "label": "V2 Guided",
        "sentence_profile": "short_to_medium",
        "jargon_density": "low",
        "explicitness": "medium_high",
        "ambiguity": "low_to_mild",
        "validator_min_avg_words": 5,
        "validator_max_avg_words": 28,
    },
    "V3_APPLIED": {
        "label": "V3 Applied",
        "sentence_profile": "medium",
        "jargon_density": "moderate",
        "explicitness": "medium",
        "ambiguity": "moderate",
        "validator_min_avg_words": 7,
        "validator_max_avg_words": 34,
    },
    "V4_PROFESSIONAL": {
        "label": "V4 Professional",
        "sentence_profile": "medium_to_long",
        "jargon_density": "moderate_to_high",
        "explicitness": "lower",
        "ambiguity": "moderate_to_high",
        "validator_min_avg_words": 8,
        "validator_max_avg_words": 42,
    },
    "V5_STRATEGIC": {
        "label": "V5 Strategic",
        "sentence_profile": "medium_to_long",
        "jargon_density": "high",
        "explicitness": "lower",
        "ambiguity": "high",
        "validator_min_avg_words": 10,
        "validator_max_avg_words": 60,
    },
}

KNOWLEDGE_RATIO_TARGETS: Dict[str, float] = {
    "factual": 0.15,
    "conceptual": 0.25,
    "procedural": 0.40,
    "metacognitive": 0.20,
}

ROLE_FROM_GAME = {
    "IT": "IT",
    "Finance": "FINANCE",
    "HR": "HR",
    "Human Resources": "HR",
    "Management": "MANAGEMENT",
    "Other": "OTHER",
    "finance": "FINANCE",
    "hr": "HR",
    "human resources": "HR",
    "management": "MANAGEMENT",
    "other": "OTHER",
}

STAGE_FROM_GAME = {
    "Beginner": "BEGINNER_INTRODUCTORY",
    "Intermediate": "INTERMEDIATE_INTRODUCTORY",
    "Expert": "EXPERT_INTRODUCTORY",
    "beginner": "BEGINNER_INTRODUCTORY",
    "intermediate": "INTERMEDIATE_INTRODUCTORY",
    "expert": "EXPERT_INTRODUCTORY",
}

MACRO_STAGE_SHORT = {"Beginner": "B", "Intermediate": "I", "Expert": "E"}
MICRO_STAGE_SHORT = {"Introductory": "I", "Developing": "D", "Advanced": "A"}

STAGE_LADDER: List[Dict[str, Any]] = [
    {
        "stage_id": "BEGINNER_INTRODUCTORY",
        "index": 1,
        "macro_stage": "Beginner",
        "micro_stage": "Introductory",
        "vocabulary_band": "V1_FOUNDATION",
        "knowledge_type_default": "factual",
        "interaction_pattern": "Recognize–Explain",
        "development_focus": "Recognize obvious threats, basic terms, explicit cues",
        "difficulty_label": "easy",
        "difficulty_band": "easy",
        "time_pressure_label": "low",
        "pressure_level": "low",
        "deception_depth": "obvious",
        "red_flags_visible": "many",
        "hint_policy": "high",
        "scenario_style": "explicit_labels",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "BEGINNER_DEVELOPING",
        "index": 2,
        "macro_stage": "Beginner",
        "micro_stage": "Developing",
        "vocabulary_band": "V2_GUIDED",
        "knowledge_type_default": "conceptual",
        "interaction_pattern": "Identify–Classify",
        "development_focus": "Identify mixed cues, partial guidance, simple verification",
        "difficulty_label": "easy",
        "difficulty_band": "easy",
        "time_pressure_label": "low",
        "pressure_level": "low_to_mild",
        "deception_depth": "surface",
        "red_flags_visible": "several",
        "hint_policy": "high",
        "scenario_style": "guided_verification",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "BEGINNER_ADVANCED",
        "index": 3,
        "macro_stage": "Beginner",
        "micro_stage": "Advanced",
        "vocabulary_band": "V2_GUIDED",
        "knowledge_type_default": "procedural",
        "interaction_pattern": "Inspect–Verify",
        "development_focus": "Perform basic verification without explicit labels",
        "difficulty_label": "easy_to_moderate",
        "difficulty_band": "easy",
        "time_pressure_label": "low_to_medium",
        "pressure_level": "mild",
        "deception_depth": "shallow_layered",
        "red_flags_visible": "some",
        "hint_policy": "medium_high",
        "scenario_style": "guided_realism",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "INTERMEDIATE_INTRODUCTORY",
        "index": 4,
        "macro_stage": "Intermediate",
        "micro_stage": "Introductory",
        "vocabulary_band": "V3_APPLIED",
        "knowledge_type_default": "conceptual",
        "interaction_pattern": "Identify–Classify",
        "development_focus": "Interpret mild ambiguity and contextual pressure",
        "difficulty_label": "moderate",
        "difficulty_band": "moderate",
        "time_pressure_label": "medium",
        "pressure_level": "mild_to_moderate",
        "deception_depth": "moderate",
        "red_flags_visible": "few",
        "hint_policy": "medium",
        "scenario_style": "contextual_ambiguity",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "INTERMEDIATE_DEVELOPING",
        "index": 5,
        "macro_stage": "Intermediate",
        "micro_stage": "Developing",
        "vocabulary_band": "V3_APPLIED",
        "knowledge_type_default": "procedural",
        "interaction_pattern": "Compare–Choose",
        "development_focus": "Analyze multiple cues and attack vectors",
        "difficulty_label": "moderate",
        "difficulty_band": "moderate",
        "time_pressure_label": "medium",
        "pressure_level": "moderate",
        "deception_depth": "layered",
        "red_flags_visible": "few",
        "hint_policy": "medium",
        "scenario_style": "multi_cue_analysis",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "INTERMEDIATE_ADVANCED",
        "index": 6,
        "macro_stage": "Intermediate",
        "micro_stage": "Advanced",
        "vocabulary_band": "V4_PROFESSIONAL",
        "knowledge_type_default": "procedural",
        "interaction_pattern": "Challenge–Report",
        "development_focus": "Evaluate realistic scenarios under moderate pressure",
        "difficulty_label": "moderate_to_hard",
        "difficulty_band": "moderate",
        "time_pressure_label": "medium_to_high",
        "pressure_level": "moderate",
        "deception_depth": "layered_deep",
        "red_flags_visible": "minimal",
        "hint_policy": "medium_low",
        "scenario_style": "realistic_workflow_pressure",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "EXPERT_INTRODUCTORY",
        "index": 7,
        "macro_stage": "Expert",
        "micro_stage": "Introductory",
        "vocabulary_band": "V4_PROFESSIONAL",
        "knowledge_type_default": "procedural",
        "interaction_pattern": "Inspect–Verify",
        "development_focus": "Handle subtle, high-ambiguity scenarios",
        "difficulty_label": "hard",
        "difficulty_band": "hard",
        "time_pressure_label": "high",
        "pressure_level": "high",
        "deception_depth": "deep",
        "red_flags_visible": "very_few",
        "hint_policy": "low",
        "scenario_style": "subtle_high_ambiguity",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "EXPERT_DEVELOPING",
        "index": 8,
        "macro_stage": "Expert",
        "micro_stage": "Developing",
        "vocabulary_band": "V5_STRATEGIC",
        "knowledge_type_default": "metacognitive",
        "interaction_pattern": "Reflect–Justify",
        "development_focus": "Reflect on near-miss reasoning and decision habits",
        "difficulty_label": "hard",
        "difficulty_band": "hard",
        "time_pressure_label": "high",
        "pressure_level": "high",
        "deception_depth": "sophisticated",
        "red_flags_visible": "almost_none",
        "hint_policy": "low",
        "scenario_style": "near_miss_reflection",
        "prompt_method_default": "scot",
    },
    {
        "stage_id": "EXPERT_ADVANCED",
        "index": 9,
        "macro_stage": "Expert",
        "micro_stage": "Advanced",
        "vocabulary_band": "V5_STRATEGIC",
        "knowledge_type_default": "metacognitive",
        "interaction_pattern": "Design–Respond",
        "development_focus": "Synthesize defensive response and justify decisions",
        "difficulty_label": "hard",
        "difficulty_band": "hard",
        "time_pressure_label": "high",
        "pressure_level": "high",
        "deception_depth": "expert",
        "red_flags_visible": "none",
        "hint_policy": "very_low",
        "scenario_style": "defense_planning",
        "prompt_method_default": "scot",
    },
]
STAGE_BY_ID = {stage["stage_id"]: stage for stage in STAGE_LADDER}
ORDERED_STAGE_IDS = [stage["stage_id"] for stage in STAGE_LADDER]
NEXT_STAGE_MAP = {ORDERED_STAGE_IDS[i]: ORDERED_STAGE_IDS[i + 1] if i + 1 < len(ORDERED_STAGE_IDS) else None for i in range(len(ORDERED_STAGE_IDS))}
PREV_STAGE_MAP = {ORDERED_STAGE_IDS[i]: ORDERED_STAGE_IDS[i - 1] if i - 1 >= 0 else None for i in range(len(ORDERED_STAGE_IDS))}

AGE_GROUPS: List[Dict[str, Any]] = [
    {
        "age_group_code": "15_21",
        "age_group_label": "15–21",
        "learner_group": "Teenagers and young adults",
        "story_style": "Use more educational scaffolding, simpler institutional language, and familiar digital-message framing.",
        "channel_affinity": ["sms", "email", "voice"],
        "digital_familiarity_profile": "high mobile-first familiarity",
    },
    {
        "age_group_code": "22_35",
        "age_group_label": "22–35",
        "learner_group": "Early-career adults",
        "story_style": "Use operational workplace scenarios, moderate pace, and clear task-based verification steps.",
        "channel_affinity": ["sms", "email", "voice"],
        "digital_familiarity_profile": "high digital workplace familiarity",
    },
    {
        "age_group_code": "36_45",
        "age_group_label": "36–45",
        "learner_group": "Mid-career adults",
        "story_style": "Use role accountability, workflow legitimacy, peer coordination, and contextual pressure.",
        "channel_affinity": ["email", "voice", "sms"],
        "digital_familiarity_profile": "mixed but strong workplace-platform familiarity",
    },
    {
        "age_group_code": "46_59",
        "age_group_label": "46–59",
        "learner_group": "Later-career adults",
        "story_style": "Use management responsibility, process compliance, decision justification, and mixed digital/phone contact patterns.",
        "channel_affinity": ["email", "voice", "sms"],
        "digital_familiarity_profile": "mixed digital familiarity with strong process expectations",
    },
    {
        "age_group_code": "60_90",
        "age_group_label": "60–90",
        "learner_group": "Senior adults",
        "story_style": "Use respectful pacing, clear contextual framing, reduced jargon overload, and carefully controlled ambiguity.",
        "channel_affinity": ["voice", "email", "sms"],
        "digital_familiarity_profile": "variable digital familiarity; avoid unnecessary jargon",
    },
]
AGE_GROUP_BY_CODE = {age["age_group_code"]: age for age in AGE_GROUPS}

ROLE_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "IT": {
        "company_type_hint": "software or enterprise technology firm",
        "manager_title_hint": "IT Manager",
        "department_hint": "IT Operations",
        "job_titles": ["IT Support Specialist", "Systems Analyst", "Security Operations Coordinator"],
        "tool_hints": ["Microsoft 365 Admin Center", "Jira Service Management", "endpoint security dashboard", "VPN portal"],
        "task_hints": ["review user access requests", "triage service tickets", "verify MFA issues", "monitor endpoint alerts"],
        "learning_objectives": [
            "Identify spoofed technical requests",
            "Verify links, domains, and sender legitimacy",
            "Escalate suspicious incidents through approved channels",
        ],
        "tactic_pool": ["phishing", "pretexting", "tech_support_scam", "credential_harvesting", "vishing"],
        "role_language_style": "Use operational IT support wording, ticketing language, access-control terms, and system-administration context.",
    },
    "FINANCE": {
        "company_type_hint": "corporate finance, accounting, or payroll environment",
        "manager_title_hint": "Finance Manager",
        "department_hint": "Finance and Accounting",
        "job_titles": ["Finance Officer", "Accounts Payable Specialist", "Payroll Coordinator"],
        "tool_hints": ["ERP finance module", "invoice approval portal", "corporate banking dashboard", "Excel reporting workbook"],
        "task_hints": ["review invoices", "approve reimbursements", "verify vendor details", "prepare payment schedules"],
        "learning_objectives": [
            "Detect invoice and payment fraud indicators",
            "Verify beneficiaries and payment instructions",
            "Pause and escalate unusual urgency or authority claims",
        ],
        "tactic_pool": ["invoice_fraud", "business_email_compromise", "phishing", "vishing", "pretexting"],
        "role_language_style": "Use finance wording such as invoice, vendor, payroll, approval, reimbursement, payment instruction, and audit trail.",
    },
    "HR": {
        "company_type_hint": "human resources, recruitment, people operations, or employee services environment",
        "manager_title_hint": "HR Manager",
        "department_hint": "Human Resources",
        "job_titles": ["HR Officer", "Recruitment Coordinator", "People Operations Specialist"],
        "tool_hints": ["HRIS portal", "recruitment tracking system", "leave approval workflow", "employee records dashboard"],
        "task_hints": ["review employee records", "process leave requests", "coordinate recruitment documents", "verify onboarding forms"],
        "learning_objectives": [
            "Recognize social engineering involving employee data and HR workflows",
            "Verify requests affecting payroll, benefits, leave, or employee records",
            "Protect personal and organizational data through approved procedures",
        ],
        "tactic_pool": ["phishing", "pretexting", "business_email_compromise", "smishing", "vishing"],
        "role_language_style": "Use HR wording such as employee record, leave request, onboarding, payroll coordination, recruitment document, and policy compliance.",
    },
    "MANAGEMENT": {
        "company_type_hint": "mid-size enterprise or professional services organization",
        "manager_title_hint": "Senior Director",
        "department_hint": "Business Operations",
        "job_titles": ["Operations Manager", "Department Manager", "Program Lead"],
        "tool_hints": ["Microsoft Teams", "executive calendar", "approval workflow system", "shared drive"],
        "task_hints": ["approve requests", "coordinate teams", "review reports", "respond to executive messages"],
        "learning_objectives": [
            "Recognize authority-based manipulation",
            "Assess legitimacy under time pressure",
            "Justify defensive choices and reporting steps",
        ],
        "tactic_pool": ["whaling", "business_email_compromise", "pretexting", "vishing", "phishing"],
        "role_language_style": "Use management wording such as approval, escalation, executive coordination, policy impact, delegation, and decision justification.",
    },
    "OTHER": {
        "company_type_hint": "general office, education, service, or administrative environment",
        "manager_title_hint": "Team Lead",
        "department_hint": "Administration",
        "job_titles": ["Administrative Coordinator", "Office Staff Member", "Customer Service Coordinator"],
        "tool_hints": ["email client", "calendar system", "line-of-business web portal", "document approval form"],
        "task_hints": ["coordinate schedules", "respond to messages", "update records", "route internal requests"],
        "learning_objectives": [
            "Recognize suspicious contact patterns",
            "Verify requests through trusted channels",
            "Practice safe response and reporting behavior",
        ],
        "tactic_pool": ["phishing", "smishing", "vishing", "baiting", "pretexting"],
        "role_language_style": "Use clear office-administration wording without heavy specialist jargon.",
    },
}
BLUEPRINTS = ROLE_BLUEPRINTS

PSYCH_TRIGGERS = ["authority", "urgency", "fear", "scarcity", "social_proof", "reciprocity", "curiosity"]

# ---------- Placement test and game-loop rules ----------
PLACEMENT_TEST_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_id": "PT1",
        "prompt": "A message asks you to verify an account quickly. What is the safest first step?",
        "dimension": "verification",
        "options": [
            {"key": "a", "label": "Click immediately because it looks urgent", "points": 0},
            {"key": "b", "label": "Read it again and trust the sender name only", "points": 1},
            {"key": "c", "label": "Check the sender, link, and workflow before acting", "points": 3},
            {"key": "d", "label": "Verify through a trusted separate channel and report if suspicious", "points": 4},
        ],
    },
    {
        "question_id": "PT2",
        "prompt": "How confident are you at spotting phishing, smishing, and vishing patterns?",
        "dimension": "self_awareness",
        "options": [
            {"key": "a", "label": "Not confident yet", "points": 0},
            {"key": "b", "label": "A little confident", "points": 1},
            {"key": "c", "label": "Reasonably confident", "points": 2},
            {"key": "d", "label": "Confident and can explain why", "points": 4},
        ],
    },
    {
        "question_id": "PT3",
        "prompt": "An unexpected payment or record-change request arrives. What would you do?",
        "dimension": "workflow_judgment",
        "options": [
            {"key": "a", "label": "Process it quickly to avoid delay", "points": 0},
            {"key": "b", "label": "Ask only in the same message thread", "points": 1},
            {"key": "c", "label": "Compare it with normal workflow and sender details", "points": 3},
            {"key": "d", "label": "Use approved workflow checks and trusted escalation path", "points": 4},
        ],
    },
    {
        "question_id": "PT4",
        "prompt": "A caller pressures you for immediate action. Which response is best?",
        "dimension": "pressure_response",
        "options": [
            {"key": "a", "label": "Give the information to reduce pressure", "points": 0},
            {"key": "b", "label": "Stay on the call and try to guess", "points": 1},
            {"key": "c", "label": "Pause and ask for verifiable details", "points": 3},
            {"key": "d", "label": "End the call politely and verify independently", "points": 4},
        ],
    },
    {
        "question_id": "PT5",
        "prompt": "What should happen after you identify a suspicious communication?",
        "dimension": "reporting",
        "options": [
            {"key": "a", "label": "Delete it and tell no one", "points": 0},
            {"key": "b", "label": "Ignore it and move on", "points": 1},
            {"key": "c", "label": "Record the issue and notify the appropriate channel", "points": 3},
            {"key": "d", "label": "Document why it is suspicious and report through approved process", "points": 4},
        ],
    },
    {
        "question_id": "PT6",
        "prompt": "How do you decide whether a message is legitimate?",
        "dimension": "reasoning",
        "options": [
            {"key": "a", "label": "Mostly by feeling", "points": 0},
            {"key": "b", "label": "Mostly by sender name", "points": 1},
            {"key": "c", "label": "By checking multiple cues", "points": 3},
            {"key": "d", "label": "By checking cues, workflow fit, and trusted verification path", "points": 4},
        ],
    },
]

PLACEMENT_STAGE_BANDS: List[Dict[str, Any]] = [
    {"min_score": 0, "max_score": 4, "stage_id": "BEGINNER_INTRODUCTORY"},
    {"min_score": 5, "max_score": 8, "stage_id": "BEGINNER_DEVELOPING"},
    {"min_score": 9, "max_score": 11, "stage_id": "BEGINNER_ADVANCED"},
    {"min_score": 12, "max_score": 14, "stage_id": "INTERMEDIATE_INTRODUCTORY"},
    {"min_score": 15, "max_score": 17, "stage_id": "INTERMEDIATE_DEVELOPING"},
    {"min_score": 18, "max_score": 19, "stage_id": "INTERMEDIATE_ADVANCED"},
    {"min_score": 20, "max_score": 21, "stage_id": "EXPERT_INTRODUCTORY"},
    {"min_score": 22, "max_score": 23, "stage_id": "EXPERT_DEVELOPING"},
    {"min_score": 24, "max_score": 24, "stage_id": "EXPERT_ADVANCED"},
]

TRAINING_LOOP_POLICY: Dict[str, Any] = {
    "loop_name": "training_loop",
    "window_scenarios": 6,
    "goal": "stabilize secure recognition and verification behavior at the current stage",
    "promotion_gate": {
        "accuracy_min": 0.70,
        "behavior_min": 0.70,
        "speed_min": 0.55,
        "safe_choice_rate_min": 0.70,
    },
    "failure_response": {
        "show_more_hints": True,
        "increase_red_flag_visibility": True,
        "lower_time_pressure": True,
        "micro_stage_drop_max": 1,
    },
}

MASTERY_LOOP_POLICY: Dict[str, Any] = {
    "loop_name": "mastery_loop",
    "window_scenarios": 6,
    "goal": "prove readiness for the next stage under more realistic pressure",
    "promotion_gate": {
        "accuracy_min": 0.82,
        "behavior_min": 0.80,
        "speed_min": 0.65,
        "safe_choice_rate_min": 0.80,
    },
    "completion_rule": "If final stage passes mastery loop, training is complete.",
}

REGRESSION_POLICY = {
    "single_window_action": {
        "clearer_cues": True,
        "more_hints": True,
        "lower_pressure": True,
        "micro_stage_drop_max": 1,
        "macro_stage_demote": False,
    },
    "persistent_failure_action": {
        "windows_required": 2,
        "metrics_required": 2,
        "micro_stage_drop_max": 2,
        "macro_stage_demote": True,
    },
    "hysteresis_rule": {
        "enabled": True,
        "note": "Promotion requires stronger evidence than holding steady, to reduce stage oscillation.",
    },
}

TOTAL_PATHS_PER_MODE = len(ROLES) * len(STAGE_LADDER) * len(AGE_GROUPS)
TOTAL_SCENARIOS_PER_LLM_PER_MODE = TOTAL_PATHS_PER_MODE * len(CHANNELS) * len(VARIANTS)
FULL_PATH_FORMULA = (
    f"{len(ROLES)} roles × {len(STAGE_LADDER)} stages × {len(AGE_GROUPS)} age groups × "
    f"{len(CHANNELS)} channels × {len(VARIANTS)} variants = {TOTAL_SCENARIOS_PER_LLM_PER_MODE} scenarios per LLM per retrieval mode"
)

LLM_MODELS: Dict[str, Dict[str, Any]] = {
    "gpt_nano": {
        "provider": "openai",
        "model_name": os.getenv("PSQ_OPENAI_MODEL", "gpt-5.4-nano"),
        "description": "Cloud — OpenAI GPT-5.4 nano",
        "temperature": 0.5,
        "max_tokens": 2200,
        "timeout": 120,
        "num_ctx": 16384,
        "max_rag_examples": 3,
    },
    "qwen3_8b": {
        "provider": "ollama",
        "model_name": os.getenv("PSQ_OLLAMA_QWEN", "qwen3:8b"),
        "description": "Local — Qwen3 8B (Ollama)",
        "temperature": 0.6,
        "max_tokens": 1800,
        "timeout": 240,
        "num_ctx": 8192,
        "max_rag_examples": 3,
    },
    "mistral_7b": {
        "provider": "ollama",
        "model_name": os.getenv("PSQ_OLLAMA_MISTRAL", "mistral:7b"),
        "description": "Local — Mistral 7B (Ollama)",
        "temperature": 0.6,
        "max_tokens": 1600,
        "timeout": 240,
        "num_ctx": 4096,
        "max_rag_examples": 2,
    },
}
ALL_GENERATION_LLMS = list(LLM_MODELS.keys())
DEFAULT_PROFILE_LLM = "gpt_nano"
DEFAULT_SCENARIO_LLM = "mistral_7b"
FALLBACK_LLM = "qwen3_8b"
MIN_QUALITY_SCORE = 0.60
MAX_RETRIES = 3

@dataclass
class GenerationSeed:
    role: str
    stage_id: str
    age_group_code: str
    retrieval_mode: str
    language_mode: str
    macro_stage: str
    micro_stage: str
    stage_index: int
    vocabulary_band: str
    knowledge_type: str
    interaction_pattern: str
    development_focus: str
    difficulty_label: str
    difficulty_band: str
    time_pressure_label: str
    pressure_level: str
    deception_depth: str
    red_flags_visible: str
    hint_policy: str
    prompt_method: str
    company_type_hint: str
    manager_title_hint: str
    department_hint: str
    job_title_hint: str
    role_language_style: str
    tool_hints: List[str] = field(default_factory=list)
    task_hints: List[str] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)
    age_group_label: str = ""
    age_group_name: str = ""
    age_story_style: str = ""
    digital_familiarity_profile: str = ""
    persona_id: str = ""
    persona_path_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _language_from_retrieval_mode(retrieval_mode: str) -> str:
    return "th" if retrieval_mode == "THAI_LOCAL" else "en"


def stage_short(stage_id: str) -> str:
    stage = STAGE_BY_ID[stage_id]
    return f"{MACRO_STAGE_SHORT[stage['macro_stage']]}_{MICRO_STAGE_SHORT[stage['micro_stage']]}"


def build_persona_id(role: str, stage_id: str) -> str:
    role_key = ROLE_FROM_GAME.get(role, role.upper())
    return f"{role_key}_{stage_short(stage_id)}"


def build_persona_path_id(role: str, stage_id: str, age_group_code: str, retrieval_mode: str) -> str:
    role_key = ROLE_FROM_GAME.get(role, role.upper())
    lang_tag = "TH" if retrieval_mode == "THAI_LOCAL" else "EN" if retrieval_mode == "ENGLISH_GLOBAL" else "HYB"
    age_tag = age_group_code.replace("_", "")
    return f"{role_key}_{stage_short(stage_id)}_A{age_tag}_{lang_tag}"


def bundle_filename(persona_path_id: str, llm_key: str) -> str:
    return f"{persona_path_id}_{llm_key}.json"


def choose_knowledge_type(stage_id: str, override: Optional[str] = None) -> str:
    return override.lower() if override else STAGE_BY_ID[stage_id]["knowledge_type_default"]


def build_generation_seed(
    role: str,
    stage_id: str,
    age_group_code: str,
    retrieval_mode: str,
    *,
    language_mode: Optional[str] = None,
    knowledge_type: Optional[str] = None,
    prompt_method: Optional[str] = None,
) -> GenerationSeed:
    role_key = ROLE_FROM_GAME.get(role, role.upper())
    stage = STAGE_BY_ID[stage_id]
    age = AGE_GROUP_BY_CODE[age_group_code]
    role_bp = ROLE_BLUEPRINTS[role_key]
    lang = language_mode or _language_from_retrieval_mode(retrieval_mode)
    knowledge = choose_knowledge_type(stage_id, knowledge_type)
    prompt_method = prompt_method or stage["prompt_method_default"]
    persona_id = build_persona_id(role_key, stage_id)
    persona_path_id = build_persona_path_id(role_key, stage_id, age_group_code, retrieval_mode)
    return GenerationSeed(
        role=role_key,
        stage_id=stage_id,
        age_group_code=age_group_code,
        retrieval_mode=retrieval_mode,
        language_mode=lang,
        macro_stage=stage["macro_stage"],
        micro_stage=stage["micro_stage"],
        stage_index=stage["index"],
        vocabulary_band=stage["vocabulary_band"],
        knowledge_type=knowledge,
        interaction_pattern=stage["interaction_pattern"],
        development_focus=stage["development_focus"],
        difficulty_label=stage["difficulty_label"],
        difficulty_band=stage["difficulty_band"],
        time_pressure_label=stage["time_pressure_label"],
        pressure_level=stage["pressure_level"],
        deception_depth=stage["deception_depth"],
        red_flags_visible=stage["red_flags_visible"],
        hint_policy=stage["hint_policy"],
        prompt_method=prompt_method,
        company_type_hint=role_bp["company_type_hint"],
        manager_title_hint=role_bp["manager_title_hint"],
        department_hint=role_bp["department_hint"],
        job_title_hint=role_bp["job_titles"][(stage["index"] - 1) % len(role_bp["job_titles"])],
        role_language_style=role_bp["role_language_style"],
        tool_hints=role_bp["tool_hints"][:],
        task_hints=role_bp["task_hints"][:],
        learning_objectives=role_bp["learning_objectives"][:],
        age_group_label=age["age_group_label"],
        age_group_name=age["learner_group"],
        age_story_style=age["story_style"],
        digital_familiarity_profile=age["digital_familiarity_profile"],
        persona_id=persona_id,
        persona_path_id=persona_path_id,
    )


def iter_generation_seeds(
    roles: Optional[List[str]] = None,
    stage_ids: Optional[List[str]] = None,
    age_group_codes: Optional[List[str]] = None,
    retrieval_modes: Optional[List[str]] = None,
    *,
    include_hybrid: bool = False,
) -> List[GenerationSeed]:
    roles = roles or ROLES
    stage_ids = stage_ids or [s["stage_id"] for s in STAGE_LADDER]
    age_group_codes = age_group_codes or [a["age_group_code"] for a in AGE_GROUPS]
    retrieval_modes = retrieval_modes or PRODUCTION_RETRIEVAL_MODES
    if include_hybrid and "HYBRID_COMPARE" not in retrieval_modes:
        retrieval_modes = list(retrieval_modes) + ["HYBRID_COMPARE"]
    seeds: List[GenerationSeed] = []
    for role in roles:
        for stage_id in stage_ids:
            for age_code in age_group_codes:
                for retrieval_mode in retrieval_modes:
                    seeds.append(build_generation_seed(role, stage_id, age_code, retrieval_mode))
    return seeds


def filter_seeds(
    seeds: List[GenerationSeed],
    *,
    role: Optional[str] = None,
    stage_id: Optional[str] = None,
    age_group_code: Optional[str] = None,
    retrieval_mode: Optional[str] = None,
    language_mode: Optional[str] = None,
) -> List[GenerationSeed]:
    out = []
    for seed in seeds:
        if role and seed.role != ROLE_FROM_GAME.get(role, role.upper()):
            continue
        if stage_id and seed.stage_id != stage_id:
            continue
        if age_group_code and seed.age_group_code != age_group_code:
            continue
        if retrieval_mode and seed.retrieval_mode != retrieval_mode:
            continue
        if language_mode and seed.language_mode != language_mode:
            continue
        out.append(seed)
    return out


def safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
