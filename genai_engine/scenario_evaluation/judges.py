"""Open-weight judge profiles and judge metadata helpers."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


PROVIDER_TYPES = {
    "ollama",
    "huggingface",
    "vllm",
    "llama_cpp",
    "lm_studio",
    "openai_compatible",
    "openrouter",
    "free_api",
    "paid_api",
    "mock_test",
}

LOCAL_RUNTIMES = {
    "ollama",
    "llama.cpp",
    "vllm",
    "transformers",
    "lm_studio",
    "openai_compatible",
    "none",
}

COST_MODES = {
    "free_local",
    "free_hosted",
    "institutional_gpu",
    "paid_api",
    "mock_test",
}

PROMPT_VERSION = "pcue_open_weight_v1"
RUBRIC_VERSION = "pcue_macro_micro_v1"
DEFAULT_PROFILE_NAME = "open_weight_research"


class JudgeConfigError(ValueError):
    """Raised when judge profile/configuration cannot be used safely."""


@dataclass(frozen=True)
class JudgeConfig:
    judge_id: str
    model_name: str
    model_family: str
    provider_type: str
    endpoint_url: str
    local_runtime: str
    role: str
    enabled: bool = True
    max_tokens: int = 2048
    temperature: float = 0.0
    structured_output_mode: str = "json"
    self_judge_policy: str = "flag_and_allow_if_not_sole"
    fallback_model: Optional[str] = None
    model_version: Optional[str] = None
    quantization_level: Optional[str] = None
    cost_mode: str = "free_local"
    seed: Optional[int] = 42
    prompt_version: str = PROMPT_VERSION
    rubric_version: str = RUBRIC_VERSION

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def model_size_class(self) -> str:
        return infer_model_size_class(self.model_name)

    @property
    def judge_model_type(self) -> str:
        if self.provider_type == "paid_api" or self.cost_mode == "paid_api":
            return "paid proprietary baseline"
        if self.provider_type == "mock_test":
            return "mock/test judge"
        if self.cost_mode == "free_hosted":
            return "open-weight hosted"
        return "open-weight local"

    @property
    def requires_api_key(self) -> bool:
        if self.provider_type in {"ollama", "vllm", "llama_cpp", "lm_studio", "openai_compatible", "mock_test"}:
            return False
        return self.provider_type in {"huggingface", "openrouter", "free_api", "paid_api"}

    @property
    def is_paid(self) -> bool:
        return self.provider_type == "paid_api" or self.cost_mode == "paid_api"


def _judge(**kwargs: Any) -> JudgeConfig:
    provider = kwargs.get("provider_type", "mock_test")
    runtime = kwargs.get("local_runtime", "none")
    cost = kwargs.get("cost_mode", "free_local")
    if provider not in PROVIDER_TYPES:
        raise JudgeConfigError(f"Unsupported provider_type: {provider}")
    if runtime not in LOCAL_RUNTIMES:
        raise JudgeConfigError(f"Unsupported local_runtime: {runtime}")
    if cost not in COST_MODES:
        raise JudgeConfigError(f"Unsupported cost_mode: {cost}")
    return JudgeConfig(**kwargs)


JUDGE_PROFILES: Dict[str, List[JudgeConfig]] = {
    "open_weight_research": [
        _judge(
            judge_id="llama_pedagogy",
            model_name="Llama-3.3-70B-Instruct",
            model_family="llama",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="pedagogy_structure",
            fallback_model="qwen2.5-7b-instruct",
            cost_mode="institutional_gpu",
        ),
        _judge(
            judge_id="qwen_multilingual",
            model_name="Qwen2.5-72B-Instruct",
            model_family="qwen",
            provider_type="vllm",
            endpoint_url="http://localhost:8000/v1",
            local_runtime="vllm",
            role="multilingual_json",
            fallback_model="qwen2.5-7b-instruct",
            cost_mode="institutional_gpu",
        ),
        _judge(
            judge_id="deepseek_cyber",
            model_name="DeepSeek-V3",
            model_family="deepseek",
            provider_type="openai_compatible",
            endpoint_url="http://localhost:8080/v1",
            local_runtime="openai_compatible",
            role="cyber_reasoning",
            fallback_model="llama3.1-8b-instruct",
            cost_mode="institutional_gpu",
        ),
    ],
    "local_mid_resource": [
        _judge(
            judge_id="qwen14_json",
            model_name="Qwen2.5-14B-Instruct",
            model_family="qwen",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="multilingual_json",
            fallback_model="qwen2.5-7b-instruct",
            cost_mode="free_local",
        ),
        _judge(
            judge_id="llama8_pedagogy",
            model_name="Llama-3.1-8B-Instruct",
            model_family="llama",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="pedagogy_structure",
            fallback_model="qwen2.5-7b-instruct",
            cost_mode="free_local",
        ),
        _judge(
            judge_id="mistral_nemo_usability",
            model_name="Mistral-Nemo-12B-Instruct",
            model_family="mistral",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="serious_game_usability",
            fallback_model="llama3.1-8b-instruct",
            cost_mode="free_local",
        ),
    ],
    "local_low_spec": [
        _judge(
            judge_id="qwen7_low_spec",
            model_name="Qwen2.5-7B-Instruct quantized",
            model_family="qwen",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="multilingual_json",
            fallback_model="qwen2.5-3b-instruct",
            quantization_level="quantized",
            cost_mode="free_local",
        ),
        _judge(
            judge_id="qwen3_low_spec",
            model_name="Qwen2.5-3B-Instruct quantized",
            model_family="qwen",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="pedagogy_structure",
            fallback_model="llama3.2-3b-instruct",
            quantization_level="quantized",
            cost_mode="free_local",
        ),
        _judge(
            judge_id="llama32_low_spec",
            model_name="Llama-3.2-3B-Instruct",
            model_family="llama",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="serious_game_usability",
            fallback_model="phi-4-mini-instruct",
            cost_mode="free_local",
        ),
        _judge(
            judge_id="phi4mini_low_spec",
            model_name="Phi-4-mini-instruct",
            model_family="phi",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="cyber_reasoning",
            fallback_model="qwen2.5-3b-instruct",
            cost_mode="free_local",
        ),
    ],
    "hybrid_validation": [
        _judge(
            judge_id="qwen72_research_anchor",
            model_name="Qwen2.5-72B-Instruct",
            model_family="qwen",
            provider_type="vllm",
            endpoint_url="http://localhost:8000/v1",
            local_runtime="vllm",
            role="multilingual_json",
            fallback_model="qwen2.5-7b-instruct",
            cost_mode="institutional_gpu",
        ),
        _judge(
            judge_id="qwen7_local_filter",
            model_name="Qwen2.5-7B-Instruct quantized",
            model_family="qwen",
            provider_type="ollama",
            endpoint_url="http://localhost:11434",
            local_runtime="ollama",
            role="local_preliminary_filter",
            fallback_model="qwen2.5-3b-instruct",
            quantization_level="quantized",
            cost_mode="free_local",
        ),
        _judge(
            judge_id="human_expert_sample",
            model_name="Human expert review sample",
            model_family="human",
            provider_type="mock_test",
            endpoint_url="",
            local_runtime="none",
            role="optional_human_review_sample",
            enabled=False,
            cost_mode="mock_test",
        ),
    ],
}


def infer_model_size_class(model_name: str) -> str:
    text = (model_name or "").lower()
    if "deepseek-v3" in text:
        return "large_moe"
    match = re.search(r"(\d+(?:\.\d+)?)\s*b", text)
    if match:
        size = float(match.group(1))
        if size >= 70:
            return "70b_plus"
        if size >= 13:
            return "13b_to_69b"
        if size >= 7:
            return "7b_to_12b"
        return "under_7b"
    if "human" in text:
        return "human"
    return "unknown"


def hardware_warnings(judges: Iterable[JudgeConfig]) -> List[str]:
    warnings: List[str] = []
    for judge in judges:
        if judge.model_size_class in {"70b_plus", "large_moe"}:
            warnings.append(
                f"{judge.model_name}: The selected model is 70B+ or similarly high-resource and may not run on a normal laptop without quantization or GPU memory."
            )
    if warnings:
        warnings.append("For low-spec laptop testing, use --judge-profile local_low_spec.")
        warnings.append("Low-spec judges are recommended for preliminary filtering, not final research validation.")
    return warnings


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _parse_key_value(text: str) -> tuple[str, Any]:
    if ":" not in text:
        raise JudgeConfigError(f"Invalid config line: {text}")
    key, value = text.split(":", 1)
    return key.strip(), _parse_scalar(value.strip())


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Parse the small YAML subset used by judge config examples."""

    data: Dict[str, Any] = {}
    current_list: Optional[str] = None
    current_item: Optional[Dict[str, Any]] = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if not raw_line.startswith(" ") and stripped.endswith(":"):
            current_list = stripped[:-1]
            data[current_list] = []
            current_item = None
            continue
        if current_list and stripped.startswith("- "):
            current_item = {}
            data[current_list].append(current_item)
            rest = stripped[2:].strip()
            if rest:
                key, value = _parse_key_value(rest)
                current_item[key] = value
            continue
        if current_item is not None and ":" in stripped:
            key, value = _parse_key_value(stripped)
            current_item[key] = value
            continue
        if ":" in stripped:
            key, value = _parse_key_value(stripped)
            data[key] = value
            current_item = None
            current_list = None
    return data


