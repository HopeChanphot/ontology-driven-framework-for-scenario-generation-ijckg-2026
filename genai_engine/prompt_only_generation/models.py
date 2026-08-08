"""Local lightweight model profiles for the prompt-only engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class LocalModelProfile:
    """Local open-weight Ollama model profile."""

    key: str
    model_name: str
    provider: str
    role: str
    temperature: float
    max_tokens: int
    timeout: int
    num_ctx: int
    description: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


LIGHTWEIGHT_MODEL_PROFILES: Dict[str, LocalModelProfile] = {
    "qwen2_5_7b": LocalModelProfile(
        key="qwen2_5_7b",
        model_name="qwen2.5:7b-instruct",
        provider="ollama",
        role="structured_json_and_multilingual_generation",
        temperature=0.45,
        max_tokens=1500,
        timeout=240,
        num_ctx=4096,
        description="Local lightweight open-weight Qwen2.5 7B Instruct via Ollama.",
    ),
    "qwen3_8b": LocalModelProfile(
        key="qwen3_8b",
        model_name="qwen3:8b",
        provider="ollama",
        role="reasoning_and_instruction_following_generation",
        temperature=0.45,
        max_tokens=1500,
        timeout=240,
        num_ctx=4096,
        description="Local lightweight open-weight Qwen3 8B via Ollama.",
    ),
    "mistral_7b": LocalModelProfile(
        key="mistral_7b",
        model_name="mistral:7b",
        provider="ollama",
        role="concise_scenario_wording_and_fast_local_generation",
        temperature=0.50,
        max_tokens=1400,
        timeout=240,
        num_ctx=4096,
        description="Local lightweight open-weight Mistral 7B via Ollama.",
    ),
    "phi3_mini": LocalModelProfile(
        key="phi3_mini",
        model_name="phi3:mini",
        provider="ollama",
        role="low_spec_fallback_and_smoke_testing",
        temperature=0.40,
        max_tokens=1100,
        timeout=180,
        num_ctx=3072,
        description="Very small local fallback model for preliminary smoke tests.",
    ),
}
