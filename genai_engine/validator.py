
"""
PersonaShield Quest — Validator (v4.3)
======================================
Validation and quality scoring for stage-aware bundles.
Adds strict fake/real separation checks, persona-binding checks,
repetition checks, and reflective-language checks.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple

from pydantic import ValidationError

from config import CHANNELS, MIN_QUALITY_SCORE, VARIANTS, VOCAB_BANDS
from schemas import ContentBundle, PersonaProfile, ScenarioContent

PLACEHOLDER_TOKENS = {
    "company_name", "manager_name", "company_email", "manager_email",
    "tool_1", "tool_2", "tool_3", "tool1", "tool2", "tool3",
    "full_name", "job_title", "department"
}
SUSPICIOUS_REAL_PATTERNS = [
    r"\bskip the portal\b",
    r"\bbypass approval\b",
    r"\breply yes\b",
    r"\bdo not route this through\b",
    r"\bdon't wait for the portal\b",
    r"\bpush it through\b",
]
REFLECTIVE_WORDS = ["justify", "reflect", "reason", "defend", "explain", "document", "rationale"]


class BundleValidator:
    def validate_bundle(self, bundle: ContentBundle) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        if not bundle.llm_key:
            issues.append("ContentBundle missing llm_key")
        if not bundle.llm_description:
            issues.append("ContentBundle missing llm_description")

        p_ok, p_issues = self.validate_profile(bundle.persona_profile.model_dump())
        if not p_ok:
            issues.extend(f"Profile: {i}" for i in p_issues)

        for scenario in bundle.scenario_pool:
            s_ok, s_issues = self.validate_scenario(
                scenario.model_dump(),
                scenario.channel,
                scenario.variant,
                scenario.stage_index,
                scenario.vocabulary_band,
                scenario.knowledge_type,
                scenario.role,
            )
            if not s_ok:
                issues.extend(f"{scenario.scenario_id}: {i}" for i in s_issues)

        issues.extend(self.check_persona_coherence(bundle.persona_profile.model_dump(), bundle.scenario_pool))
        issues.extend(self.check_bundle_diversity(bundle.scenario_pool))

        for channel in CHANNELS:
            for variant in VARIANTS:
                if bundle.get_scenario(channel, variant) is None:
                    issues.append(f"Missing scenario slot: {channel}/{variant}")

        return len(issues) == 0, issues

    def validate_profile(self, raw: Dict[str, Any]) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        try:
            PersonaProfile(**raw)
        except ValidationError as exc:
            for err in exc.errors():
                field = ".".join(str(x) for x in err["loc"])
                issues.append(f"Field '{field}': {err['msg']}")
            return False, issues

        if len(raw.get("tools", [])) < 2:
            issues.append("Profile must have at least 2 tools")
        if len(raw.get("daily_tasks", [])) < 2:
            issues.append("Profile must have at least 2 daily_tasks")
        if len(raw.get("policy_rules", [])) < 2:
            issues.append("Profile must have at least 2 policy_rules")
        if raw.get("company_domain") not in raw.get("company_email", ""):
            issues.append("company_email does not use company_domain")
        if raw.get("company_domain") not in raw.get("manager_email", ""):
            issues.append("manager_email does not use company_domain")
        return len(issues) == 0, issues

    def validate_scenario(
        self,
        raw: Dict[str, Any],
        channel: str,
        variant: str,
        stage_index: int,
        vocabulary_band: str,
        knowledge_type: str,
        role: str,
    ) -> Tuple[bool, List[str]]:
        issues: List[str] = []
        raw = self._sanitize(raw, variant)

        try:
            ScenarioContent(**raw)
        except ValidationError as exc:
            for err in exc.errors():
                field = ".".join(str(x) for x in err["loc"])
                issues.append(f"Schema '{field}': {err['msg']}")
            return False, issues

        issues.extend(self._check_content_rules(raw, channel, variant))
        issues.extend(self._check_stage_fit(raw, stage_index, vocabulary_band, knowledge_type))
        issues.extend(self._check_role_fit(raw, role))
        issues.extend(self._check_variant_contamination(raw, variant))
        issues.extend(self._check_placeholder_binding(raw))
        issues.extend(self._check_legitimate_clarity(raw, variant))
        issues.extend(self._check_grounding(raw))

        score, _, flags = self.score_scenario_details(
            raw, channel, variant, stage_index, vocabulary_band, knowledge_type, role
        )
        issues.extend(flags)

        if score < MIN_QUALITY_SCORE:
            issues.append(f"Quality score {score:.2f} below threshold {MIN_QUALITY_SCORE}")

        if not raw.get("llm_source") or raw.get("llm_source") in {"", "model key"}:
            issues.append("llm_source is missing or placeholder")

        return len(issues) == 0, issues

    def check_persona_coherence(self, profile_raw: Dict[str, Any], scenario_pool) -> List[str]:
        issues: List[str] = []
        required_entities = [profile_raw.get("company_name", ""), profile_raw.get("manager_name", "")]
        required_entities += profile_raw.get("tools", [])[:1]
        required_entities = [x for x in required_entities if x]

        for scenario in scenario_pool:
            raw = scenario.model_dump() if hasattr(scenario, "model_dump") else scenario
            haystack = self._scenario_haystack(raw)
            if not any(entity in haystack for entity in required_entities):
                issues.append(f"{raw['scenario_id']}: scenario does not reference key persona entities")
        return issues

    def check_bundle_diversity(self, scenario_pool) -> List[str]:
        issues: List[str] = []
        titles: Dict[str, List[str]] = {}
        hooks: Dict[str, List[str]] = {}
        choice_sigs: Dict[str, List[str]] = {}

        for scenario in scenario_pool:
            raw = scenario.model_dump() if hasattr(scenario, "model_dump") else scenario
            t = self._normalize_text(raw.get("title", ""))
            h = self._normalize_text(raw.get("opening_hook", ""))
            c = self._choice_signature(raw.get("game_choices", []))
            titles.setdefault(t, []).append(raw["scenario_id"])
            hooks.setdefault(h, []).append(raw["scenario_id"])
            choice_sigs.setdefault(c, []).append(raw["scenario_id"])

        for _, ids in titles.items():
            if len(ids) > 1:
                issues.append(f"Repeated title pattern across bundle: {', '.join(ids)}")
        for _, ids in hooks.items():
            if len(ids) > 1:
                issues.append(f"Repeated opening_hook pattern across bundle: {', '.join(ids)}")
        for _, ids in choice_sigs.items():
            if len(ids) > 2:
                issues.append(f"Repeated choice structure across bundle: {', '.join(ids)}")

        return issues

    def score_scenario_details(
        self,
        raw: Dict[str, Any],
        channel: str,
        variant: str,
        stage_index: int,
        vocabulary_band: str,
        knowledge_type: str,
        role: str,
    ) -> Tuple[float, Dict[str, float], List[str]]:
        data = self._sanitize(raw, variant)
        flags: List[str] = []

        structure = 1.0
        try:
            ScenarioContent(**data)
        except ValidationError:
            structure = 0.0
            flags.append("schema validation failed before scoring")

        variant_flags = self._check_variant_contamination(data, variant)
        binding_flags = self._check_placeholder_binding(data)
        stage_flags = self._check_stage_fit(data, stage_index, vocabulary_band, knowledge_type)
        role_flags = self._check_role_fit(data, role)
        legit_flags = self._check_legitimate_clarity(data, variant)
        grounding_flags = self._check_grounding(data)
        flags.extend(variant_flags + binding_flags + stage_flags + role_flags + legit_flags + grounding_flags)

        breakdown = {
            "structure": structure,
            "variant_consistency": 1.0 if not variant_flags else max(0.0, 1.0 - 0.25 * len(variant_flags)),
            "entity_binding": 1.0 if not binding_flags else 0.2,
            "stage_fit": 1.0 if not stage_flags else max(0.0, 1.0 - 0.2 * len(stage_flags)),
            "role_fit": 1.0 if not role_flags else 0.3,
            "legitimate_clarity": 1.0 if not legit_flags else 0.2,
            "grounding": 1.0 if not grounding_flags else 0.15,
            "diversity": self._diversity_score(data),
            "reflection_fit": self._reflection_score(data, stage_index, knowledge_type),
        }
        weights = {
            "structure": 0.18,
            "variant_consistency": 0.14,
            "entity_binding": 0.14,
            "stage_fit": 0.13,
            "role_fit": 0.08,
            "legitimate_clarity": 0.08,
            "grounding": 0.15,
            "diversity": 0.06,
            "reflection_fit": 0.04,
        }
        score = round(sum(breakdown[k] * weights[k] for k in breakdown), 4)
        return score, breakdown, flags

    def _sanitize(self, raw: Dict[str, Any], variant: str) -> Dict[str, Any]:
        data = copy.deepcopy(raw)
        for field in (
            "messages",
            "attack_tactics",
            "psych_triggers",
            "red_flags",
            "safe_indicators",
            "learning_focus",
            "referenced_entities",
            "quality_flags",
            "repair_actions",
        ):
            if isinstance(data.get(field), str):
                data[field] = [data[field]]

        if variant == "fake" and not data.get("red_flags"):
            data["red_flags"] = ["Suspicious context requires verification"]
        if variant == "real" and not data.get("safe_indicators"):
            data["safe_indicators"] = ["Known workflow and trusted sender"]

        if data.get("channel") == "voice" and len(data.get("dialogue") or []) < 2:
            data["dialogue"] = [
                {"speaker": "caller", "text": "Hello, I need your help regarding a work request.", "emotion": "neutral"},
                {"speaker": "target", "text": "Please explain the request and how I should verify it.", "emotion": "neutral"},
            ]
        return data

    def _check_content_rules(self, raw: Dict[str, Any], channel: str, variant: str) -> List[str]:
        issues = []
        if raw.get("channel") != channel:
            issues.append("channel mismatch")
        if raw.get("variant") != variant:
            issues.append("variant mismatch")
        if variant == "fake" and len(raw.get("red_flags", [])) < 1:
            issues.append("fake scenario requires red_flags")
        if variant == "real" and len(raw.get("safe_indicators", [])) < 1:
            issues.append("real scenario requires safe_indicators")
        if len(raw.get("game_choices", [])) < 3:
            issues.append("scenario should provide at least three game choices for richer judgement")
        return issues

    def _check_variant_contamination(self, raw: Dict[str, Any], variant: str) -> List[str]:
        issues = []
        if variant == "fake":
            if raw.get("safe_indicators"):
                issues.append("fake scenario should not store safe_indicators after generation")
        if variant == "real":
            if raw.get("attack_tactics"):
                issues.append("real scenario should not store attack_tactics after generation")
            if raw.get("psych_triggers"):
                issues.append("real scenario should not store psych_triggers after generation")
            if raw.get("red_flags"):
                issues.append("real scenario should not store red_flags after generation")
        return issues

    def _check_placeholder_binding(self, raw: Dict[str, Any]) -> List[str]:
        issues = []
        for ent in raw.get("referenced_entities", []):
            if isinstance(ent, str) and ent.strip().lower() in PLACEHOLDER_TOKENS:
                issues.append("referenced_entities still contain placeholders")
                break
        haystack = self._scenario_haystack(raw).lower()
        if any(tok in haystack for tok in PLACEHOLDER_TOKENS):
            issues.append("scenario text still contains placeholder tokens")
        return issues

    def _check_legitimate_clarity(self, raw: Dict[str, Any], variant: str) -> List[str]:
        if variant != "real":
            return []
        haystack = self._scenario_haystack(raw).lower()
        issues = []
        for pat in SUSPICIOUS_REAL_PATTERNS:
            if re.search(pat, haystack, flags=re.I):
                issues.append("real scenario contains suspicious/bypass phrasing")
                break
        return issues

    def _check_stage_fit(self, raw: Dict[str, Any], stage_index: int, vocabulary_band: str, knowledge_type: str) -> List[str]:
        issues = []
        body = self._scenario_haystack(raw)
        avg_sentence_len = self._avg_sentence_length(raw.get("opening_hook", "") + " " + body)
        band = VOCAB_BANDS[vocabulary_band]

        if avg_sentence_len > band["validator_max_avg_words"]:
            issues.append(f"text is too dense for {band['label']}")
        if avg_sentence_len < band["validator_min_avg_words"]:
            issues.append(f"text is too simple for {band['label']}")

        if stage_index <= 3 and raw.get("variant") == "fake" and len(raw.get("red_flags", [])) < 2:
            issues.append("early-stage fake scenario should show more explicit red flags")

        if stage_index >= 8 or knowledge_type == "metacognitive":
            focus_text = " ".join(raw.get("learning_focus", [])).lower() + " " + raw.get("correct_action", "").lower()
            choice_text = " ".join(
                (c.get("label", "") + " " + c.get("feedback", ""))
                for c in raw.get("game_choices", [])
                if isinstance(c, dict)
            ).lower()
            if not any(w in focus_text for w in REFLECTIVE_WORDS):
                issues.append("metacognitive stage needs reflective or justification-oriented language")
            if not any(w in choice_text for w in REFLECTIVE_WORDS):
                issues.append("expert-stage game choices should include justification or rationale language")
        return issues

    def _check_role_fit(self, raw: Dict[str, Any], role: str) -> List[str]:
        issues = []
        haystack = self._scenario_haystack(raw).lower()
        role_terms = {
            "FINANCE": ["invoice", "payment", "vendor", "reimbursement", "payroll", "bank"],
            "HR": ["employee", "leave", "recruit", "onboarding", "record", "policy", "benefits"],
            "IT": ["account", "access", "ticket", "mfa", "system", "portal", "security"],
            "MANAGEMENT": ["approval", "board", "executive", "policy", "manager", "decision", "meeting"],
            "OTHER": ["workflow", "request", "office", "schedule", "coordination"],
        }
        if not any(k in haystack for k in role_terms.get(role, role_terms["OTHER"])):
            issues.append(f"{role} scenario lacks role-context vocabulary")
        return issues

    def _check_grounding(self, raw: Dict[str, Any]) -> List[str]:
        issues = []
        meta = raw.get("generation_meta") or {}
        if meta.get("mode") == "prompt_only":
            return issues
        rag_count = int(meta.get("rag_example_count") or (meta.get("llm_metrics") or {}).get("rag_count", 0) or 0)
        rag_files = meta.get("rag_source_files") or (meta.get("llm_metrics") or {}).get("rag_source_files") or []
        if rag_count <= 0:
            issues.append("scenario has no retrieved RAG grounding")
        if rag_count > 0 and not rag_files:
            issues.append("scenario has rag_example_count but no rag_source_files")
        return issues

    def _diversity_score(self, raw: Dict[str, Any]) -> float:
        choices = raw.get("game_choices", []) or []
        labels = []
        for c in choices:
            if isinstance(c, dict):
                labels.append(self._normalize_text(c.get("label", "")))
        if not labels:
            return 0.0
        unique_ratio = len(set(labels)) / max(1, len(labels))
        count_bonus = 1.0 if len(labels) >= 3 else 0.5
        return round(min(1.0, 0.5 * unique_ratio + 0.5 * count_bonus), 4)

    def _reflection_score(self, raw: Dict[str, Any], stage_index: int, knowledge_type: str) -> float:
        if stage_index < 8 and knowledge_type != "metacognitive":
            return 1.0
        text = (raw.get("correct_action", "") + " " + " ".join(raw.get("learning_focus", []))).lower()
        return 1.0 if any(w in text for w in REFLECTIVE_WORDS) else 0.2

    def _choice_signature(self, choices: List[Dict[str, Any]]) -> str:
        labels = []
        for item in choices:
            if isinstance(item, dict):
                labels.append(self._normalize_text(item.get("label", "")))
        return "|".join(labels)

    def _scenario_haystack(self, raw: Dict[str, Any]) -> str:
        return " ".join([
            raw.get("title", ""),
            raw.get("opening_hook", ""),
            " ".join(raw.get("messages", []) or []),
            raw.get("subject", "") or "",
            raw.get("body_html", "") or "",
            " ".join(x.get("text", "") for x in (raw.get("dialogue") or []) if isinstance(x, dict)),
            raw.get("correct_action", "") or "",
            " ".join(raw.get("learning_focus", []) or []),
            " ".join(raw.get("red_flags", []) or []),
            " ".join(raw.get("safe_indicators", []) or []),
        ])

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = re.sub(r"<[^>]+>", " ", text or "")
        text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text.lower())
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _avg_sentence_length(text: str) -> float:
        text = re.sub(r"<[^>]+>", " ", text or "")
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return 0.0
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        if not sentences:
            return float(len(text.split()))
        return sum(len(s.split()) for s in sentences) / len(sentences)
