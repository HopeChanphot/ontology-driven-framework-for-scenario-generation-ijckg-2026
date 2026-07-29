"""Data models for the separate PSQ-SCO generation engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

GenerationMode = Literal["prompt_only", "prompt_rag", "ontology_prompt_rag", "ontology_text_rag"]
ENGINE_MODES = ("prompt_only", "prompt_rag", "ontology_prompt_rag", "ontology_text_rag")
LEGACY_COMPARISON_MODES = ("prompt_rag", "ontology_prompt_rag")
THREE_WAY_COMPARISON_MODES = ("prompt_only", "prompt_rag", "ontology_text_rag")


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
        max_tokens=1900,
        timeout=240,
        num_ctx=8192,
        description="Local lightweight open-weight Qwen2.5 7B Instruct via Ollama.",
    ),
    "qwen3_8b": LocalModelProfile(
        key="qwen3_8b",
        model_name="qwen3:8b",
        provider="ollama",
        role="reasoning_and_instruction_following_generation",
        temperature=0.45,
        max_tokens=1900,
        timeout=240,
        num_ctx=8192,
        description="Local lightweight open-weight Qwen3 8B via Ollama.",
    ),
    "mistral_7b": LocalModelProfile(
        key="mistral_7b",
        model_name="mistral:7b",
        provider="ollama",
        role="concise_scenario_wording_and_fast_local_generation",
        temperature=0.50,
        max_tokens=1700,
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
        max_tokens=1400,
        timeout=180,
        num_ctx=4096,
        description="Very small local fallback model for preliminary smoke tests.",
    ),
}


@dataclass
class OntologyRecord:
    """Small record extracted from a PSQ-SCO RDF description."""

    identifier: str
    types: List[str] = field(default_factory=list)
    label: str = ""
    definition: str = ""
    properties: Dict[str, List[str]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OntologyTextDocument:
    """Graph-to-text representation of a PSQ-SCO ontology subgraph for RAG."""

    doc_id: str
    title: str
    text: str
    document_type: str
    source_ids: List[str]
    relevance_terms: List[str]
    graph_text_strategy: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def as_rag_example(self, *, channel: str, language: str) -> Dict[str, Any]:
        """Expose the ontology text document through the existing RAG example shape."""

        return {
            "channel": channel,
            "language": language,
            "corpus_mode": "ontology_text",
            "source_file": f"PSQ-SCO-v9.1::{self.doc_id}",
            "source_dataset": "personashield-psq-sco-v9.1.owl",
            "retrieval_tier": "ontology_text_rag",
            "text": self.text,
            "ontology_ids": list(self.source_ids),
            "graph_text_strategy": self.graph_text_strategy,
            "document_type": self.document_type,
            "title": self.title,
        }


@dataclass
class SemanticPacket:
    """Ontology-selected control packet sent to the prompt/RAG generation step."""

    ontology_path: str
    ontology_version: str
    mode: GenerationMode
    seed: Dict[str, Any]
    channel: str
    variant: str
    attack_type: str
    selected_templates: List[Dict[str, Any]]
    required_rules: List[Dict[str, Any]]
    evidence_sources: List[Dict[str, Any]]
    quality_controls: List[str]
    must_include: List[str]
    must_exclude: List[str]
    validation_checks: List[str]
    provenance: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioGenerationResult:
    """Generated scenario plus reproducibility metadata."""

    mode: GenerationMode
    llm_key: str
    model: Dict[str, Any]
    scenario: Dict[str, Any]
    validation_passed: bool
    validation_issues: List[str]
    semantic_packet: Optional[Dict[str, Any]]
    rag_examples: List[Dict[str, Any]]
    prompt_metadata: Dict[str, Any]
    used_live_llm: bool
    used_fallback: bool

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
