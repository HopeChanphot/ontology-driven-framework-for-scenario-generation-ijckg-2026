"""Default templates for prompt-only PersonaShield scenario generation.

This module deliberately does not import RAG or ontology code. It creates a
complete schema-safe baseline scenario that can be used directly in dry runs or
as a repair fallback for local LLM output.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List

from config import ATTACK_CHANNEL_MAP


FIRST_NAMES = ["Arisa", "Narin", "Mina", "Daniel", "Sirin", "Alex", "Kanya", "Jirapat"]
LAST_NAMES = ["Tanaka", "Pattana", "Rivers", "Wirote", "Limsakul", "Anand", "Boonmee"]
COMPANY_ROOTS = ["SkyLink", "NorthBridge", "CrestPoint", "OrchidWorks", "VertexFlow", "BrightHarbor"]


def build_default_persona(seed: Dict[str, Any]) -> Dict[str, Any]:
    """Build a deterministic fictional persona without RAG or ontology."""

    rng = random.Random(seed["persona_path_id"])
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    manager_first = rng.choice(FIRST_NAMES)
    manager_last = rng.choice(LAST_NAMES)
    company_root = rng.choice(COMPANY_ROOTS)
    company_name = f"{company_root} Solutions"
    company_domain = f"{company_root.lower()}-solutions.com"
    return {
        "persona_id": seed["persona_id"],
        "persona_path_id": seed["persona_path_id"],
        "role": seed["role"],
        "stage_id": seed["stage_id"],
        "macro_stage": seed["macro_stage"],
        "micro_stage": seed["micro_stage"],
        "stage_index": seed["stage_index"],
        "age_group": seed["age_group_label"],
        "age_group_code": seed["age_group_code"],
        "age_group_name": seed["age_group_name"],
        "language_mode": seed["language_mode"],
        "retrieval_mode": seed["retrieval_mode"],
        "vocabulary_band": seed["vocabulary_band"],
        "knowledge_type": seed["knowledge_type"],
        "digital_familiarity_profile": seed["digital_familiarity_profile"],
        "full_name": f"{first} {last}",
        "job_title": seed["job_title_hint"],
        "department": seed["department_hint"],
        "company_name": company_name,
        "company_domain": company_domain,
        "company_email": f"{first.lower()}.{last.lower()}@{company_domain}",
        "manager_name": f"{manager_first} {manager_last}",
        "manager_title": seed["manager_title_hint"],
        "manager_email": f"{manager_first.lower()}.{manager_last.lower()}@{company_domain}",
        "tools": seed["tool_hints"][:3],
        "daily_tasks": seed["task_hints"][:3],
        "trusted_contacts": [f"{manager_first} {manager_last} - {seed['manager_title_hint']}"],
        "trusted_numbers": ["+66-2-100-2000", "+66-2-100-2001"],
        "policy_rules": [
            "Verify unusual requests through a trusted separate channel.",
            "Never share passwords, OTPs, or MFA codes.",
            "Report suspicious messages through the approved security process.",
        ],
        "story_summary": f"{first} {last} works in {seed['department_hint']} and handles routine workplace requests.",
        "work_context": f"The work context uses {', '.join(seed['tool_hints'][:2])} for {', '.join(seed['task_hints'][:2])}.",
        "age_context_notes": seed["age_story_style"],
    }


def build_default_game_choices(variant: str, knowledge_type: str) -> List[Dict[str, Any]]:
    """Return default game choice intents for fake or real scenarios."""

    if variant == "fake":
        return [
            {
                "key": "opt_1",
                "label": "Act immediately because the request sounds urgent.",
                "is_correct": False,
                "outcome": "unsafe",
                "feedback": "This skips verification and increases risk.",
            },
            {
                "key": "opt_2",
                "label": "Reply inside the same message and then proceed.",
                "is_correct": False,
                "outcome": "unsafe",
                "feedback": "This still uses an untrusted channel controlled by the sender.",
            },
            {
                "key": "opt_3",
                "label": "Pause, verify through an approved channel, and report if needed.",
                "is_correct": True,
                "outcome": "safe",
                "feedback": "This follows safe defensive behavior.",
            },
        ]
    good_label = "Verify the workflow and continue through the approved process."
    if knowledge_type == "metacognitive":
        good_label = "Verify the workflow, explain why it is legitimate, and continue through the approved process."
    return [
        {
            "key": "opt_1",
            "label": "Report it immediately without checking the approved workflow.",
            "is_correct": False,
            "outcome": "unsafe",
            "feedback": "This may over-report a normal workflow before checking available evidence.",
        },
        {
            "key": "opt_2",
            "label": "Trust it automatically because it looks familiar.",
            "is_correct": False,
            "outcome": "unsafe",
            "feedback": "This under-verifies the request and builds a risky habit.",
        },
        {
            "key": "opt_3",
            "label": good_label,
            "is_correct": True,
            "outcome": "safe",
            "feedback": "This uses calibrated verification.",
        },
    ]


def build_default_scenario(seed: Dict[str, Any], profile: Dict[str, Any], gsdl: Dict[str, Any], channel: str, variant: str) -> Dict[str, Any]:
    """Build a complete default-template scenario without RAG or ontology."""

    suspicious = variant == "fake"
    attack_type = ATTACK_CHANNEL_MAP.get(channel, channel) if suspicious else "legitimate"
    title = f"{profile['department']} {channel.upper()} {'verification request' if suspicious else 'workflow notice'}"
    common: Dict[str, Any] = {
        "scenario_id": f"{seed['persona_path_id']}_{channel}_{variant}",
        "persona_id": seed["persona_id"],
        "persona_path_id": seed["persona_path_id"],
        "role": seed["role"],
        "stage_id": seed["stage_id"],
        "macro_stage": seed["macro_stage"],
        "micro_stage": seed["micro_stage"],
        "stage_index": seed["stage_index"],
        "age_group": seed["age_group_label"],
        "age_group_code": seed["age_group_code"],
        "language_mode": seed["language_mode"],
        "retrieval_mode": seed["retrieval_mode"],
        "vocabulary_band": seed["vocabulary_band"],
        "knowledge_type": seed["knowledge_type"],
        "interaction_pattern": seed["interaction_pattern"],
        "prompt_method": seed["prompt_method"],
        "channel": channel,
        "attack_type": attack_type,
        "variant": variant,
        "title": title,
        "opening_hook": f"A {profile['job_title']} receives a {channel} related to {profile['tools'][0]}.",
        "sender_or_caller": profile["manager_name"] if not suspicious else "External Support Desk",
        "attack_tactics": ["pretexting", attack_type] if suspicious else [],
        "psych_triggers": ["authority", "urgency"] if suspicious else [],
        "red_flags": ["Urgent request through an unusual path", "Verification is pushed outside the approved process"] if suspicious else [],
        "safe_indicators": [] if suspicious else ["Expected workflow", "Can be verified in the approved system"],
        "correct_action": "Pause, verify through a trusted separate channel, and report if it cannot be confirmed." if suspicious else "Verify the request in the approved workflow, then continue normally.",
        "learning_focus": seed["learning_objectives"][:2],
        "referenced_entities": [profile["company_name"], profile["manager_name"], profile["tools"][0]],
        "game_choices": build_default_game_choices(variant, seed["knowledge_type"]),
        "difficulty_band": seed["difficulty_band"],
        "pressure_band": seed["pressure_level"],
        "score_reward": 10,
        "score_penalty": -5,
        "show_hint": True,
        "hint_text": "Use a trusted workflow or separate channel before acting.",
        "quality_score": 0.0,
        "quality_breakdown": {},
        "quality_flags": [],
        "repair_actions": [],
        "llm_source": "default_template",
        "generation_meta": {
            "template_id": "prompt_only_default_template_v1",
            "gsdl": gsdl,
            "rag_used": False,
            "ontology_used": False,
            "grounding_mode": "prompt_only_default_template",
        },
    }

    if channel == "sms":
        common["messages"] = [
            f"{'URGENT: ' if suspicious else ''}{profile['company_name']} {profile['tools'][0]} notice for {profile['job_title']}.",
            "Use the approved portal to verify before acting." if not suspicious else "Reply now to keep access active.",
        ]
        common["malicious_url"] = "https://verify-example.invalid/login" if suspicious else None
    elif channel == "email":
        common.update(
            {
                "from_address": f"support@{'external-help.invalid' if suspicious else profile['company_domain']}",
                "from_display_name": common["sender_or_caller"],
                "to_role_hint": profile["job_title"],
                "subject": title,
                "body_html": f"<p>Hello {profile['full_name']}, please verify this {profile['tools'][0]} request through the approved process.</p>",
                "has_attachment": False,
                "attachment_name": None,
                "legitimate_url": f"https://{profile['company_domain']}/portal" if not suspicious else None,
            }
        )
    else:
        common.update(
            {
                "caller_id": "+66-2-100-2000" if not suspicious else "+66-90-000-0000",
                "caller_persona": common["sender_or_caller"],
                "dialogue": [
                    {
                        "speaker": "caller",
                        "text": f"I am calling about your {profile['tools'][0]} workflow.",
                        "emotion": "urgent" if suspicious else "neutral",
                    },
                    {
                        "speaker": "target",
                        "text": "I will verify this through the approved process before acting.",
                        "emotion": "calm",
                    },
                ],
            }
        )
    return common