def load_judge_config(path: Path) -> List[JudgeConfig]:
    """Load judge configuration from JSON or YAML."""

    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
        except Exception:
            data = _parse_simple_yaml(text)
    if not isinstance(data, dict) or not isinstance(data.get("judges"), list):
        raise JudgeConfigError("Judge config must contain a top-level 'judges' list.")
    return [_judge(**dict(item)) for item in data["judges"] if isinstance(item, Mapping)]


def select_judges(
    profile_name: str = DEFAULT_PROFILE_NAME,
    judge_config: Optional[Path] = None,
    disable_paid_judges: bool = True,
    allow_paid_baseline: bool = False,
) -> List[JudgeConfig]:
    """Select enabled judges from a named profile or external config."""

    if judge_config:
        judges = load_judge_config(judge_config)
    else:
        if profile_name not in JUDGE_PROFILES:
            raise JudgeConfigError(
                f"Unknown judge profile {profile_name!r}. Available: {', '.join(sorted(JUDGE_PROFILES))}"
            )
        judges = list(JUDGE_PROFILES[profile_name])

    enabled = [judge for judge in judges if judge.enabled]
    if not enabled:
        raise JudgeConfigError("Selected judge profile/config has no enabled judges.")

    paid_judges = [judge for judge in enabled if judge.is_paid]
    if paid_judges and (disable_paid_judges or not allow_paid_baseline):
        names = ", ".join(f"{j.judge_id} ({j.provider_type}/{j.cost_mode})" for j in paid_judges)
        raise JudgeConfigError(
            "Paid proprietary judges are disabled for the primary validation pipeline. "
            f"Remove paid judges or pass --allow-paid-baseline for optional comparison baselines: {names}"
        )
    return enabled


