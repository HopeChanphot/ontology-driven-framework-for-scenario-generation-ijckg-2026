
"""
PersonaShield Quest — GSDL Descriptor Generator (v4.1)
======================================================
Deterministic descriptor generation from role + stage + age + retrieval mode.
"""

from __future__ import annotations

import hashlib
import random
from typing import List

from config import CHANNELS, PSYCH_TRIGGERS, REGRESSION_POLICY, ROLE_BLUEPRINTS, build_generation_seed
from schemas import GSDLDescriptor


def _seed_from_key(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _choose_tactics(role: str, stage_index: int, rng: random.Random) -> List[str]:
    pool = ROLE_BLUEPRINTS[role]["tactic_pool"][:]
    count = 1 if stage_index <= 2 else 2 if stage_index <= 6 else 3
    return rng.sample(pool, min(count, len(pool)))


def _choose_triggers(stage_index: int, rng: random.Random) -> List[str]:
    count = 1 if stage_index <= 2 else 2 if stage_index <= 6 else 3
    return rng.sample(PSYCH_TRIGGERS, count)


def generate_gsdl_for_seed(seed) -> GSDLDescriptor:
    key = f"{seed.persona_path_id}|{seed.role}|{seed.stage_id}|{seed.age_group_code}|{seed.retrieval_mode}"
    rng = random.Random(_seed_from_key(key))
    return GSDLDescriptor(
        persona_id=seed.persona_id,
        persona_path_id=seed.persona_path_id,
        role=seed.role,
        stage_id=seed.stage_id,
        macro_stage=seed.macro_stage,
        micro_stage=seed.micro_stage,
        stage_index=seed.stage_index,
        age_group=seed.age_group_label,
        age_group_code=seed.age_group_code,
        language_mode=seed.language_mode,
        retrieval_mode=seed.retrieval_mode,
        vocabulary_band=seed.vocabulary_band,
        knowledge_type=seed.knowledge_type,
        interaction_pattern=seed.interaction_pattern,
        difficulty_label=seed.difficulty_label,
        difficulty_band=seed.difficulty_band,
        time_pressure=seed.time_pressure_label,
        pressure_level=seed.pressure_level,
        deception_depth=seed.deception_depth,
        red_flags_visible=seed.red_flags_visible,
        hint_policy=seed.hint_policy,
        suitable_channels=list(CHANNELS),
        attack_tactics=_choose_tactics(seed.role, seed.stage_index, rng),
        psych_triggers=_choose_triggers(seed.stage_index, rng),
        regression_policy=REGRESSION_POLICY,
    )


def generate_gsdl_for_path(role: str, stage_id: str, age_group_code: str, retrieval_mode: str) -> GSDLDescriptor:
    seed = build_generation_seed(role, stage_id, age_group_code, retrieval_mode)
    return generate_gsdl_for_seed(seed)
