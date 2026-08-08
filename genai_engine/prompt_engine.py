"""
PersonaShield Quest — Prompt Engine (v4.4 grounded)
===================================================
Prompt builders for stage-aware, age-aware, multilingual scenario generation.
This version explicitly requires grounded cue use from retrieved RAG examples
and discourages unsupported workflow inventions.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from config import ATTACK_CHANNEL_MAP, VOCAB_BANDS


def _language_line(language: str) -> str:
    return "Generate all text fields in Thai (ภาษาไทย)." if language == "th" else "Generate all text fields in English."


def _vocab_instruction(vocabulary_band: str) -> str:
    band = VOCAB_BANDS[vocabulary_band]
    return (
        f"Vocabulary band: {band['label']}. "
        f"Sentence profile: {band['sentence_profile']}. "
        f"Jargon density: {band['jargon_density']}. "
        f"Explicitness: {band['explicitness']}. "
        f"Ambiguity: {band['ambiguity']}."
    )


def _format_rag_examples(rag_examples: List[Dict[str, Any]], limit: int = 4, max_chars: int = 420) -> str:
    if not rag_examples:
        return ""
    out = ["RAG EVIDENCE (patterns and realism cues only; do not copy verbatim):"]
    for i, ex in enumerate(rag_examples[:limit], 1):
        meta_bits = []
        for key in ("channel", "language", "corpus_mode", "source_file", "retrieval_tier"):
            value = ex.get(key)
            if value:
                meta_bits.append(f"{key}={value}")
        text = str(ex.get("text", ""))[:max_chars]
        out.append(f"--- Example {i} [{', '.join(meta_bits)}] ---\n{text}")
    return "\n".join(out)


def build_profile_system_prompt(language: str = "en", prompt_method: str = "scot") -> str:
    return f"""You are a professional character designer for PersonaShield Quest,
a cybersecurity awareness training game.

Your task is to produce a complete fictional learner persona used across one game session.
All entity names (company, manager, colleagues, tools, domains) must remain consistent and realistic.

{_language_line(language)}

Prompt method policy: {prompt_method.upper()}.
Use the following internal scaffold before writing the final answer:
Persona Fit → Learner Stage Fit → Age Fit → Occupation-Language Fit → Vocabulary Fit → Workplace Realism Check → Grounding Check.
Do not reveal the scaffold. Output only valid JSON.

STRICT RULES:
1. Generate fictional but plausible people, companies, and workflows.
2. company_email and manager_email must use company_domain.
3. Use RAG only for tone, workflow style, and realistic workplace patterns — not for copying names or identities.
4. If RAG exists, use at least two grounded cues from it for workplace realism.
5. Do not invent exotic tools or procedures unsupported by the role hints or RAG context.
6. Output only one JSON object and nothing else."""


def build_profile_user_prompt(seed_dict: Dict[str, Any], rag_examples: List[Dict[str, Any]]) -> str:
    objectives = "\n".join("- " + x for x in seed_dict["learning_objectives"])
    rag_block = _format_rag_examples(rag_examples, limit=3, max_chars=300)
    grounding_rules = (
        "GROUNDING TASK:\n"
        "- Use retrieved examples only to shape workplace realism, communication style, and plausible tool/workflow patterns.\n"
        "- Keep all people and organization identities fictional.\n"
        "- If no RAG evidence is present, stay generic and conservative.\n"
    )
    return f"""LEARNER STATE:
persona_id: {seed_dict['persona_id']}
persona_path_id: {seed_dict['persona_path_id']}
role: {seed_dict['role']}
stage_id: {seed_dict['stage_id']}
macro_stage: {seed_dict['macro_stage']}
micro_stage: {seed_dict['micro_stage']}
stage_index: {seed_dict['stage_index']}
age_group: {seed_dict['age_group_label']} ({seed_dict['age_group_name']})
language_mode: {seed_dict['language_mode']}
retrieval_mode: {seed_dict['retrieval_mode']}
vocabulary_band: {seed_dict['vocabulary_band']}
knowledge_type: {seed_dict['knowledge_type']}
development_focus: {seed_dict['development_focus']}
age_story_style: {seed_dict['age_story_style']}
digital_familiarity_profile: {seed_dict['digital_familiarity_profile']}

