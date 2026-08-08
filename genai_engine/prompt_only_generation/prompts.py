"""Prompt builders for the prompt-only/default-template engine."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from config import ATTACK_CHANNEL_MAP, VOCAB_BANDS


def _vocab_instruction(vocabulary_band: str) -> str:
    band = VOCAB_BANDS[vocabulary_band]
    return (
        f"Vocabulary band: {band['label']}. "
        f"Sentence profile: {band['sentence_profile']}. "
        f"Jargon density: {band['jargon_density']}. "
        f"Explicitness: {band['explicitness']}. "
        f"Ambiguity: {band['ambiguity']}."
    )


def build_prompt_only_prompts(
    *,
    seed_dict: Dict[str, Any],
    profile_dict: Dict[str, Any],
    gsdl_dict: Dict[str, Any],
    channel: str,
    variant: str,
    default_template: Dict[str, Any],
) -> Tuple[str, str, Dict[str, Any]]:
    """Build prompts that use prompt engineering and a default template only."""

    language_line = "Generate all player-facing text in Thai." if seed_dict["language_mode"] == "th" else "Generate all player-facing text in English."
    attack_type = ATTACK_CHANNEL_MAP.get(channel, channel) if variant == "fake" else "legitimate"
    variant_rules = (
        "- This is a FAKE/social-engineering scenario.\n"
        "- Include attack_tactics, psych_triggers, and red_flags.\n"
        "- Do not include safe_indicators.\n"
        "- Correct action must emphasize pause, verify, and report.\n"
        if variant == "fake"
        else
        "- This is a REAL/legitimate communication scenario.\n"
        "- Include safe_indicators only.\n"
        "- Do not include attack_tactics, psych_triggers, or red_flags.\n"
        "- Correct action must emphasize calibrated verification and normal continuation.\n"
    )

    system_prompt = f"""You are a PersonaShield Quest scenario-generation engine.

Generate one complete cybersecurity-awareness game scenario using only:
1. the learner seed,
2. the GSDL difficulty descriptor,
3. the fictional persona profile,
4. the default scenario template.

No RAG is available. No ontology is available. Do not claim external evidence.
Use prompt engineering and the provided default template as the control layer.
{language_line}
Output only valid JSON.
"""

    default_json = json.dumps(default_template, ensure_ascii=False, indent=2)
    profile_json = json.dumps(profile_dict, ensure_ascii=False, indent=2)
    gsdl_json = json.dumps(gsdl_dict, ensure_ascii=False, indent=2)
    objectives = "\n".join(f"- {item}" for item in seed_dict["learning_objectives"])

    user_prompt = f"""SCENARIO SLOT:
scenario_id: {seed_dict['persona_path_id']}_{channel}_{variant}
role: {seed_dict['role']}
stage_id: {seed_dict['stage_id']}
macro_stage: {seed_dict['macro_stage']}
micro_stage: {seed_dict['micro_stage']}
stage_index: {seed_dict['stage_index']}
age_group: {seed_dict['age_group_label']} ({seed_dict['age_group_name']})
channel: {channel}
variant: {variant}
attack_type: {attack_type}
knowledge_type: {seed_dict['knowledge_type']}
interaction_pattern: {seed_dict['interaction_pattern']}
development_focus: {seed_dict['development_focus']}

LEARNING OBJECTIVES:
{objectives}

VOCABULARY CONTROL:
{_vocab_instruction(seed_dict['vocabulary_band'])}

VARIANT RULES:
{variant_rules}

PERSONA PROFILE:
{profile_json}

GSDL DIFFICULTY DESCRIPTOR:
{gsdl_json}

DEFAULT TEMPLATE:
{default_json}

GENERATION REQUIREMENTS:
- Keep all required metadata fields from the default template.
- Improve the player-facing wording while preserving role, stage, channel, variant, and persona consistency.
- Make the best choice require cybersecurity reasoning, not just obvious keyword spotting.
- Include actionable feedback for every game choice.
- Use only fictional people, organizations, domains, numbers, and URLs.
- Do not add RAG source claims or ontology claims.
- Set generation_meta.engine to "prompt_only_generation".
- Set generation_meta.rag_used to false.
- Set generation_meta.ontology_used to false.
- Set generation_meta.template_id to "prompt_only_default_template_v1".

Return exactly one JSON object compatible with the provided default template."""

    metadata = {
        "engine": "prompt_only_generation",
        "prompt_version": "prompt_only_default_template_v1",
        "template_id": "prompt_only_default_template_v1",
        "rag_used": False,
        "ontology_used": False,
        "system_chars": len(system_prompt),
        "user_chars": len(user_prompt),
    }
    return system_prompt, user_prompt, metadata
