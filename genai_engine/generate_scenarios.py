"""
PersonaShield Quest — Main Orchestrator (v4.3 quality + observability)
============================================================
Adds detailed progress logging, structured telemetry, runtime metrics,
and evaluation-ready outputs for cross-LLM comparison.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import sys
import time
import traceback
import hashlib
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from config import (
    ALL_GENERATION_LLMS,
    BUNDLE_DIR,
    CHANNELS,
    FULL_PATH_FORMULA,
    LLM_MODELS,
    MAX_RETRIES,
    MASTERY_LOOP_POLICY,
    PRODUCTION_RETRIEVAL_MODES,
    REGRESSION_POLICY,
    ROLE_BLUEPRINTS,
    TOTAL_PATHS_PER_MODE,
    TOTAL_SCENARIOS_PER_LLM_PER_MODE,
    TRAINING_LOOP_POLICY,
    VARIANTS,
    bundle_filename,
    filter_seeds,
    iter_generation_seeds,
)
from game_system import build_game_system_config
from gsdl_generator import generate_gsdl_for_seed
from llm_client import LLMClient
from prompt_engine import (
    build_profile_system_prompt,
    build_profile_user_prompt,
    build_scenario_system_prompt,
    build_scenario_user_prompt,
)
from rag_engine import RAGEngine
from schemas import ContentBundle, GameplayRules, LearningCriteria, PersonaProfile, ScenarioContent
from validator import BundleValidator

LOG_DIR = BUNDLE_DIR.parent / "logs"
TELEMETRY_DIR = BUNDLE_DIR.parent / "telemetry"
logger = logging.getLogger("personashield_v4_3.orchestrator")

PLACEHOLDER_MAP_KEYS = [
    "company_name", "manager_name", "company_email", "manager_email",
    "full_name", "job_title", "department",
    "tool_1", "tool_2", "tool_3", "tool1", "tool2", "tool3",
]
REFLECTIVE_WORDS = ["justify", "reflect", "reason", "defend", "explain", "document", "rationale"]
SUSPICIOUS_REAL_REPLACEMENTS = [
    (r"\bskip the portal\b", "follow the portal workflow"),
    (r"\bbypass approval\b", "follow the approval workflow"),
    (r"\breply yes\b", "confirm through the approved workflow"),
    (r"\bdon't wait for the portal\b", "check the portal record first"),
    (r"\bdo not route this through\b", "route this through"),
    (r"\bpush it through\b", "process it through the approved workflow"),
]


class _NullRAGEngine:
    def retrieve_for_profile_v2(self, seed, n_results: int = 3) -> List[Dict[str, Any]]:
        return []

    def retrieve_for_scenario_v2(self, seed, channel: str, variant: str, n_results: int = 4) -> List[Dict[str, Any]]:
        return []

    def retrieve_mixed(self, seed, channel: str, n_results: int = 4) -> List[Dict[str, Any]]:
        return []

    def index_knowledge_base(self, *args, **kwargs) -> int:
        return 0

    def get_stats(self) -> Dict[str, Any]:
        return {"available": False, "mode": "null (--skip-rag or unavailable)"}


class TelemetryCollector:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        self.paths = {
            "attempts": TELEMETRY_DIR / f"llm_attempts_{run_id}.jsonl",
            "scenarios": TELEMETRY_DIR / f"scenario_metrics_{run_id}.jsonl",
            "bundles": TELEMETRY_DIR / f"bundle_metrics_{run_id}.jsonl",
            "summary": TELEMETRY_DIR / f"run_summary_{run_id}.json",
        }
        self._attempts = self.paths["attempts"].open("a", encoding="utf-8")
        self._scenarios = self.paths["scenarios"].open("a", encoding="utf-8")
        self._bundles = self.paths["bundles"].open("a", encoding="utf-8")

    def _write_jsonl(self, handle, payload: Dict[str, Any]) -> None:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()

    def record_attempt(self, payload: Dict[str, Any]) -> None:
        payload = {"record_type": "llm_attempt", "run_id": self.run_id, **payload}
        self._write_jsonl(self._attempts, payload)

    def record_scenario(self, payload: Dict[str, Any]) -> None:
        payload = {"record_type": "scenario_metric", "run_id": self.run_id, **payload}
        self._write_jsonl(self._scenarios, payload)

    def record_bundle(self, payload: Dict[str, Any]) -> None:
        payload = {"record_type": "bundle_metric", "run_id": self.run_id, **payload}
        self._write_jsonl(self._bundles, payload)

    def close(self) -> None:
        self._attempts.close()
        self._scenarios.close()
        self._bundles.close()

    def write_summary(self, payload: Dict[str, Any]) -> None:
        self.paths["summary"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def setup_logging(run_id: str, log_level: str = "INFO") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, log_level.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)

    main_log = logging.FileHandler(BUNDLE_DIR.parent / "generation.log", encoding="utf-8")
    main_log.setLevel(logging.DEBUG)
    main_log.setFormatter(formatter)

    run_log = logging.FileHandler(LOG_DIR / f"generation_{run_id}.log", encoding="utf-8")
    run_log.setLevel(logging.DEBUG)
    run_log.setFormatter(formatter)

    root.addHandler(console)
    root.addHandler(main_log)
    root.addHandler(run_log)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PersonaShield Quest v4.2 content bundles with telemetry")
    parser.add_argument("--role", choices=list(ROLE_BLUEPRINTS.keys()))
    parser.add_argument("--stage", dest="stage_id")
    parser.add_argument("--age-group", dest="age_group_code")
    parser.add_argument("--retrieval-mode", choices=["THAI_LOCAL", "ENGLISH_GLOBAL", "HYBRID_COMPARE"])
    parser.add_argument("--language-mode", choices=["en", "th"])
    parser.add_argument("--llm", choices=ALL_GENERATION_LLMS)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-rag", action="store_true")
    parser.add_argument("--force-rag", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--include-hybrid", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def _deterministic_rng(key: str) -> random.Random:
    return random.Random(key)


FIRST_NAMES = ["Arisa", "Narin", "Mina", "Daniel", "Sirin", "Alex", "Pimchanok", "Natthapon", "Kanya", "Jirapat"]
LAST_NAMES = ["Tanaka", "Pattana", "Rivers", "Wirote", "Limsakul", "Anand", "Suwanna", "Kietpaisan", "Boonmee", "Sathit"]
THAI_COMPANIES = ["Siam Horizon", "Kaset Link", "Apex Digital", "MetroServe", "Blue Lotus", "Riverlight"]
EN_COMPANIES = ["SkyLink", "NorthBridge", "CrestPoint", "OrchidWorks", "VertexFlow", "BrightHarbor"]


def _make_domain(company_name: str) -> str:
    parts = [p.lower() for p in company_name.replace(",", "").replace(".", "").split() if p.lower() not in {"co", "ltd", "company", "solutions"}]
    return "-".join(parts[:3]) + ".com"


def _offline_profile(seed) -> Dict[str, Any]:
    rng = _deterministic_rng(seed.persona_path_id)
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    full_name = f"{first} {last}"
    manager_name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    company_root = rng.choice(THAI_COMPANIES if seed.language_mode == "th" else EN_COMPANIES)
    company_name = f"{company_root} Solutions Co., Ltd." if seed.language_mode == "th" else f"{company_root} Solutions"
    company_domain = _make_domain(company_name)
    company_email = f"{first.lower()}.{last.lower()}@{company_domain}"
    mgr_first, mgr_last = manager_name.split(" ", 1)
    manager_email = f"{mgr_first.lower()}.{mgr_last.lower()}@{company_domain}"
    return {
        "persona_id": seed.persona_id,
        "persona_path_id": seed.persona_path_id,
        "role": seed.role,
        "stage_id": seed.stage_id,
        "macro_stage": seed.macro_stage,
        "micro_stage": seed.micro_stage,
        "stage_index": seed.stage_index,
        "age_group": seed.age_group_label,
        "age_group_code": seed.age_group_code,
        "age_group_name": seed.age_group_name,
        "language_mode": seed.language_mode,
        "retrieval_mode": seed.retrieval_mode,
        "vocabulary_band": seed.vocabulary_band,
        "knowledge_type": seed.knowledge_type,
        "digital_familiarity_profile": seed.digital_familiarity_profile,
        "full_name": full_name,
        "job_title": seed.job_title_hint,
        "department": seed.department_hint,
        "company_name": company_name,
        "company_domain": company_domain,
        "company_email": company_email,
        "manager_name": manager_name,
        "manager_title": seed.manager_title_hint,
        "manager_email": manager_email,
        "tools": seed.tool_hints[:3],
        "daily_tasks": seed.task_hints[:3],
        "trusted_contacts": [f"{manager_name} — {seed.manager_title_hint}", f"{full_name} Colleague — Senior Coordinator"],
        "trusted_numbers": ["+66-2-100-2000", "+66-2-100-2001"],
        "policy_rules": [
            "Verify unusual requests through a trusted channel before acting.",
            "Do not share passwords, OTPs, or MFA codes.",
            "Report suspicious messages through the internal security process.",
        ],
        "story_summary": (
            f"{full_name} works as a {seed.job_title_hint} in the {seed.department_hint} team. "
            f"The role involves regular coordination, message review, and operational decisions under normal workplace pressure."
        ),
        "work_context": (
            f"A typical workday includes using {seed.tool_hints[0]} and {seed.tool_hints[1]} to handle "
            f"{seed.task_hints[0]} and {seed.task_hints[1]}. The learner context follows the stage focus of "
            f"{seed.development_focus.lower()}."
        ),
        "age_context_notes": seed.age_story_style,
    }



def _default_game_choices(channel: str, variant: str, knowledge_type: str) -> List[Dict[str, Any]]:
    if variant == "fake":
        return [
            {
                "key": "opt_1",
                "label": "Act immediately because the message sounds urgent.",
                "is_correct": False,
                "outcome": "unsafe",
                "feedback": "This accepts the request without sufficient verification and increases the risk of a social-engineering success.",
            },
            {
                "key": "opt_2",
                "label": "Ask for reassurance inside the same message or call, then continue if the sender sounds convincing.",
                "is_correct": False,
                "outcome": "unsafe",
                "feedback": "This seems cautious, but it still relies on the same untrusted communication instead of an approved verification path.",
            },
            {
                "key": "opt_3",
                "label": "Pause, verify through an approved workflow or trusted separate channel, and report it if it cannot be confirmed.",
                "is_correct": True,
                "outcome": "safe",
                "feedback": "This follows secure verification, escalation, and reporting behavior.",
            },
        ]

    good = "Confirm the sender and workflow details through the approved process, then continue the task."
    if knowledge_type == "metacognitive":
        good = "Confirm the sender and workflow details, explain why the request is legitimate, and then continue through the approved process."
    return [
        {
            "key": "opt_1",
            "label": "Report it as phishing immediately without checking anything else.",
            "is_correct": False,
            "outcome": "unsafe",
            "feedback": "This over-reports a legitimate workflow message and disrupts normal work.",
        },
        {
            "key": "opt_2",
            "label": "Treat it as automatically safe because it looks familiar and proceed without checking the workflow record.",
            "is_correct": False,
            "outcome": "unsafe",
            "feedback": "This under-verifies the request and does not apply the approved workflow checks.",
        },
        {
            "key": "opt_3",
            "label": good,
            "is_correct": True,
            "outcome": "safe",
            "feedback": "This uses calibrated verification: not blind trust, not over-reporting, but the approved process before action.",
        },
    ]


def _role_focus_terms(role: str) -> List[str]:
    mapping = {
        "IT": ["access request", "service ticket", "security portal"],
        "FINANCE": ["invoice", "payment instruction", "vendor verification"],
        "HR": ["employee record", "leave request", "onboarding document"],
        "MANAGEMENT": ["approval request", "executive coordination", "policy decision"],
        "OTHER": ["workflow request", "office update", "routine coordination"],
    }
    return mapping.get(role, mapping["OTHER"])


def _offline_scenario(seed, profile: Dict[str, Any], gsdl, channel: str, variant: str) -> Dict[str, Any]:
    role_terms = _role_focus_terms(seed.role)
    base = {
        "scenario_id": f"{seed.persona_path_id}_{channel}_{variant}",
        "persona_id": seed.persona_id,
        "persona_path_id": seed.persona_path_id,
        "role": seed.role,
        "stage_id": seed.stage_id,
        "macro_stage": seed.macro_stage,
        "micro_stage": seed.micro_stage,
        "stage_index": seed.stage_index,
        "age_group": seed.age_group_label,
        "age_group_code": seed.age_group_code,
        "language_mode": seed.language_mode,
        "retrieval_mode": seed.retrieval_mode,
        "vocabulary_band": seed.vocabulary_band,
        "knowledge_type": seed.knowledge_type,
        "interaction_pattern": seed.interaction_pattern,
        "prompt_method": seed.prompt_method,
        "channel": channel,
        "attack_type": {"sms": "smishing", "email": "phishing", "voice": "vishing"}[channel] if variant == "fake" else "legitimate",
        "variant": variant,
        "title": f"{channel.upper()} {variant.title()} Scenario",
        "opening_hook": (
            f"A {channel.upper()} request appears during normal work for {profile['job_title']} responsibilities "
            f"at {profile['company_name']} and references {role_terms[0]} using {profile['tools'][0]}."
        ),
        "sender_or_caller": profile["manager_name"] if variant == "real" else "Unknown External Contact",
        "attack_tactics": gsdl.attack_tactics if variant == "fake" else [],
        "psych_triggers": gsdl.psych_triggers if variant == "fake" else [],
        "red_flags": [],
        "safe_indicators": [],
        "correct_action": "",
        "learning_focus": [seed.development_focus, f"Practice {seed.interaction_pattern.lower()} behavior using {role_terms[0]} context"],
        "referenced_entities": [profile["company_name"], profile["manager_name"], profile["tools"][0]],
        "game_choices": _default_game_choices(channel, variant, seed.knowledge_type),
        "difficulty_band": seed.difficulty_band,
        "pressure_band": seed.pressure_level,
        "regression_reason": "single_window_support" if seed.stage_index <= 2 else None,
        "score_reward": 10 + max(0, seed.stage_index - 3),
        "score_penalty": -5,
        "show_hint": seed.stage_index <= 6,
        "hint_text": "Look for workflow consistency, sender legitimacy, and pressure cues before deciding.",
        "quality_score": 0.0,
        "llm_source": "offline_template",
    }

    if variant == "fake":
        base["red_flags"] = [
            f"Unexpected request mentioning {profile['company_name']} outside normal workflow",
            f"Pressure to act quickly without full verification through {profile['tools'][0]}",
        ] if seed.stage_index <= 3 else [
            f"Subtle mismatch between request context and trusted process at {profile['company_name']}"
        ]
        base["correct_action"] = f"Pause, verify with {profile['manager_name']} through a known trusted channel, and report if the request cannot be confirmed."
    else:
        base["safe_indicators"] = [
            f"Matches an expected business workflow at {profile['company_name']}",
            f"Uses known sender details from {profile['manager_name']} and appropriate context",
        ]
        base["correct_action"] = f"Confirm the sender and workflow details with {profile['manager_name']}, then proceed through the approved process in {profile['tools'][0]}."
        if seed.knowledge_type == "metacognitive":
            base["correct_action"] = (
                f"Confirm the message is consistent with normal workflow at {profile['company_name']}, explain why it is safe, then proceed through the approved process."
            )

    if channel == "sms":
        if variant == "fake":
            base["messages"] = [
                f"{profile['manager_name']}: Need you to review a {role_terms[0]} for {profile['company_name']} right now.",
                f"Use this link to confirm your account in {profile['tools'][0]} immediately: https://bit.ly/review-now",
            ]
            base["malicious_url"] = "https://bit.ly/review-now"
        else:
            base["messages"] = [
                f"{profile['manager_name']}: The updated {role_terms[1]} for {profile['company_name']} is in {profile['tools'][0]}.",
                "Please review it before the afternoon meeting.",
            ]
            base["malicious_url"] = None
    elif channel == "email":
        base.update(
            {
                "from_address": profile["manager_email"] if variant == "real" else f"support@{profile['company_domain'].replace('.com', '-help.com')}",
                "from_display_name": profile["manager_name"] if variant == "real" else "IT Support Desk",
                "to_role_hint": profile["job_title"],
                "subject": f"Urgent {role_terms[0]} confirmation for {profile['company_name']}" if variant == "fake" else f"Weekly {role_terms[2]} update for {profile['company_name']}",
                "body_html": (
                    f"<p>{profile['manager_name']} asks you to confirm your access to {profile['tools'][0]} immediately for {profile['company_name']} and use the attached {role_terms[2]} update.</p>"
                    if variant == "fake"
                    else f"<p>This is the normal weekly update for {profile['daily_tasks'][0]} in {profile['tools'][0]} at {profile['company_name']}.</p>"
                ),
                "has_attachment": variant == "fake",
                "attachment_name": "Access_Update.zip" if variant == "fake" else None,
                "legitimate_url": f"https://{profile['company_domain']}/portal" if variant == "real" else None,
            }
        )
    else:
        caller_name = profile["manager_name"] if variant == "real" else "External Compliance Officer"
        base.update(
            {
                "caller_id": "+66-2-555-0200",
                "caller_persona": caller_name,
                "dialogue": [
                    {
                        "speaker": "caller",
                        "text": f"Hello, this is {caller_name}. I need your help with a request related to {role_terms[0]} at {profile['company_name']} and {profile['tools'][0]}.",
                        "emotion": "neutral",
                    },
                    {
                        "speaker": "target",
                        "text": f"Please explain the request and how I should verify it with {profile['manager_name']}.",
                        "emotion": "cautious",
                    },
                ],
            }
        )
    return base


def _summarize_rag_examples(rag_examples: List[Dict[str, Any]]) -> Dict[str, Any]:
    files = sorted({str(x.get("source_file", "")) for x in rag_examples if x.get("source_file")})
    text_lengths = [len(x.get("text", "")) for x in rag_examples]
    return {
        "rag_count": len(rag_examples),
        "rag_source_files": files,
        "rag_languages": sorted({str(x.get("language", "")) for x in rag_examples if x.get("language")}),
        "rag_channels": sorted({str(x.get("channel", "")) for x in rag_examples if x.get("channel")}),
        "rag_avg_text_chars": round(sum(text_lengths) / len(text_lengths), 2) if text_lengths else 0.0,
    }


def _ensure_persona_mentions(raw: Dict[str, Any], profile: Dict[str, Any], channel: str) -> None:
    company = profile.get("company_name", "")
    manager = profile.get("manager_name", "")
    tool = (profile.get("tools") or [""])[0]
    if company and company not in (raw.get("opening_hook") or ""):
        raw["opening_hook"] = f"{raw.get('opening_hook', '')} This occurs within {company}.".strip()

    if channel == "sms":
        messages = raw.get("messages") or []
        if messages and not any(company in m or manager in m or tool in m for m in messages):
            messages[0] = f"{messages[0]} ({manager}, {company}, {tool})".strip()
        raw["messages"] = messages
    elif channel == "email":
        body_html = raw.get("body_html") or ""
        if company not in body_html and manager not in body_html and tool not in body_html:
            raw["body_html"] = f"{body_html} <p>Reference: {manager}, {company}, {tool}.</p>".strip()
    elif channel == "voice":
        dialogue = raw.get("dialogue") or []
        if dialogue:
            joined = " ".join(str(x.get("text", "")) for x in dialogue if isinstance(x, dict))
            if company not in joined and manager not in joined and tool not in joined:
                dialogue[0]["text"] = f"{dialogue[0].get('text', '')} This is about {company}, {manager}, and {tool}.".strip()
            raw["dialogue"] = dialogue


def _repair_scenario_output(raw: Dict[str, Any], seed, profile: Dict[str, Any], gsdl, channel: str, variant: str) -> Dict[str, Any]:
    base = _offline_scenario(seed, profile, gsdl, channel, variant)
    if not isinstance(raw, dict):
        return base
    repaired: Dict[str, Any] = {**base, **raw}

    for field in ["messages", "attack_tactics", "psych_triggers", "red_flags", "safe_indicators", "learning_focus", "referenced_entities"]:
        if isinstance(repaired.get(field), str):
            repaired[field] = [repaired[field]]
        elif repaired.get(field) is None:
            repaired[field] = base.get(field, [])

    if repaired.get("game_choices") is None:
        repaired["game_choices"] = base["game_choices"]

    if channel == "sms" and not repaired.get("messages"):
        repaired["messages"] = base["messages"]
    if channel == "email":
        for field in ["from_address", "subject", "body_html"]:
            if not repaired.get(field):
                repaired[field] = base[field]
    if channel == "voice":
        if not repaired.get("sender_or_caller"):
            repaired["sender_or_caller"] = repaired.get("caller_persona") or repaired.get("from_display_name") or base["sender_or_caller"]
        dialogue = repaired.get("dialogue")
        if not isinstance(dialogue, list) or len(dialogue) < 2:
            repaired["dialogue"] = base["dialogue"]

    if variant == "fake" and not repaired.get("red_flags"):
        repaired["red_flags"] = base["red_flags"]
    if variant == "real" and not repaired.get("safe_indicators"):
        repaired["safe_indicators"] = base["safe_indicators"]
    if not repaired.get("correct_action"):
        repaired["correct_action"] = base["correct_action"]

    _ensure_persona_mentions(repaired, profile, channel)
    return repaired




def _binding_map(profile: Dict[str, Any]) -> Dict[str, str]:
    tools = list(profile.get("tools") or ["approved workflow"])
    while len(tools) < 3:
        tools.append(tools[-1])
    return {
        "company_name": profile.get("company_name", ""),
        "manager_name": profile.get("manager_name", ""),
        "company_email": profile.get("company_email", ""),
        "manager_email": profile.get("manager_email", ""),
        "full_name": profile.get("full_name", ""),
        "job_title": profile.get("job_title", ""),
        "department": profile.get("department", ""),
        "tool_1": tools[0],
        "tool_2": tools[1],
        "tool_3": tools[2],
        "tool1": tools[0],
        "tool2": tools[1],
        "tool3": tools[2],
    }


def _replace_placeholders_obj(obj: Any, mapping: Dict[str, str]) -> Any:
    if isinstance(obj, str):
        text = obj
        for key, value in mapping.items():
            text = re.sub(rf"\b{re.escape(key)}\b", value, text)
        return text
    if isinstance(obj, list):
        return [_replace_placeholders_obj(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {k: _replace_placeholders_obj(v, mapping) for k, v in obj.items()}
    return obj


def _messages_haystack(raw: Dict[str, Any]) -> str:
    dialogue = " ".join(turn.get("text", "") for turn in raw.get("dialogue", []) if isinstance(turn, dict))
    return " ".join([
        raw.get("title", ""), raw.get("opening_hook", ""),
        " ".join(raw.get("messages", []) or []),
        raw.get("subject", "") or "",
        raw.get("body_html", "") or "",
        dialogue,
        raw.get("correct_action", ""),
        " ".join(raw.get("learning_focus", []) or []),
    ])


def _enforce_fake_real_separation(raw: Dict[str, Any], seed, profile: Dict[str, Any], gsdl, channel: str, variant: str, repair_actions: List[str]) -> None:
    if variant == "fake":
        if raw.get("safe_indicators"):
            repair_actions.append("cleared fake.safe_indicators")
        raw["safe_indicators"] = []
        if not raw.get("attack_tactics"):
            raw["attack_tactics"] = list(gsdl.attack_tactics)
            repair_actions.append("injected fake.attack_tactics from GSDL")
        if not raw.get("psych_triggers"):
            raw["psych_triggers"] = list(gsdl.psych_triggers)
            repair_actions.append("injected fake.psych_triggers from GSDL")
        if not raw.get("red_flags"):
            raw["red_flags"] = [
                "The request tries to create urgency before proper verification.",
                "It pushes the learner to act from the message or call itself instead of the approved workflow.",
                f"It does not clearly align with how {profile['company_name']} normally handles this process.",
            ]
            repair_actions.append("injected fake.red_flags")
    else:
        for field in ("attack_tactics", "psych_triggers", "red_flags"):
            if raw.get(field):
                repair_actions.append(f"cleared real.{field}")
            raw[field] = []
        if not raw.get("safe_indicators"):
            raw["safe_indicators"] = [
                f"The communication aligns with the approved workflow supported by {profile['tools'][0]}.",
                f"The named sender matches a known internal contact such as {profile['manager_name']}.",
                f"The request can be confirmed through standard process records at {profile['company_name']}.",
            ]
            repair_actions.append("injected real.safe_indicators")


def _ensure_entity_binding_v43(raw: Dict[str, Any], profile: Dict[str, Any], channel: str, repair_actions: List[str]) -> None:
    company = profile["company_name"]
    mgr = profile["manager_name"]
    tool = profile["tools"][0]
    raw["referenced_entities"] = [company, mgr, tool]
    hay = _messages_haystack(raw)
    if company in hay or mgr in hay or tool in hay:
        return

    if channel == "sms":
        messages = list(raw.get("messages") or [])
        messages.append(f"Use {tool} and contact {mgr} through the known internal channel if you need to verify the request at {company}.")
        raw["messages"] = messages
    elif channel == "email":
        body = raw.get("body_html") or ""
        body += f"<p>This request should be verified through {tool} and the normal process at {company}. If needed, confirm with {mgr} using a trusted internal contact method.</p>"
        raw["body_html"] = body
    else:
        dialogue = list(raw.get("dialogue") or [])
        dialogue.append({
            "speaker": "target",
            "text": f"Before I act, I will verify this in {tool} and confirm with {mgr} through the normal process at {company}.",
            "emotion": "cautious",
        })
        raw["dialogue"] = dialogue

    repair_actions.append("injected persona-binding sentence")


def _make_real_more_legitimate(raw: Dict[str, Any], channel: str, repair_actions: List[str]) -> None:
    if raw.get("variant") != "real":
        return

    def scrub(text: str) -> str:
        out = text or ""
        for pat, repl in SUSPICIOUS_REAL_REPLACEMENTS:
            out = re.sub(pat, repl, out, flags=re.I)
        return out

    if channel == "sms":
        raw["messages"] = [scrub(m) for m in raw.get("messages", [])]
    elif channel == "email":
        raw["subject"] = scrub(raw.get("subject") or "")
        raw["body_html"] = scrub(raw.get("body_html") or "")
    else:
        raw["dialogue"] = [{**d, "text": scrub(d.get("text", ""))} for d in raw.get("dialogue", [])]

    repair_actions.append("strengthened legitimacy and removed suspicious real phrasing")


def _diverse_game_choices(seed, profile: Dict[str, Any], channel: str, variant: str) -> List[Dict[str, Any]]:
    tool = profile["tools"][0]
    mgr = profile["manager_name"]

    if variant == "fake":
        partial = {
            "sms": "Reply in the same message thread and wait for reassurance.",
            "email": "Reply to the email asking if the request is really urgent, then follow whatever answer comes back.",
            "voice": "Stay on the call and let the caller walk you through the action while you verify later.",
        }[channel]
        correct = f"Pause, verify through {tool} or another trusted workflow, and report the attempt if it does not match the approved process."
        if seed.stage_index >= 8 or seed.knowledge_type == "metacognitive":
            correct = f"Pause, verify through {tool}, explain why the request breaks the approved process, document the rationale, and report it if it cannot be confirmed."

        return [
            {
                "key": "opt_1",
                "label": "Act immediately because the message sounds urgent.",
                "is_correct": False,
                "outcome": "unsafe",
                "feedback": "This accepts the request without sufficient verification and increases the risk of a social-engineering success.",
            },
            {
                "key": "opt_2",
                "label": partial,
                "is_correct": False,
                "outcome": "unsafe",
                "feedback": "This feels cautious, but it still relies on the same untrusted communication instead of an approved verification path.",
            },
            {
                "key": "opt_3",
                "label": correct,
                "is_correct": True,
                "outcome": "safe",
                "feedback": f"This follows the approved workflow, uses a trusted verification path, and escalates appropriately to {mgr} when needed.",
            },
        ]

    blind = {
        "sms": "Treat it as automatically safe and act from the text alone.",
        "email": "Assume it is fine because it matches your work area and proceed without checking the workflow record.",
        "voice": "Accept the call as legitimate and follow the instruction while the caller waits.",
    }[channel]
    correct = f"Confirm the sender and workflow details in {tool}, then proceed through the approved process."
    if seed.stage_index >= 8 or seed.knowledge_type == "metacognitive":
        correct = f"Confirm the sender and workflow details in {tool}, justify why the request is legitimate, and then proceed through the approved process."

    return [
        {
            "key": "opt_1",
            "label": "Report it as phishing immediately without checking anything else.",
            "is_correct": False,
            "outcome": "unsafe",
            "feedback": "This over-reports a legitimate workflow message and disrupts normal work.",
        },
        {
            "key": "opt_2",
            "label": "Treat it as automatically safe because it looks familiar and proceed without checking the workflow record.",
            "is_correct": False,
            "outcome": "unsafe",
            "feedback": "This under-verifies the request and does not apply the approved workflow checks.",
        },
        {
            "key": "opt_3",
            "label": correct,
            "is_correct": True,
            "outcome": "safe",
            "feedback": "This uses calibrated verification: not blind trust, not over-reporting, but the approved process before action.",
        },
    ]


def _enforce_stage_language(raw: Dict[str, Any], seed, profile: Dict[str, Any], channel: str, variant: str, repair_actions: List[str]) -> None:
    raw["game_choices"] = _diverse_game_choices(seed, profile, channel, variant)

    if seed.stage_index >= 8 or seed.knowledge_type == "metacognitive":
        if not any(w in raw.get("correct_action", "").lower() for w in REFLECTIVE_WORDS):
            raw["correct_action"] += " Explain the reasoning, justify the decision, and document the rationale."
        focus = list(raw.get("learning_focus") or [])
        if not any(any(w in f.lower() for w in REFLECTIVE_WORDS) for f in focus):
            focus.append("Explain or justify why the decision is safe or unsafe, rather than only naming the action.")
        raw["learning_focus"] = focus
        raw["hint_text"] = (
            f"Do not only decide; explain why the workflow, sender, and evidence support your action. "
            f"Use {profile['tools'][0]} to justify the decision before continuing."
        )
        repair_actions.append("enforced expert/metacognitive reflective language")


def _repair_scenario_output_v43(
    raw: Dict[str, Any],
    seed,
    profile: Dict[str, Any],
    gsdl,
    llm_key: str,
    channel: str,
    variant: str,
    validator: BundleValidator,
    rag_meta: Dict[str, Any],
    llm_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    fallback = _offline_scenario(seed, profile, gsdl, channel, variant)
    repair_actions: List[str] = []
    data = dict(raw or {})

    for key, value in fallback.items():
        if data.get(key) in (None, "", [], {}):
            data[key] = value
            repair_actions.append(f"defaulted {key}")

    data = _replace_placeholders_obj(data, _binding_map(profile))
    _enforce_fake_real_separation(data, seed, profile, gsdl, channel, variant, repair_actions)
    _ensure_entity_binding_v43(data, profile, channel, repair_actions)
    _enforce_stage_language(data, seed, profile, channel, variant, repair_actions)
    if variant == "real":
        _make_real_more_legitimate(data, channel, repair_actions)

    data["llm_source"] = f"{llm_key}:{LLM_MODELS[llm_key]['model_name']}"
    data["generation_meta"] = {
        "provider": LLM_MODELS[llm_key]["provider"],
        "model_name": LLM_MODELS[llm_key]["model_name"],
        "rag_example_count": rag_meta.get("rag_count", 0),
        "rag_languages": rag_meta.get("rag_languages", []),
        "rag_channels": rag_meta.get("rag_channels", []),
        "llm_metrics": {k: v for k, v in llm_metrics.items() if k not in {"errors", "last_call"}},
    }

    score, breakdown, flags = validator.score_scenario_details(
        data, channel, variant, seed.stage_index, seed.vocabulary_band, seed.knowledge_type, seed.role
    )
    data["quality_score"] = score
    data["quality_breakdown"] = breakdown
    data["quality_flags"] = flags
    data["repair_actions"] = sorted(set(repair_actions))
    data["diversity_fingerprint"] = hashlib.md5(
        (data["title"] + "|" + data["opening_hook"] + "|" + "|".join(c["label"] for c in data["game_choices"])).encode("utf-8")
    ).hexdigest()[:12]

    return data

def _build_learning_criteria(seed, gsdl) -> LearningCriteria:
    return LearningCriteria(
        stage_id=seed.stage_id,
        macro_stage=seed.macro_stage,
        micro_stage=seed.micro_stage,
        age_group=seed.age_group_label,
        language_mode=seed.language_mode,
        retrieval_mode=seed.retrieval_mode,
        vocabulary_band=seed.vocabulary_band,
        knowledge_type=seed.knowledge_type,
        interaction_pattern=seed.interaction_pattern,
        learning_objectives=seed.learning_objectives,
        teach_red_flags=gsdl.psych_triggers if seed.knowledge_type != "metacognitive" else ["Explain why subtle cues require reflection"],
        teach_safe_indicators=["Known sender", "Expected workflow", "No coercive urgency"],
        development_focus=seed.development_focus,
        difficulty_label=seed.difficulty_label,
        difficulty_band=seed.difficulty_band,
        gameplay_style=gsdl.deception_depth,
        hint_policy=seed.hint_policy,
        time_pressure_label=seed.time_pressure_label,
        pressure_level=seed.pressure_level,
        prompt_method=seed.prompt_method,
    )


def _build_gameplay_rules(seed) -> GameplayRules:
    return GameplayRules(
        stage_id=seed.stage_id,
        macro_stage=seed.macro_stage,
        micro_stage=seed.micro_stage,
        vocabulary_band=seed.vocabulary_band,
        hint_policy=seed.hint_policy,
        time_pressure_label=seed.time_pressure_label,
        pressure_level=seed.pressure_level,
        score_reward_correct=10 + max(0, seed.stage_index - 3),
        score_penalty_incorrect=-5,
        hint_cost=2,
        max_attempts=1,
        show_hints=seed.stage_index <= 6,
        regression_policy=REGRESSION_POLICY,
        training_loop=TRAINING_LOOP_POLICY,
        mastery_loop=MASTERY_LOOP_POLICY,
    )


def _generate_profile(seed, llm_key: str, client: LLMClient, rag, dry_run: bool, telemetry: TelemetryCollector, require_rag: bool = False, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    started = time.perf_counter()
    rag_examples = rag.retrieve_for_profile_v2(seed, n_results=3)
    rag_meta = _summarize_rag_examples(rag_examples)
    if require_rag and not rag_examples:
        logger.warning("Profile generation proceeding without RAG examples for %s", seed.persona_path_id)
    if require_rag and not rag_examples:
        logger.warning("Profile generation proceeding without RAG examples for %s", seed.persona_path_id)
    if dry_run:
        return _offline_profile(seed), {
            "phase": "profile",
            "success": True,
            "used_fallback": True,
            "attempts_used": 0,
            "duration_seconds": round(time.perf_counter() - started, 4),
            **rag_meta,
        }

    model_cfg = LLM_MODELS[llm_key]
    system_prompt = build_profile_system_prompt(seed.language_mode, seed.prompt_method)
    user_prompt = build_profile_user_prompt(seed.to_dict(), rag_examples)
    errors = []
    for attempt in range(1, MAX_RETRIES + 1):
        raw = client.generate(
            model_cfg["provider"],
            model_cfg["model_name"],
            system_prompt,
            user_prompt,
            temperature=model_cfg["temperature"],
            max_tokens=model_cfg["max_tokens"],
            timeout=model_cfg["timeout"],
            num_ctx=model_cfg["num_ctx"],
        )
        info = dict(client.last_call_info or {})
        info.update({
            "phase": "profile",
            "attempt": attempt,
            "llm_key": llm_key,
            "persona_path_id": seed.persona_path_id,
            "channel": None,
            "variant": None,
            **rag_meta,
        })
        telemetry.record_attempt(info)
        if raw:
            raw.setdefault("digital_familiarity_profile", seed.digital_familiarity_profile)
            return raw, {
                "phase": "profile",
                "success": True,
                "used_fallback": False,
                "attempts_used": attempt,
                "duration_seconds": round(time.perf_counter() - started, 4),
                **rag_meta,
                "last_call": info,
            }
        errors.append(info.get("error_message") or info.get("error_type") or "unknown_error")

    logger.warning("Profile fallback activated for %s/%s after %s failed attempts", seed.persona_path_id, llm_key, MAX_RETRIES)
    return _offline_profile(seed), {
        "phase": "profile",
        "success": False,
        "used_fallback": True,
        "attempts_used": MAX_RETRIES,
        "duration_seconds": round(time.perf_counter() - started, 4),
        **rag_meta,
        "errors": errors,
    }


def _generate_scenario(seed, profile: Dict[str, Any], gsdl, llm_key: str, channel: str, variant: str, client: LLMClient, rag, dry_run: bool, telemetry: TelemetryCollector, require_rag: bool = False, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    started = time.perf_counter()
    rag_examples = rag.retrieve_for_scenario_v2(seed, channel, variant, n_results=4)
    rag_meta = _summarize_rag_examples(rag_examples)
    if require_rag and not rag_examples:
        logger.warning("Scenario generation proceeding without RAG examples for %s/%s/%s", seed.persona_path_id, channel, variant)
    fallback = _offline_scenario(seed, profile, gsdl, channel, variant)
    if dry_run:
        return fallback, {
            "success": True,
            "used_fallback": True,
            "attempts_used": 0,
            "duration_seconds": round(time.perf_counter() - started, 4),
            **rag_meta,
        }

    model_cfg = LLM_MODELS[llm_key]
    system_prompt = build_scenario_system_prompt(channel, variant, seed.language_mode, seed.prompt_method)
    user_prompt = build_scenario_user_prompt(
        seed.to_dict(),
        profile,
        gsdl.model_dump(),
        channel,
        variant,
        _default_game_choices(channel, variant, seed.knowledge_type),
        rag_examples,
    )
    errors = []
    for attempt in range(1, MAX_RETRIES + 1):
        raw = client.generate(
            model_cfg["provider"],
            model_cfg["model_name"],
            system_prompt,
            user_prompt,
            temperature=model_cfg["temperature"],
            max_tokens=model_cfg["max_tokens"],
            timeout=model_cfg["timeout"],
            num_ctx=model_cfg["num_ctx"],
        )
        info = dict(client.last_call_info or {})
        info.update({
            "phase": "scenario",
            "attempt": attempt,
            "llm_key": llm_key,
            "persona_path_id": seed.persona_path_id,
            "channel": channel,
            "variant": variant,
            **rag_meta,
        })
        telemetry.record_attempt(info)
        if raw:
            raw.setdefault("difficulty_band", seed.difficulty_band)
            raw.setdefault("pressure_band", seed.pressure_level)
            return raw, {
                "success": True,
                "used_fallback": False,
                "attempts_used": attempt,
                "duration_seconds": round(time.perf_counter() - started, 4),
                **rag_meta,
                "last_call": info,
            }
        errors.append(info.get("error_message") or info.get("error_type") or "unknown_error")

    logger.warning("Scenario fallback activated for %s/%s/%s/%s after %s failed attempts", seed.persona_path_id, llm_key, channel, variant, MAX_RETRIES)
    return fallback, {
        "success": False,
        "used_fallback": True,
        "attempts_used": MAX_RETRIES,
        "duration_seconds": round(time.perf_counter() - started, 4),
        **rag_meta,
        "errors": errors,
    }


def _quality_stats(scenarios: List[ScenarioContent]) -> Dict[str, Any]:
    scores = [s.quality_score for s in scenarios]
    return {
        "scenario_count": len(scenarios),
        "avg_quality_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "min_quality_score": round(min(scores), 4) if scores else 0.0,
        "max_quality_score": round(max(scores), 4) if scores else 0.0,
    }


def generate_bundle(seed, llm_key: str, client: LLMClient, rag, telemetry: TelemetryCollector, dry_run: bool = False) -> Tuple[ContentBundle, Dict[str, Any]]:
    started = time.perf_counter()
    gsdl = generate_gsdl_for_seed(seed)
    game_system = build_game_system_config()

    profile_raw, profile_metrics = _generate_profile(seed, llm_key, client, rag, dry_run, telemetry)
    profile = PersonaProfile(**profile_raw)

    scenarios: List[ScenarioContent] = []
    scenario_metrics: List[Dict[str, Any]] = []
    validator = BundleValidator()

    for channel in CHANNELS:
        for variant in VARIANTS:
            scenario_started = time.perf_counter()
            raw, llm_metrics = _generate_scenario(seed, profile.model_dump(), gsdl, llm_key, channel, variant, client, rag, dry_run, telemetry)
            rag_meta = {k: llm_metrics.get(k) for k in ("rag_count", "rag_source_files", "rag_languages", "rag_channels", "rag_avg_text_chars")}
            repaired = _repair_scenario_output_v43(raw, seed, profile.model_dump(), gsdl, llm_key, channel, variant, validator, rag_meta, llm_metrics)
            used_schema_fallback = False
            schema_error = None
            try:
                scenario = ScenarioContent(**repaired)
            except ValidationError as exc:
                used_schema_fallback = True
                schema_error = str(exc)
                logger.error("Schema validation failed for %s | %s/%s/%s: %s", seed.persona_path_id, llm_key, channel, variant, exc)
                fallback = _repair_scenario_output_v43(_offline_scenario(seed, profile.model_dump(), gsdl, channel, variant), seed, profile.model_dump(), gsdl, llm_key, channel, variant, validator, rag_meta, {**llm_metrics, "used_fallback": True, "schema_error": schema_error})
                fallback["llm_source"] = f"{llm_key}:{LLM_MODELS[llm_key]['model_name']}:schema_fallback"
                scenario = ScenarioContent(**fallback)

            passed, issues = validator.validate_scenario(
                scenario.model_dump(),
                channel,
                variant,
                seed.stage_index,
                seed.vocabulary_band,
                seed.knowledge_type,
                seed.role,
            )
            scenario_record = {
                "timestamp": datetime.now().isoformat(),
                "persona_path_id": seed.persona_path_id,
                "persona_id": seed.persona_id,
                "llm_key": llm_key,
                "role": seed.role,
                "stage_id": seed.stage_id,
                "age_group_code": seed.age_group_code,
                "retrieval_mode": seed.retrieval_mode,
                "language_mode": seed.language_mode,
                "channel": channel,
                "variant": variant,
                "scenario_id": scenario.scenario_id,
                "scenario_duration_seconds": round(time.perf_counter() - scenario_started, 4),
                "llm_duration_seconds": llm_metrics.get("duration_seconds", 0.0),
                "attempts_used": llm_metrics.get("attempts_used", 0),
                "used_llm_fallback": llm_metrics.get("used_fallback", False),
                "used_schema_fallback": used_schema_fallback,
                "validation_passed": passed,
                "validation_issue_count": len(issues),
                "validation_issues": issues,
                "schema_error": schema_error,
                "quality_score": scenario.quality_score,
                "llm_source": scenario.llm_source,
                "output_chars": len(json.dumps(scenario.model_dump(), ensure_ascii=False)),
                **{k: v for k, v in llm_metrics.items() if k not in {"last_call"}},
            }
            telemetry.record_scenario(scenario_record)
            scenarios.append(scenario)
            scenario_metrics.append(scenario_record)

    bundle = ContentBundle(
        persona_id=seed.persona_id,
        persona_path_id=seed.persona_path_id,
        llm_key=llm_key,
        llm_description=LLM_MODELS[llm_key]["description"],
        persona_profile=profile,
        gsdl_descriptor=gsdl,
        learning_criteria=_build_learning_criteria(seed, gsdl),
        gameplay_rules=_build_gameplay_rules(seed),
        game_system=game_system,
        scenario_pool=scenarios,
        generation_notes={
            "dry_run": dry_run,
            "retrieval_mode": seed.retrieval_mode,
            "language_mode": seed.language_mode,
            "prompt_method": seed.prompt_method,
            "expected_paths_per_mode": TOTAL_PATHS_PER_MODE,
            "expected_scenarios_per_llm_per_mode": TOTAL_SCENARIOS_PER_LLM_PER_MODE,
            "path_formula": FULL_PATH_FORMULA,
            "profile_metrics": profile_metrics,
            "scenario_metrics_summary": {
                "scenario_count": len(scenario_metrics),
                "fallback_count": sum(1 for x in scenario_metrics if x["used_llm_fallback"] or x["used_schema_fallback"]),
                "validation_issue_count": sum(x["validation_issue_count"] for x in scenario_metrics),
            },
        },
    )

    bundle_metrics = {
        "timestamp": datetime.now().isoformat(),
        "persona_path_id": seed.persona_path_id,
        "persona_id": seed.persona_id,
        "llm_key": llm_key,
        "llm_description": LLM_MODELS[llm_key]["description"],
        "role": seed.role,
        "stage_id": seed.stage_id,
        "age_group_code": seed.age_group_code,
        "retrieval_mode": seed.retrieval_mode,
        "language_mode": seed.language_mode,
        "bundle_duration_seconds": round(time.perf_counter() - started, 4),
        "profile_duration_seconds": profile_metrics.get("duration_seconds", 0.0),
        "profile_used_fallback": profile_metrics.get("used_fallback", False),
        "scenario_fallback_count": sum(1 for x in scenario_metrics if x["used_llm_fallback"]),
        "schema_fallback_count": sum(1 for x in scenario_metrics if x["used_schema_fallback"]),
        "validation_issue_count": sum(x["validation_issue_count"] for x in scenario_metrics),
        "avg_scenario_duration_seconds": round(sum(x["scenario_duration_seconds"] for x in scenario_metrics) / len(scenario_metrics), 4) if scenario_metrics else 0.0,
        **_quality_stats(scenarios),
    }
    return bundle, bundle_metrics


def save_bundle(bundle: ContentBundle, *, force: bool = False) -> Path:
    path = BUNDLE_DIR / bundle_filename(bundle.persona_path_id, bundle.llm_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(bundle.model_dump(), f, ensure_ascii=False, indent=2)
    return path


def existing_bundle_path(persona_path_id: str, llm_key: str) -> Path:
    return BUNDLE_DIR / bundle_filename(persona_path_id, llm_key)


def should_skip_bundle(path: Path, force: bool) -> bool:
    return path.exists() and not force


def main() -> None:
    args = parse_args()
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    setup_logging(run_id, args.log_level)
    telemetry = TelemetryCollector(run_id)
    run_started = time.perf_counter()

    try:
        seeds = iter_generation_seeds(
            retrieval_modes=[args.retrieval_mode] if args.retrieval_mode else PRODUCTION_RETRIEVAL_MODES,
            include_hybrid=args.include_hybrid,
        )
        seeds = filter_seeds(
            seeds,
            role=args.role,
            stage_id=args.stage_id,
            age_group_code=args.age_group_code,
            retrieval_mode=args.retrieval_mode,
            language_mode=args.language_mode,
        )
        if args.limit and args.limit > 0:
            seeds = seeds[: args.limit]
        if not seeds:
            logger.error("No generation seeds matched the requested filters")
            sys.exit(1)

        logger.info("Run ID: %s", run_id)
        logger.info("Path formula: %s", FULL_PATH_FORMULA)

        client = LLMClient()
        rag = _NullRAGEngine() if args.skip_rag else RAGEngine()
        rag_stats = rag.get_stats() if args.skip_rag else {}
        if not args.skip_rag:
            rag.index_knowledge_base(force=args.force_rag)
            rag_stats = rag.get_stats()
            logger.info("RAG stats: %s", rag_stats)

        validator = BundleValidator()
        llm_keys = [args.llm] if args.llm else ALL_GENERATION_LLMS
        total_work_items = len(seeds) * len(llm_keys)
        completed = 0
        skipped = 0
        failed = 0
        validation_issue_counter: Counter[str] = Counter()

        for seed_index, seed in enumerate(seeds, start=1):
            logger.info(
                "Seed progress %s/%s | %s | role=%s stage=%s age=%s mode=%s",
                seed_index,
                len(seeds),
                seed.persona_path_id,
                seed.role,
                seed.stage_id,
                seed.age_group_code,
                seed.retrieval_mode,
            )
            for llm_index, llm_key in enumerate(llm_keys, start=1):
                work_path = existing_bundle_path(seed.persona_path_id, llm_key)
                work_number = completed + skipped + failed + 1
                if should_skip_bundle(work_path, args.force):
                    skipped += 1
                    logger.info(
                        "[%s/%s | %.1f%%] SKIP existing bundle %s (%s)",
                        work_number,
                        total_work_items,
                        100.0 * (work_number / total_work_items),
                        work_path.name,
                        llm_key,
                    )
                    continue

                llm_started = time.perf_counter()
                logger.info(
                    "[%s/%s | %.1f%%] Generating %s with %s (%s/%s for this seed)",
                    work_number,
                    total_work_items,
                    100.0 * (work_number / total_work_items),
                    seed.persona_path_id,
                    llm_key,
                    llm_index,
                    len(llm_keys),
                )
                try:
                    bundle, bundle_metrics = generate_bundle(seed, llm_key, client, rag, telemetry, dry_run=args.dry_run)
                    passed, issues = validator.validate_bundle(bundle)
                    if not passed:
                        validation_issue_counter.update(issues)
                        logger.warning("Bundle validation issues (%s/%s): %s", bundle.persona_path_id, llm_key, "; ".join(issues[:8]))
                    path = save_bundle(bundle, force=True)
                    bundle_metrics.update(
                        {
                            "validation_passed": passed,
                            "bundle_validation_issue_count": len(issues),
                            "bundle_validation_issues": issues,
                            "bundle_file": str(path),
                            "exists_after_save": path.exists(),
                            "wall_clock_seconds": round(time.perf_counter() - llm_started, 4),
                        }
                    )
                    telemetry.record_bundle(bundle_metrics)
                    completed += 1
                    logger.info(
                        "Done %s | llm=%s | duration=%.2fs | bundle_issues=%s | file=%s",
                        seed.persona_path_id,
                        llm_key,
                        bundle_metrics["wall_clock_seconds"],
                        len(issues),
                        path.name,
                    )
                except Exception as exc:
                    failed += 1
                    error_payload = {
                        "timestamp": datetime.now().isoformat(),
                        "persona_path_id": seed.persona_path_id,
                        "llm_key": llm_key,
                        "role": seed.role,
                        "stage_id": seed.stage_id,
                        "age_group_code": seed.age_group_code,
                        "retrieval_mode": seed.retrieval_mode,
                        "language_mode": seed.language_mode,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                    telemetry.record_bundle({"status": "failed", **error_payload})
                    logger.error("FAILED %s/%s: %s", seed.persona_path_id, llm_key, exc)
                    logger.debug("Traceback for failure:\n%s", traceback.format_exc())

        duration = round(time.perf_counter() - run_started, 4)
        summary = {
            "run_id": run_id,
            "started_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "total_seeds": len(seeds),
            "llm_keys": llm_keys,
            "total_work_items": total_work_items,
            "completed": completed,
            "skipped": skipped,
            "failed": failed,
            "rag_stats": rag_stats,
            "top_validation_issues": validation_issue_counter.most_common(25),
            "telemetry_files": {k: str(v) for k, v in telemetry.paths.items()},
        }
        telemetry.write_summary(summary)
        logger.info("Run complete | completed=%s skipped=%s failed=%s duration=%.2fs", completed, skipped, failed, duration)
        logger.info("Telemetry summary written to %s", telemetry.paths["summary"])
    finally:
        telemetry.close()


if __name__ == "__main__":
    main()
