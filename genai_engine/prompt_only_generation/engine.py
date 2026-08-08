"""Prompt-only/default-template scenario generation engine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import ATTACK_CHANNEL_MAP
from gsdl_generator import generate_gsdl_for_seed
from llm_client import LLMClient
from schemas import ScenarioContent
from validator import BundleValidator

from .models import LIGHTWEIGHT_MODEL_PROFILES, LocalModelProfile
from .prompts import build_prompt_only_prompts
from .templates import build_default_persona, build_default_scenario


@dataclass
class PromptOnlyGenerationResult:
    """Generated prompt-only scenario plus reproducibility metadata."""

    llm_key: str
    model: Dict[str, Any]
    scenario: Dict[str, Any]
    validation_passed: bool
    validation_issues: List[str]
    prompt_metadata: Dict[str, Any]
    used_live_llm: bool
    used_fallback: bool

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PromptOnlyGenerationEngine:
    """Generate scenarios with prompt engineering and a default template only."""

    engine_name = "prompt_only_generation"
    engine_version = "v1.0"

    def __init__(self) -> None:
        self.validator = BundleValidator()

    def generate_one(
        self,
        *,
        seed: Any,
        channel: str,
        variant: str,
        llm_key: str = "qwen2_5_7b",
        dry_run: bool = False,
    ) -> PromptOnlyGenerationResult:
        """Generate one prompt-only scenario slot."""

        if llm_key not in LIGHTWEIGHT_MODEL_PROFILES:
            raise ValueError(f"Unknown local model key {llm_key!r}; expected {sorted(LIGHTWEIGHT_MODEL_PROFILES)}")

        model = LIGHTWEIGHT_MODEL_PROFILES[llm_key]
        seed_dict = seed.to_dict() if hasattr(seed, "to_dict") else dict(seed)
        gsdl = generate_gsdl_for_seed(seed)
        gsdl_dict = gsdl.model_dump() if hasattr(gsdl, "model_dump") else dict(gsdl)
        profile = build_default_persona(seed_dict)
        default_template = build_default_scenario(seed_dict, profile, gsdl_dict, channel, variant)
        system_prompt, user_prompt, prompt_metadata = build_prompt_only_prompts(
            seed_dict=seed_dict,
            profile_dict=profile,
            gsdl_dict=gsdl_dict,
            channel=channel,
            variant=variant,
            default_template=default_template,
        )

        used_live_llm = False
        used_fallback = False
        raw: Optional[Dict[str, Any]] = None
        if not dry_run:
            raw = self._call_local_llm(model, system_prompt, user_prompt)
            used_live_llm = raw is not None
        if raw is None:
            raw = default_template
            used_fallback = True

        scenario = self._repair_and_trace(
            raw=raw,
            fallback=default_template,
            seed=seed_dict,
            gsdl=gsdl_dict,
            channel=channel,
            variant=variant,
            llm_key=llm_key,
            model=model,
            prompt_metadata=prompt_metadata,
        )
        validation_passed, validation_issues = self.validator.validate_scenario(
            scenario,
            channel,
            variant,
            int(seed_dict["stage_index"]),
            seed_dict["vocabulary_band"],
            seed_dict["knowledge_type"],
            seed_dict["role"],
        )
        validation_issues = self._filter_prompt_only_issues(validation_issues)
        validation_passed = not validation_issues

        return PromptOnlyGenerationResult(
            llm_key=llm_key,
            model=model.as_dict(),
            scenario=scenario,
            validation_passed=validation_passed,
            validation_issues=validation_issues,
            prompt_metadata=prompt_metadata,
            used_live_llm=used_live_llm,
            used_fallback=used_fallback,
        )

    def _call_local_llm(self, model: LocalModelProfile, system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
        client = LLMClient()
        return client.generate(
            model.provider,
            model.model_name,
            system_prompt,
            user_prompt,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            timeout=model.timeout,
            num_ctx=model.num_ctx,
        )

    def _repair_and_trace(
        self,
        *,
        raw: Dict[str, Any],
        fallback: Dict[str, Any],
        seed: Dict[str, Any],
        gsdl: Dict[str, Any],
        channel: str,
        variant: str,
        llm_key: str,
        model: LocalModelProfile,
        prompt_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        data = {**fallback, **{k: v for k, v in raw.items() if v not in (None, "", [])}}
        for key in (
            "scenario_id",
            "persona_id",
            "persona_path_id",
            "role",
            "stage_id",
            "macro_stage",
            "micro_stage",
            "stage_index",
            "age_group",
            "age_group_code",
            "language_mode",
            "retrieval_mode",
            "vocabulary_band",
            "knowledge_type",
            "interaction_pattern",
            "prompt_method",
            "channel",
            "variant",
        ):
            data[key] = fallback[key]

        data["attack_type"] = ATTACK_CHANNEL_MAP.get(channel, channel) if variant == "fake" else "legitimate"
        data["difficulty_band"] = seed["difficulty_band"]
        data["pressure_band"] = seed["pressure_level"]
        data["llm_source"] = f"{llm_key}:{model.model_name}:prompt_only_default_template"
        data["generation_timestamp"] = datetime.now().isoformat()
        data["generation_meta"] = {
            **data.get("generation_meta", {}),
            "engine": self.engine_name,
            "engine_version": self.engine_version,
            "mode": "prompt_only_default_template",
            "local_model": model.as_dict(),
            "rag_used": False,
            "ontology_used": False,
            "rag_trace": [],
            "ontology_trace": None,
            "grounding_mode": "prompt_only_default_template",
            "template_id": "prompt_only_default_template_v1",
            "prompt_metadata": prompt_metadata,
            "gsdl": gsdl,
        }

        if variant == "fake":
            data["safe_indicators"] = []
            if not data.get("red_flags"):
                data["red_flags"] = ["Unexpected request requires verification"]
        else:
            data["attack_tactics"] = []
            data["psych_triggers"] = []
            data["red_flags"] = []
            if not data.get("safe_indicators"):
                data["safe_indicators"] = ["Expected workflow can be verified through approved systems"]

        try:
            scenario = ScenarioContent(**data)
            data = scenario.model_dump()
        except Exception:
            scenario = ScenarioContent(**fallback)
            data = scenario.model_dump()
            data["generation_meta"]["repair_note"] = "LLM output could not be repaired; schema-safe default template used."

        score, breakdown, flags = self.validator.score_scenario_details(
            data,
            channel,
            variant,
            int(seed["stage_index"]),
            seed["vocabulary_band"],
            seed["knowledge_type"],
            seed["role"],
        )
        data["quality_score"] = score
        data["quality_breakdown"] = breakdown
        data["quality_flags"] = self._filter_prompt_only_issues(flags)
        data["diversity_fingerprint"] = hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return data

    @staticmethod
    def _filter_prompt_only_issues(issues: List[str]) -> List[str]:
        """Remove RAG-only warnings because this engine intentionally has no RAG layer."""

        return [issue for issue in issues if issue != "scenario has no retrieved RAG grounding"]
