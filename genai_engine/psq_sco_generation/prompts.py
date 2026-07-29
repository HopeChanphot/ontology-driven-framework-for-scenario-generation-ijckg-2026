"""Prompt builders for PSQ-SCO scenario generation modes."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from prompt_engine import build_scenario_system_prompt, build_scenario_user_prompt

from .models import OntologyTextDocument, SemanticPacket


def _compact_ontology_text_documents(
    documents: List[OntologyTextDocument],
    *,
    max_text_chars: int = 350,
) -> List[Dict[str, Any]]:
    """Return prompt-safe ontology document summaries without duplicating huge text."""

    compact: List[Dict[str, Any]] = []
    for doc in documents:
        compact.append(
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "document_type": doc.document_type,
                "source_ids": doc.source_ids,
                "graph_text_strategy": doc.graph_text_strategy,
                "text": doc.text[:max_text_chars],
            }
        )
    return compact


def _compact_text(text: Any, *, max_chars: int = 180) -> str:
    """Clean noisy retrieved text so local models do not copy long corpus fragments."""

    cleaned = " ".join(str(text or "").split())
    cleaned = re.sub(r"(?:\*\s*){4,}", " [repeated punctuation removed] ", cleaned)
    cleaned = re.sub(r"([!?.\-_=])(?:\s*\1){3,}", r"\1", cleaned)
    cleaned = re.sub(r"\b(.{1,24}?)\b(?:\s+\1\b){3,}", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_chars].rstrip()


def _format_compact_rag_examples(
    rag_examples: List[Dict[str, Any]],
    *,
    channel: str,
    variant: str,
    limit: int = 1,
) -> List[Dict[str, Any]]:
    """Return very small external RAG cue summaries for low-resource models."""

    compact: List[Dict[str, Any]] = []
    for item in rag_examples[:limit]:
        cue_type = "legitimate-message indicators" if variant == "real" else "social-engineering red-flag pattern"
        source_dataset = item.get("source_dataset") or item.get("source_file") or "retrieved corpus"
        compact.append(
            {
                "source_file": item.get("source_file"),
                "source_dataset": item.get("source_dataset"),
                "retrieval_tier": item.get("retrieval_tier"),
                "channel": item.get("channel"),
                "corpus_mode": item.get("corpus_mode"),
                "raw_text_withheld": True,
                "cue_summary": (
                    f"Retrieved {channel} example from {source_dataset}. Use it only as a {cue_type}; "
                    "do not copy wording, punctuation, URLs, names, or long message text."
                ),
            }
        )
    return compact


def _build_compact_generation_prompts(
    *,
    seed_dict: Dict[str, Any],
    profile_dict: Dict[str, Any],
    channel: str,
    variant: str,
    game_choices: List[Dict[str, Any]],
    rag_examples: List[Dict[str, Any]],
    semantic_packet: Optional[SemanticPacket] = None,
    ontology_text_documents: Optional[List[OntologyTextDocument]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """Build a smaller prompt for slow local models such as qwen3 on CPU."""

    attack_type = "legitimate" if variant == "real" else channel
    if channel == "sms":
        channel_fields = '"messages": ["one or two SMS messages"], "malicious_url": null'
    elif channel == "email":
        channel_fields = '"from_address": "", "from_display_name": "", "subject": "", "body_html": "", "has_attachment": false'
    else:
        channel_fields = '"caller_id": "", "caller_persona": "", "dialogue": [{"speaker": "caller", "text": "", "emotion": ""}]'

    ontology_docs = _compact_ontology_text_documents(ontology_text_documents or [], max_text_chars=220)
    packet_summary = None
    if semantic_packet:
        packet_summary = {
            "selected_template_ids": [item.get("id") for item in semantic_packet.selected_templates],
            "required_rule_ids": [item.get("id") for item in semantic_packet.required_rules],
            "must_include": semantic_packet.must_include[:6],
            "must_exclude": semantic_packet.must_exclude[:5],
        }

    system_prompt = (
        "You generate concise PersonaShield Quest cybersecurity game scenario JSON. "
        "Return one valid JSON object only. No markdown, no explanation, no prose outside JSON. "
        "Use defensive, fictional, age-suitable workplace content."
    )
    user_prompt = f"""SCENARIO SLOT
