"""Separate scenario generation engine for PSQ-SCO v9.1."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ATTACK_CHANNEL_MAP
from gsdl_generator import generate_gsdl_for_seed
from rag_engine import RAGEngine
from schemas import ScenarioContent
from validator import BundleValidator

from .models import (
    ENGINE_MODES,
    LIGHTWEIGHT_MODEL_PROFILES,
    GenerationMode,
    LocalModelProfile,
    OntologyTextDocument,
    ScenarioGenerationResult,
    SemanticPacket,
)
from .ontology import DEFAULT_ONTOLOGY_PATH, PSQSCOOntology
from .ontology_text import OntologyTextCorpus
from .prompts import build_generation_prompts


class NullRAGEngine:
    """No-op RAG adapter used for tests, dry runs, or explicit --skip-rag."""

    def retrieve_for_scenario_v2(self, seed: Any, channel: str, variant: str, n_results: int = 4) -> List[Dict[str, Any]]:
        return []

    def index_knowledge_base(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def get_stats(self) -> Dict[str, Any]:
        return {"available": False, "reason": "disabled"}


class PSQSCOGenerationEngine:
    """Generate PersonaShield scenarios across prompt, RAG, and ontology-grounded modes."""

    def __init__(
        self,
        *,
        ontology_path: Path | str = DEFAULT_ONTOLOGY_PATH,
        use_rag: bool = True,
        rag: Optional[Any] = None,
    ) -> None:
        self.ontology = PSQSCOOntology(ontology_path)
        self.ontology_text_corpus = OntologyTextCorpus(self.ontology)
        self.rag = rag if rag is not None else (RAGEngine() if use_rag else NullRAGEngine())
        self.validator = BundleValidator()
        self.last_llm_call_info: Dict[str, Any] = {}

    def generate_one(
        self,
        *,
        seed: Any,
        channel: str,
        variant: str,
        mode: GenerationMode,
        llm_key: str = "qwen2_5_7b",
        dry_run: bool = False,
        n_rag_examples: int = 4,
        ontology_text_limit: int = 5,
        llm_timeout: Optional[int] = None,
        llm_max_tokens: Optional[int] = None,
        llm_num_ctx: Optional[int] = None,
        llm_temperature: Optional[float] = None,
        compact_prompt: bool = False,
        llm_parse_retries: int = 1,
    ) -> ScenarioGenerationResult:
        """Generate one scenario slot using one supported generation mode."""

        if mode not in ENGINE_MODES:
            raise ValueError(f"Unsupported mode {mode!r}; expected one of {ENGINE_MODES}")
        if llm_key not in LIGHTWEIGHT_MODEL_PROFILES:
            raise ValueError(f"Unknown local model key {llm_key!r}; expected {sorted(LIGHTWEIGHT_MODEL_PROFILES)}")

        model = LIGHTWEIGHT_MODEL_PROFILES[llm_key]
        seed_dict = seed.to_dict() if hasattr(seed, "to_dict") else dict(seed)
        gsdl = generate_gsdl_for_seed(seed)
        gsdl_dict = gsdl.model_dump() if hasattr(gsdl, "model_dump") else dict(gsdl)
        profile = self._offline_profile(seed_dict)
        game_choices = self._default_game_choices(variant, seed_dict["knowledge_type"])
        if mode == "prompt_only":
            external_rag_examples: List[Dict[str, Any]] = []
        else:
            external_rag_examples = self.rag.retrieve_for_scenario_v2(seed, channel, variant, n_results=n_rag_examples)
        external_rag_count = len(external_rag_examples)
        semantic_packet = self.ontology.select_semantic_packet(seed, channel, variant) if mode == "ontology_prompt_rag" else None
        ontology_text_documents: List[OntologyTextDocument] = []
        ontology_rag_examples: List[Dict[str, Any]] = []
        if mode == "ontology_text_rag":
            ontology_text_documents = self.ontology_text_corpus.retrieve(
                seed=seed,
                channel=channel,
                variant=variant,
                limit=max(1, ontology_text_limit),
            )
            ontology_rag_examples = [
                doc.as_rag_example(channel=channel, language=seed_dict.get("language_mode", "en"))
                for doc in ontology_text_documents
            ]
        combined_rag_examples = [*external_rag_examples, *ontology_rag_examples]
        system_prompt, user_prompt, prompt_metadata = build_generation_prompts(
            seed_dict=seed_dict,
            profile_dict=profile,
            gsdl_dict=gsdl_dict,
            channel=channel,
            variant=variant,
            game_choices=game_choices,
            rag_examples=external_rag_examples,
            semantic_packet=semantic_packet,
            ontology_text_documents=ontology_text_documents,
            compact_prompt=compact_prompt,
        )
        if llm_key == "qwen3_8b":
            user_prompt += (
                "\n\nQWEN3 CONTROL:\n"
                "/no_think\n"
                "Return JSON only. No explanation. No markdown. Do not include chain-of-thought. "
                "Return only one compact JSON object matching the schema. Keep all strings short.\n"
            )
        if mode == "prompt_only":
            prompt_metadata.update({"mode": "prompt_only", "rag_example_count": 0})
        prompt_metadata["external_rag_example_count"] = external_rag_count
        prompt_metadata["ontology_text_rag_example_count"] = len(ontology_text_documents)
        prompt_metadata["combined_rag_context_count"] = len(combined_rag_examples)
        if llm_key == "qwen3_8b":
            prompt_metadata["qwen3_no_think"] = True
            prompt_metadata["user_chars"] = len(user_prompt)
        prompt_metadata["rag_runtime_status"] = self._rag_runtime_status()

        used_live_llm = False
        used_fallback = False
        raw: Optional[Dict[str, Any]] = None
        if not dry_run:
            try:
                call_model = model
                overrides = {}
                if llm_timeout:
                    overrides["timeout"] = llm_timeout
                if llm_max_tokens:
                    overrides["max_tokens"] = llm_max_tokens
                if llm_num_ctx:
                    overrides["num_ctx"] = llm_num_ctx
                if llm_temperature is not None:
                    overrides["temperature"] = llm_temperature
                if overrides:
                    call_model = replace(model, **overrides)
                raw = self._call_local_llm(
                    call_model,
                    system_prompt,
                    user_prompt,
                    parse_retries=max(0, llm_parse_retries),
                )
                if self.last_llm_call_info:
                    prompt_metadata["live_llm_call_info"] = self.last_llm_call_info
            except Exception as exc:
                prompt_metadata["live_llm_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc)[:1000],
                    "model_key": llm_key,
                    "model_name": model.model_name,
                    "provider": model.provider,
                    "fallback_used": True,
                }
                raw = None
            used_live_llm = raw is not None
            if raw is None and self.last_llm_call_info:
                prompt_metadata["live_llm_call_info"] = self.last_llm_call_info
                prompt_metadata["live_llm_error"] = {
                    "type": self.last_llm_call_info.get("error_type") or "llm_returned_no_parseable_json",
                    "message": self.last_llm_call_info.get("error_message") or "Local LLM did not return parseable JSON.",
                    "model_key": llm_key,
                    "model_name": model.model_name,
                    "provider": model.provider,
                    "fallback_used": True,
                }
        if raw is None:
            raw = self._offline_scenario(seed_dict, profile, gsdl_dict, channel, variant)
            used_fallback = True

        scenario = self._repair_and_trace(
            raw,
            seed_dict,
            profile,
            gsdl_dict,
            channel,
            variant,
            llm_key,
            model,
            mode,
            combined_rag_examples,
            semantic_packet,
            ontology_text_documents,
            prompt_metadata,
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

        return ScenarioGenerationResult(
            mode=mode,
            llm_key=llm_key,
            model=model.as_dict(),
            scenario=scenario,
            validation_passed=validation_passed,
            validation_issues=validation_issues,
            semantic_packet=semantic_packet.as_dict() if semantic_packet else None,
            rag_examples=[self._compact_rag_example(item) for item in combined_rag_examples],
            prompt_metadata=prompt_metadata,
            used_live_llm=used_live_llm,
            used_fallback=used_fallback,
        )

    def _call_local_llm(
        self,
        model: LocalModelProfile,
        system_prompt: str,
        user_prompt: str,
        *,
        parse_retries: int = 1,
    ) -> Optional[Dict[str, Any]]:
        from llm_client import LLMClient

        client = LLMClient()
        result = client.generate(
            model.provider,
            model.model_name,
            system_prompt,
            user_prompt,
            temperature=model.temperature,
            max_tokens=model.max_tokens,
            timeout=model.timeout,
            num_ctx=model.num_ctx,
        )
        attempts = [dict(client.last_call_info)]
        if result is not None:
            self.last_llm_call_info = {"attempts": attempts, **attempts[-1]}
            return result
        for retry_index in range(parse_retries):
            if client.last_call_info.get("error_type") != "parse_error":
                break
            retry_max_tokens = min(max(model.max_tokens + 600, 1800), 2400)
            retry_model = replace(
                model,
                max_tokens=retry_max_tokens,
                timeout=max(model.timeout, 1200),
                temperature=min(model.temperature, 0.2),
            )
            retry_user_prompt = (
                user_prompt
                + "\n\nSTRICT JSON RETRY:\n"
                + "The previous response was not parseable JSON. Return one complete JSON object only. "
                + "Close every string, list, and object. Do not include markdown, comments, or text after the JSON. "
                + "Keep scenario wording concise if needed, but do not truncate the JSON object.\n"
            )
            result = client.generate(
                retry_model.provider,
                retry_model.model_name,
                system_prompt,
                retry_user_prompt,
                temperature=retry_model.temperature,
                max_tokens=retry_model.max_tokens,
                timeout=retry_model.timeout,
                num_ctx=retry_model.num_ctx,
            )
            retry_info = dict(client.last_call_info)
            retry_info["parse_retry_index"] = retry_index + 1
            retry_info["retry_max_tokens"] = retry_model.max_tokens
            retry_info["retry_timeout"] = retry_model.timeout
            attempts.append(retry_info)
            if result is not None:
                self.last_llm_call_info = {"attempts": attempts, **retry_info}
                return result
        self.last_llm_call_info = {"attempts": attempts, **attempts[-1]}
        return None

    def _repair_and_trace(
        self,
        raw: Dict[str, Any],
        seed: Dict[str, Any],
        profile: Dict[str, Any],
        gsdl: Dict[str, Any],
        channel: str,
        variant: str,
        llm_key: str,
        model: LocalModelProfile,
        mode: GenerationMode,
        rag_examples: List[Dict[str, Any]],
        semantic_packet: Optional[SemanticPacket],
        ontology_text_documents: List[OntologyTextDocument],
        prompt_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = self._offline_scenario(seed, profile, gsdl, channel, variant)
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
        data["llm_source"] = f"{llm_key}:{model.model_name}:{mode}"
        data["generation_timestamp"] = datetime.now().isoformat()
        ontology_source_ids = []
        if semantic_packet:
            ontology_source_ids = [item.get("id", "") for item in semantic_packet.evidence_sources if item.get("id")]
        ontology_text_source_ids = sorted({source_id for doc in ontology_text_documents for source_id in doc.source_ids})
        grounding_count = len(rag_examples) if rag_examples else len(ontology_source_ids) + len(ontology_text_source_ids)
        grounding_sources = sorted({str(item.get("source_file", "")) for item in rag_examples if item.get("source_file")})
        if not grounding_sources and (ontology_source_ids or ontology_text_source_ids):
            grounding_sources = ontology_source_ids + ontology_text_source_ids
        data["generation_meta"] = {
            **data.get("generation_meta", {}),
            "engine": "psq_sco_generation",
            "engine_version": "v1.1_ontology_text_rag",
            "mode": mode,
            "local_model": model.as_dict(),
            "ontology_trace": semantic_packet.as_dict() if semantic_packet else None,
            "ontology_text_trace": {
                "ontology_path": str(self.ontology.ontology_path),
                "ontology_version": "PSQ-SCO v9.1",
                "document_count": len(ontology_text_documents),
                "documents": [doc.as_dict() for doc in ontology_text_documents],
                "source_ids": ontology_text_source_ids,
                "graph_text_strategy": sorted({doc.graph_text_strategy for doc in ontology_text_documents}),
            }
            if ontology_text_documents
            else None,
            "rag_trace": [self._compact_rag_example(item) for item in rag_examples],
            "rag_example_count": grounding_count,
            "rag_source_files": grounding_sources,
            "grounding_mode": "ontology_text_rag"
            if ontology_text_documents
            else "rag"
            if rag_examples
            else "ontology_evidence"
            if ontology_source_ids
            else "none",
            "rag_runtime_status": prompt_metadata.get("rag_runtime_status"),
            "prompt_metadata": prompt_metadata,
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
            data["generation_meta"]["repair_note"] = "LLM output could not be repaired; schema-safe fallback used."
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
        data["quality_flags"] = flags
        data["diversity_fingerprint"] = hashlib.md5(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return data

    def _rag_runtime_status(self) -> Dict[str, Any]:
        """Return best-effort RAG health metadata without interrupting generation."""

        if not hasattr(self.rag, "get_stats"):
            return {"available": False, "reason": "rag_adapter_has_no_stats"}
        try:
            stats = self.rag.get_stats()
        except Exception as exc:
            return {"available": False, "reason": "rag_stats_error", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
        if not isinstance(stats, dict):
            return {"available": False, "reason": "rag_stats_not_dict"}
        return stats

    @staticmethod
    def _offline_profile(seed: Dict[str, Any]) -> Dict[str, Any]:
        rng = random.Random(seed["persona_path_id"])
        first_names = ["Arisa", "Narin", "Mina", "Daniel", "Sirin", "Alex", "Kanya", "Jirapat"]
        last_names = ["Tanaka", "Pattana", "Rivers", "Wirote", "Limsakul", "Anand", "Boonmee"]
        first = rng.choice(first_names)
        last = rng.choice(last_names)
        manager_first = rng.choice(first_names)
        manager_last = rng.choice(last_names)
        company_root = rng.choice(["SkyLink", "NorthBridge", "CrestPoint", "OrchidWorks", "VertexFlow"])
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

    @staticmethod
    def _default_game_choices(variant: str, knowledge_type: str) -> List[Dict[str, Any]]:
        if variant == "fake":
            return [
                {"key": "opt_1", "label": "Act immediately.", "is_correct": False, "outcome": "unsafe", "feedback": "This skips verification."},
                {"key": "opt_2", "label": "Ask inside the same message, then proceed.", "is_correct": False, "outcome": "unsafe", "feedback": "This still uses an untrusted channel."},
                {"key": "opt_3", "label": "Pause, verify through an approved channel, and report if needed.", "is_correct": True, "outcome": "safe", "feedback": "This follows safe defensive behavior."},
            ]
        good = "Verify the workflow and continue through the approved process."
        if knowledge_type == "metacognitive":
            good = "Verify the workflow, explain why it is legitimate, and continue through the approved process."
        return [
            {"key": "opt_1", "label": "Report it immediately without checking.", "is_correct": False, "outcome": "unsafe", "feedback": "This over-reports a normal workflow."},
            {"key": "opt_2", "label": "Trust it automatically because it looks familiar.", "is_correct": False, "outcome": "unsafe", "feedback": "This under-verifies the request."},
            {"key": "opt_3", "label": good, "is_correct": True, "outcome": "safe", "feedback": "This uses calibrated verification."},
        ]

    def _offline_scenario(
        self,
        seed: Dict[str, Any],
        profile: Dict[str, Any],
        gsdl: Dict[str, Any],
        channel: str,
        variant: str,
    ) -> Dict[str, Any]:
        attack_type = ATTACK_CHANNEL_MAP.get(channel, channel) if variant == "fake" else "legitimate"
        suspicious = variant == "fake"
        title = f"{profile['department']} {channel.upper()} {'verification request' if suspicious else 'workflow notice'}"
        common = {
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
            "game_choices": self._default_game_choices(variant, seed["knowledge_type"]),
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
            "llm_source": "offline_fallback",
            "generation_meta": {"gsdl": gsdl},
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
                        {"speaker": "caller", "text": f"I am calling about your {profile['tools'][0]} workflow.", "emotion": "urgent" if suspicious else "neutral"},
                        {"speaker": "target", "text": "I will verify this through the approved process before acting.", "emotion": "calm"},
                    ],
                }
            )
        return common

    @staticmethod
    def _compact_rag_example(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "channel": item.get("channel"),
            "language": item.get("language"),
            "corpus_mode": item.get("corpus_mode"),
            "source_file": item.get("source_file"),
            "source_dataset": item.get("source_dataset"),
            "retrieval_tier": item.get("retrieval_tier"),
            "document_type": item.get("document_type"),
            "title": item.get("title"),
            "ontology_ids": item.get("ontology_ids"),
            "graph_text_strategy": item.get("graph_text_strategy"),
            "text_preview": str(item.get("text", ""))[:240],
        }