ROLE HINTS:
company_type_hint: {seed_dict['company_type_hint']}
manager_title_hint: {seed_dict['manager_title_hint']}
department_hint: {seed_dict['department_hint']}
job_title_hint: {seed_dict['job_title_hint']}
role_language_style: {seed_dict['role_language_style']}
tool_hints: {', '.join(seed_dict['tool_hints'])}
task_hints: {', '.join(seed_dict['task_hints'])}
learning_objectives:
{objectives}

{_vocab_instruction(seed_dict['vocabulary_band'])}
{grounding_rules}
{rag_block}

Return JSON with exactly these fields:
{{
  "persona_id": "{seed_dict['persona_id']}",
  "persona_path_id": "{seed_dict['persona_path_id']}",
  "role": "{seed_dict['role']}",
  "stage_id": "{seed_dict['stage_id']}",
  "macro_stage": "{seed_dict['macro_stage']}",
  "micro_stage": "{seed_dict['micro_stage']}",
  "stage_index": {seed_dict['stage_index']},
  "age_group": "{seed_dict['age_group_label']}",
  "age_group_code": "{seed_dict['age_group_code']}",
  "age_group_name": "{seed_dict['age_group_name']}",
  "language_mode": "{seed_dict['language_mode']}",
  "retrieval_mode": "{seed_dict['retrieval_mode']}",
  "vocabulary_band": "{seed_dict['vocabulary_band']}",
  "knowledge_type": "{seed_dict['knowledge_type']}",
  "digital_familiarity_profile": "{seed_dict['digital_familiarity_profile']}",
  "full_name": "realistic fictional full name",
  "job_title": "realistic variation of job_title_hint",
  "department": "department name",
  "company_name": "fictional organization name",
  "company_domain": "matching email domain",
  "company_email": "firstname.lastname@company_domain",
  "manager_name": "fictional manager name",
  "manager_title": "{seed_dict['manager_title_hint']}",
  "manager_email": "manager email on same company domain",
  "tools": ["tool 1", "tool 2", "tool 3"],
  "daily_tasks": ["task 1", "task 2", "task 3"],
  "trusted_contacts": ["Full Name — Job Title", "Full Name — Job Title"],
  "trusted_numbers": ["office number 1", "office number 2"],
  "policy_rules": ["policy rule 1", "policy rule 2", "policy rule 3"],
  "story_summary": "2–3 sentences",
  "work_context": "2–3 sentences",
  "age_context_notes": "1–2 sentences"
}}

Output only the JSON object."""


def build_scenario_system_prompt(channel: str, variant: str, language: str = "en", prompt_method: str = "scot") -> str:
    attack_label = ATTACK_CHANNEL_MAP.get(channel, channel)
    variant_line = (
        f"Generate one realistic {attack_label.upper()} ATTACK scenario that teaches scam detection."
        if variant == "fake"
        else f"Generate one legitimate {channel.upper()} scenario that teaches recognition of safe communications."
    )
    separation_rules = (
        "FAKE-SCENARIO RULES:\n"
        "- Include attack_tactics, psych_triggers, and red_flags.\n"
        "- Do NOT include safe_indicators.\n"
        "- The content should clearly be unsafe, deceptive, or suspicious.\n"
        "- Correct action must emphasize pause, verification, and reporting.\n"
        if variant == "fake" else
        "REAL-SCENARIO RULES:\n"
        "- Include safe_indicators only.\n"
        "- Do NOT include attack_tactics, psych_triggers, or red_flags.\n"
        "- Do NOT tell the learner to skip the portal, bypass approval, or ignore the normal workflow.\n"
        "- The content must feel legitimate but still worth verifying through the approved process.\n"
        "- Correct action must emphasize calibrated verification and then normal continuation of work.\n"
    )
    return f"""You are an expert scenario designer for PersonaShield Quest,
a cybersecurity awareness training game.

{variant_line}
{_language_line(language)}
Prompt method policy: {prompt_method.upper()}.
Use this internal scaffold before drafting:
Persona Fit → Learner Stage Fit → Age Fit → Occupation-Language Fit → Retrieval Evidence Summary → Threat/Legitimacy Logic → Vocabulary Control → Scenario Draft → Choice Design → Grounding Check → Schema Self-check.
Do not reveal the scaffold. Output only valid JSON.