role={seed_dict['role']}
stage={seed_dict['stage_id']} / {seed_dict['macro_stage']} {seed_dict['micro_stage']}
age_group={seed_dict['age_group_code']}
channel={channel}
variant={variant}
attack_type={attack_type}
knowledge_type={seed_dict['knowledge_type']}
vocabulary_band={seed_dict['vocabulary_band']}

PERSONA CONTEXT
job_title={profile_dict['job_title']}
department={profile_dict['department']}
company={profile_dict['company_name']}
manager={profile_dict['manager_name']}
tools={', '.join(profile_dict.get('tools', [])[:3])}
tasks={', '.join(profile_dict.get('daily_tasks', [])[:3])}

LEARNING OBJECTIVES
{json.dumps(seed_dict.get('learning_objectives', [])[:3], ensure_ascii=False)}

EXTERNAL RAG CUES
{json.dumps(_format_compact_rag_examples(rag_examples, channel=channel, variant=variant), ensure_ascii=False)}

PSQ-SCO ONTOLOGY CONTROLS
semantic_packet={json.dumps(packet_summary, ensure_ascii=False)}
ontology_text={json.dumps(ontology_docs, ensure_ascii=False)}

DECISION CHOICE INTENT
{json.dumps(game_choices, ensure_ascii=False)}

TASK
Write concise scenario content. Use at least one external RAG cue when present and at least one ontology control.
Do not copy raw RAG text verbatim. Paraphrase only the useful cue pattern.
Remove repeated punctuation, repeated words, spam filler, and long corpus fragments.
Keep every string short: title <= 9 words, opening_hook <= 24 words, body_html/dialogue/message text <= 80 words, feedback <= 18 words.
For email body_html: write 2 short original sentences only, under 45 words total.
Never put raw retrieved corpus text inside body_html.
For fake scenarios: include red_flags, attack_tactics, psych_triggers, and a safe defensive correct_action.
For real scenarios: include safe_indicators and no malicious pressure.

RETURN JSON WITH THESE KEYS
{{
  "title": "",
  "opening_hook": "",
  "sender_or_caller": "",
  {channel_fields},
  "attack_tactics": [],
  "psych_triggers": [],
  "red_flags": [],
  "safe_indicators": [],
  "correct_action": "",
  "learning_focus": [],
  "referenced_entities": [],
  "game_choices": [
    {{"key": "opt_1", "label": "", "is_correct": false, "outcome": "unsafe", "feedback": ""}},
    {{"key": "opt_2", "label": "", "is_correct": false, "outcome": "unsafe", "feedback": ""}},
    {{"key": "opt_3", "label": "", "is_correct": true, "outcome": "safe", "feedback": ""}}
  ],
  "hint_text": ""
}}
"""
    metadata: Dict[str, Any] = {
        "base_prompt": "PSQ-SCO compact local scenario prompt",
        "rag_example_count": len(rag_examples),
        "mode": "ontology_text_rag" if ontology_text_documents else "ontology_prompt_rag" if semantic_packet else "prompt_rag",
        "ontology_packet_used": semantic_packet is not None,
        "ontology_text_rag_used": bool(ontology_text_documents),
        "ontology_text_document_count": len(ontology_text_documents or []),
        "ontology_text_graph_strategy": sorted({doc.graph_text_strategy for doc in ontology_text_documents or []}),
        "ontology_text_document_types": sorted({doc.document_type for doc in ontology_text_documents or []}),
        "compact_generation_prompt": True,
        "system_chars": len(system_prompt),
        "user_chars": len(user_prompt),
    }
    return system_prompt, user_prompt, metadata


def build_generation_prompts(
    *,
    seed_dict: Dict[str, Any],
    profile_dict: Dict[str, Any],
    gsdl_dict: Dict[str, Any],
    channel: str,
    variant: str,
    game_choices: List[Dict[str, Any]],
    rag_examples: List[Dict[str, Any]],
    semantic_packet: Optional[SemanticPacket] = None,
    ontology_text_documents: Optional[List[OntologyTextDocument]] = None,
    compact_prompt: bool = False,
) -> Tuple[str, str, Dict[str, Any]]:
    """Build the base prompt, optionally augmented by ontology packet/text evidence."""

    if compact_prompt:
        return _build_compact_generation_prompts(
            seed_dict=seed_dict,
            profile_dict=profile_dict,
            channel=channel,
            variant=variant,
            game_choices=game_choices,
            rag_examples=rag_examples,
            semantic_packet=semantic_packet,
            ontology_text_documents=ontology_text_documents,
        )

    system_prompt = build_scenario_system_prompt(channel, variant, seed_dict["language_mode"], seed_dict["prompt_method"])
    user_prompt = build_scenario_user_prompt(
        seed_dict,
        profile_dict,
        gsdl_dict,
        channel,
        variant,
        game_choices,
        rag_examples,
    )

    prompt_metadata: Dict[str, Any] = {
        "base_prompt": "PersonaShield v4.4 scenario prompt",
        "rag_example_count": len(rag_examples),
        "mode": "prompt_rag",
        "ontology_packet_used": False,
        "ontology_text_rag_used": False,
        "ontology_text_document_count": 0,
    }

    if semantic_packet:
        packet_json = json.dumps(semantic_packet.as_dict(), ensure_ascii=False, indent=2)
        system_prompt += """