def detect_self_judge_risk(scenario: Mapping[str, Any], judge: JudgeConfig) -> bool:
    """Flag when a judge appears to match the scenario generator model."""

    source_bits = [
        scenario.get("llm_source"),
        scenario.get("model_name"),
        scenario.get("generator_model"),
    ]
    generation_meta = scenario.get("generation_meta")
    if isinstance(generation_meta, Mapping):
        source_bits.extend(
            [
                generation_meta.get("llm_key"),
                generation_meta.get("model_name"),
                generation_meta.get("provider"),
            ]
        )
    source = " ".join(str(bit).lower() for bit in source_bits if bit)
    if not source:
        return False
    return judge.model_family.lower() in source or judge.model_name.lower() in source


def normalize_likert_score(value: Any, mapping: str = "1_to_4_safe") -> float:
    """Convert a 1-4 judge rating to normalized 0..1."""

    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return 0.0
    if mapping == "1_to_4_linear":
        return {1: 0.00, 2: 0.33, 3: 0.67, 4: 1.00}.get(numeric, 0.0)
    return {1: 0.00, 2: 0.50, 3: 0.75, 4: 1.00}.get(numeric, 0.0)


def reproducibility_metadata(judges: Iterable[JudgeConfig]) -> Dict[str, Any]:
    """Return run-level judge reproducibility metadata."""

    return {
        "date_evaluated": datetime.now(timezone.utc).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "score_mapping": "1 -> 0.00, 2 -> 0.50, 3 -> 0.75, 4 -> 1.00",
        "judges": [
            {
                **judge.as_dict(),
                "model_size_class": judge.model_size_class,
                "judge_model_type": judge.judge_model_type,
                "requires_api_key": judge.requires_api_key,
            }
            for judge in judges
        ],
    }