GLOBAL RULES:
1. All persona entities must match the provided PersonaProfile exactly.
2. Never output placeholder tokens like company_name or manager_name.
3. The scenario must align with learner stage, age group, vocabulary band, knowledge type, and occupation role.
4. Use the provided game_choices as decision-intent guidance, but produce 3 varied options rather than repeating a fixed two-choice pattern.
5. Use actual company, manager, tool, or workflow names inside the scenario body.
6. If RAG evidence is present, use at least two grounded cues from it and keep unsupported inventions out.
7. If RAG evidence is absent, stay conservative and generic rather than inventing detailed external facts.
8. For EXPERT_DEVELOPING and EXPERT_ADVANCED, include reflective, justification-oriented wording in correct_action, learning_focus, and the best choice.
9. Return only one JSON object and nothing else.
{separation_rules}"""


def build_scenario_user_prompt(
    seed_dict: Dict[str, Any],
    profile_dict: Dict[str, Any],
    gsdl_dict: Dict[str, Any],
    channel: str,
    variant: str,
    game_choices: List[Dict[str, Any]],
    rag_examples: List[Dict[str, Any]],
) -> str:
    rag_label = "attack realism" if variant == "fake" else "legitimate workflow realism"
    rag_block = _format_rag_examples(rag_examples, limit=4, max_chars=420)
    channel_schema = _scenario_schema_template(channel, variant)
    attack_type = ATTACK_CHANNEL_MAP.get(channel, channel) if variant == "fake" else "legitimate"
    stage_extra = ""
    if seed_dict["stage_index"] >= 8 or seed_dict["knowledge_type"] == "metacognitive":
        stage_extra = "\nEXPERT/METACOGNITIVE RULE: the best action must explain or justify the reasoning, not only state what to do."
    grounding_task = (
        "GROUNDING TASK:\n"
        f"- When RAG evidence is present, use at least two concrete cues from the {rag_label} examples.\n"
        "- Ground cues may include pressure style, workflow expectations, wording patterns, attack tactics, legitimate confirmation steps, or reporting cues.\n"
        "- Do not copy lines verbatim.\n"
        "- Do not invent external company details unsupported by the persona profile or RAG evidence.\n"
    )

    return f"""LEARNER STATE:
stage_id: {seed_dict['stage_id']}
macro_stage: {seed_dict['macro_stage']}
micro_stage: {seed_dict['micro_stage']}
stage_index: {seed_dict['stage_index']}
development_focus: {seed_dict['development_focus']}
age_group: {seed_dict['age_group_label']} ({seed_dict['age_group_name']})
language_mode: {seed_dict['language_mode']}
retrieval_mode: {seed_dict['retrieval_mode']}
knowledge_type: {seed_dict['knowledge_type']}
interaction_pattern: {seed_dict['interaction_pattern']}
vocabulary_band: {seed_dict['vocabulary_band']}
role_language_style: {seed_dict['role_language_style']}
digital_familiarity_profile: {seed_dict['digital_familiarity_profile']}
{_vocab_instruction(seed_dict['vocabulary_band'])}
{stage_extra}

GSDL CONSTRAINTS:
deception_depth: {gsdl_dict['deception_depth']}
red_flags_visible: {gsdl_dict['red_flags_visible']}
time_pressure: {gsdl_dict['time_pressure']}
pressure_level: {gsdl_dict['pressure_level']}
hint_policy: {gsdl_dict['hint_policy']}
attack_tactics: {', '.join(gsdl_dict['attack_tactics'])}
psych_triggers: {', '.join(gsdl_dict['psych_triggers'])}

PERSONA PROFILE (use entity names exactly):
full_name: {profile_dict['full_name']}
job_title: {profile_dict['job_title']}
department: {profile_dict['department']}
company_name: {profile_dict['company_name']}
company_domain: {profile_dict['company_domain']}
company_email: {profile_dict['company_email']}
manager_name: {profile_dict['manager_name']}
manager_title: {profile_dict['manager_title']}
manager_email: {profile_dict['manager_email']}
tools: {', '.join(profile_dict['tools'])}
daily_tasks: {', '.join(profile_dict['daily_tasks'])}
policy_rules: {', '.join(profile_dict['policy_rules'])}