PSQ-SCO ONTOLOGY CONTROL POLICY:
Use the semantic packet as a hard scenario-control layer. The ontology does not write prose.
It constrains template eligibility, attack or legitimate structure, content quality, evidence grounding,
and validation checks. Do not edit or reinterpret ontology identifiers. Use them as trace metadata.
"""
        user_prompt += f"""

PSQ-SCO SEMANTIC PACKET:
{packet_json}

ONTOLOGY-GUIDED GENERATION REQUIREMENTS:
- Satisfy every must_include item unless it conflicts with the fixed schema.
- Avoid every must_exclude item.
- Make the generated scenario traceable to selected_templates, required_rules, and evidence_sources.
- Put ontology trace details inside generation_meta.ontology_trace.
- Keep prose fictional, defensive, age-suitable, role-suitable, and game-playable.
"""
        prompt_metadata.update(
            {
                "mode": "ontology_prompt_rag",
                "ontology_packet_used": True,
                "ontology_template_count": len(semantic_packet.selected_templates),
                "ontology_rule_count": len(semantic_packet.required_rules),
                "ontology_source_count": len(semantic_packet.evidence_sources),
            }
        )

    if ontology_text_documents:
        docs_json = json.dumps(_compact_ontology_text_documents(ontology_text_documents), ensure_ascii=False, indent=2)
        system_prompt += """

PSQ-SCO ONTOLOGY TEXT RAG POLICY:
The ontology text documents are retrieved evidence created from the PSQ-SCO OWL graph.
Use them as grounding and control context. Preserve ontology identifiers in trace metadata.
They supplement ordinary RAG examples; they do not replace the fixed JSON schema.
When a Graph-CoT trace is present, use it as the ordered scenario-control route:
Reasoning identifies what is needed, Interaction states the graph operation, and Execution returns the ontology evidence.
"""
        user_prompt += f"""

PSQ-SCO ONTOLOGY TEXT RAG DOCUMENTS:
{docs_json}

ONTOLOGY-TEXT GENERATION REQUIREMENTS:
- Treat these documents as graph-derived retrieved evidence from the PSQ-SCO ontology.
- Use the scenario-template, validation-rule, evidence-source, and selected-subgraph-walk text to improve scenario completeness.
- If a graph_cot_trace document is present, follow its final controls when choosing template, red flags, safe indicators, fake/real separation, and evidence grounding.
- Keep the generated scenario fictional, defensive, age-suitable, role-suitable, and game-playable.
- Put ontology text source IDs inside generation_meta.ontology_text_trace when possible.
- Do not invent new ontology IDs.
- Do not expose the Graph-CoT trace as player-facing prose; use it only to guide scenario content.
"""
        prompt_metadata.update(
            {
                "mode": "ontology_text_rag",
                "ontology_text_rag_used": True,
                "ontology_text_document_count": len(ontology_text_documents),
                "ontology_text_graph_strategy": sorted({doc.graph_text_strategy for doc in ontology_text_documents}),
                "ontology_text_document_types": sorted({doc.document_type for doc in ontology_text_documents}),
            }
        )

    prompt_metadata["system_chars"] = len(system_prompt)
    prompt_metadata["user_chars"] = len(user_prompt)
    return system_prompt, user_prompt, prompt_metadata
