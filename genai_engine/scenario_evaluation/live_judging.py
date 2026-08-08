"""Optional live LLM judge execution for local/open-weight endpoints.

The evaluator stays cost-free by default. This module is used only when the
caller explicitly enables live judge calls.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests

from .consensus import JudgeScore, proxy_judge_scores_from_layer2
from .judges import JudgeConfig, detect_self_judge_risk, normalize_likert_score
from .weights import PCUE_CRITERIA


SYSTEM_PROMPT = """You are a PersonaShield Quest scenario validation judge.
Return strict JSON only. Score scenario quality, not learner performance."""


def build_judge_prompt(scenario_content: str, channel: str, variant: str, judge_role: str) -> str:
    """Build a PCUE judge prompt for open-weight/local LLMs."""

    return f"""
Judge role: {judge_role}
Scenario channel: {channel}
Scenario variant: {variant}

Evaluate the scenario on the PCUE criteria:
- pedagogical_quality
- cybersecurity_realism
- usability_game_clarity
- ethical_safety

Use a 1-4 scale:
1 = Fail/Poor
2 = Adequate
3 = Good
4 = Excellent

Return JSON:
{{
  "scores": {{
    "pedagogical_quality": 1,
    "cybersecurity_realism": 1,
    "usability_game_clarity": 1,
    "ethical_safety": 1
  }},
  "explanation": "",
  "confidence": 0.0
}}

Scenario:
{scenario_content}
""".strip()


def _extract_json(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            return json.loads(match.group())
    raise ValueError("Judge response did not contain parseable JSON.")


def _normalize_scores(raw_scores: Mapping[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for criterion in PCUE_CRITERIA:
        value = raw_scores.get(criterion)
        if value is None:
            normalized[criterion] = 0.0
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            normalized[criterion] = 0.0
            continue
        if numeric <= 1.0:
            normalized[criterion] = max(0.0, min(1.0, numeric))
        else:
            normalized[criterion] = normalize_likert_score(int(round(numeric)))
    return normalized


def _call_ollama(judge: JudgeConfig, prompt: str, timeout: int) -> str:
    url = f"{judge.endpoint_url.rstrip('/')}/api/chat"
    payload = {
        "model": judge.model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": judge.temperature,
            "num_predict": judge.max_tokens,
            "seed": judge.seed,
        },
    }
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json().get("message", {}).get("content", "")


def _call_openai_compatible(judge: JudgeConfig, prompt: str, timeout: int) -> str:
    base = judge.endpoint_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    payload = {
        "model": judge.model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": judge.temperature,
        "max_tokens": judge.max_tokens,
        "response_format": {"type": "json_object"},
    }
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def run_live_judge(
    judge: JudgeConfig,
    scenario: Mapping[str, Any],
    scenario_content: str,
    channel: str,
    variant: str,
    timeout: int = 120,
) -> JudgeScore:
    """Run one configured local/open-access judge and normalize PCUE scores."""

    prompt = build_judge_prompt(scenario_content, channel, variant, judge.role)
    if judge.provider_type == "ollama":
        raw_text = _call_ollama(judge, prompt, timeout)
    elif judge.provider_type in {"vllm", "llama_cpp", "lm_studio", "openai_compatible", "openrouter", "free_api", "paid_api"}:
        raw_text = _call_openai_compatible(judge, prompt, timeout)
    else:
        raise ValueError(f"Live judge execution is not implemented for provider_type={judge.provider_type}")

    parsed = _extract_json(raw_text)
    raw_scores = parsed.get("scores", parsed)
    normalized_scores = _normalize_scores(raw_scores)
    return JudgeScore(
        judge_id=judge.judge_id,
        judge_model=judge.model_name,
        model_family=judge.model_family,
        provider_type=judge.provider_type,
        local_runtime=judge.local_runtime,
        role=judge.role,
        raw_scores={criterion: raw_scores.get(criterion) for criterion in PCUE_CRITERIA},
        normalized_scores=normalized_scores,
        explanation=str(parsed.get("explanation", "")),
        confidence=parsed.get("confidence"),
        self_judge_risk=detect_self_judge_risk(scenario, judge),
        metadata={
            "prompt_version": judge.prompt_version,
            "rubric_version": judge.rubric_version,
            "temperature": judge.temperature,
            "seed": judge.seed,
            "cost_mode": judge.cost_mode,
            "model_size_class": judge.model_size_class,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "live_call": True,
        },
    )


def run_live_judges_with_proxy_fallback(
    judges: Iterable[JudgeConfig],
    scenario: Mapping[str, Any],
    scenario_content: str,
    channel: str,
    variant: str,
    layer2_scores: Mapping[str, Any],
    timeout: int = 120,
) -> List[JudgeScore]:
    """Run live judges and fall back per judge to deterministic proxy scoring."""

    results: List[JudgeScore] = []
    for judge in judges:
        if judge.provider_type == "mock_test":
            results.extend(proxy_judge_scores_from_layer2(layer2_scores, [judge], scenario))
            continue
        try:
            results.append(run_live_judge(judge, scenario, scenario_content, channel, variant, timeout=timeout))
        except Exception as exc:
            fallback = proxy_judge_scores_from_layer2(layer2_scores, [judge], scenario)[0]
            metadata = dict(fallback.metadata or {})
            metadata.update({"live_call": False, "live_call_error": str(exc)})
            results.append(
                JudgeScore(
                    judge_id=fallback.judge_id,
                    judge_model=fallback.judge_model,
                    model_family=fallback.model_family,
                    provider_type=fallback.provider_type,
                    local_runtime=fallback.local_runtime,
                    role=fallback.role,
                    raw_scores=fallback.raw_scores,
                    normalized_scores=fallback.normalized_scores,
                    explanation=f"{fallback.explanation} Live judge fallback reason: {exc}",
                    confidence=fallback.confidence,
                    self_judge_risk=fallback.self_judge_risk,
                    metadata=metadata,
                )
            )
    return results