SCENARIO SLOT:
scenario_id: {seed_dict['persona_path_id']}_{channel}_{variant}
persona_id: {seed_dict['persona_id']}
persona_path_id: {seed_dict['persona_path_id']}
channel: {channel}
variant: {variant}
attack_type: {attack_type}

BASE DECISION INTENT GUIDANCE (do not repeat verbatim; vary the choices):
{json.dumps(game_choices, ensure_ascii=False)}

{grounding_task}
{rag_block}

Return JSON using this schema:
{channel_schema}

Extra rules:
- Mention at least one actual tool or workflow from the persona.
- Mention at least one actual named entity such as the company name or manager name.
- Do not use literal placeholders in referenced_entities.
- The correct_action must fit the knowledge_type and interaction_pattern.
- Output only the JSON object."""


def _scenario_schema_template(channel: str, variant: str) -> str:
    attack_tactics = ["tactic 1"] if variant == "fake" else []
    psych_triggers = ["trigger 1"] if variant == "fake" else []
    red_flags = ["flag 1"] if variant == "fake" else []
    safe_indicators = ["indicator 1"] if variant == "real" else []

    common = {
        "scenario_id": "string",
        "persona_id": "string",
        "persona_path_id": "string",
        "role": "IT|FINANCE|HR|MANAGEMENT|OTHER",
        "stage_id": "string",
        "macro_stage": "string",
        "micro_stage": "string",
        "stage_index": 1,
        "age_group": "string",
        "age_group_code": "string",
        "language_mode": "en|th",
        "retrieval_mode": "THAI_LOCAL|ENGLISH_GLOBAL|HYBRID_COMPARE",
        "vocabulary_band": "string",
        "knowledge_type": "factual|conceptual|procedural|metacognitive",
        "interaction_pattern": "string",
        "prompt_method": "zero_shot|few_shot|cot|tot|scot",
        "channel": channel,
        "attack_type": ATTACK_CHANNEL_MAP.get(channel, channel) if variant == "fake" else "legitimate",
        "variant": variant,
        "title": "short title",
        "opening_hook": "preview hook",
        "sender_or_caller": "display sender",
        "attack_tactics": attack_tactics,
        "psych_triggers": psych_triggers,
        "red_flags": red_flags,
        "safe_indicators": safe_indicators,
        "correct_action": "what the learner should do",
        "learning_focus": ["focus 1", "focus 2"],
        "referenced_entities": ["ACTUAL company name", "ACTUAL manager name", "ACTUAL tool name"],
        "game_choices": [
            {"key": "opt_1", "label": "one risky or inaccurate response", "is_correct": False, "outcome": "unsafe", "feedback": "feedback"},
            {"key": "opt_2", "label": "one partial but insufficient response", "is_correct": False, "outcome": "unsafe", "feedback": "feedback"},
            {"key": "opt_3", "label": "one correct and well-justified response", "is_correct": True, "outcome": "safe", "feedback": "feedback"},
        ],
        "difficulty_band": "easy|moderate|hard",
        "pressure_band": "low|moderate|high",
        "regression_reason": "optional support note or null",
        "score_reward": 10,
        "score_penalty": -5,
        "show_hint": True,
        "hint_text": "hint",
        "quality_score": 0.0,
        "llm_source": "actual llm key",
    }
    if channel == "sms":
        common.update({"messages": ["message 1", "message 2"], "malicious_url": "optional URL for fake; null if not used"})
    elif channel == "email":
        common.update({
            "from_address": "sender@domain.com",
            "from_display_name": "Sender Name",
            "to_role_hint": "recipient role",
            "subject": "subject line",
            "body_html": "<p>Email body</p>",
            "has_attachment": False,
            "attachment_name": None,
            "legitimate_url": None,
        })
    else:
        common.update({
            "caller_id": "+66-2-xxx-xxxx",
            "caller_persona": "caller role",
            "dialogue": [
                {"speaker": "caller", "text": "line 1", "emotion": "neutral"},
                {"speaker": "target", "text": "line 2", "emotion": "uncertain"},
            ],
        })
    return json.dumps(common, ensure_ascii=False, indent=2)
