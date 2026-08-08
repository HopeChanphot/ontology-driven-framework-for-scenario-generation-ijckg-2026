"""Ontology-to-text RAG documents for PSQ-SCO scenario generation.

This module converts the local OWL/RDF control ontology into compact text
documents that can be injected through the existing RAG prompt path. It keeps
the ontology read-only and deterministic: no ontology triples are edited during
generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from config import ATTACK_CHANNEL_MAP

from .models import OntologyRecord, OntologyTextDocument
from .ontology import PSQSCOOntology


class OntologyTextCorpus:
    """Create graph-to-text documents from PSQ-SCO records for local RAG use."""

    def __init__(self, ontology: PSQSCOOntology) -> None:
        self.ontology = ontology
        self.documents = self._build_record_documents()

    def summary(self) -> Dict[str, Any]:
        """Return a compact summary of the generated ontology text corpus."""

        counts: Dict[str, int] = {}
        for doc in self.documents:
            counts[doc.document_type] = counts.get(doc.document_type, 0) + 1
        return {
            "ontology_path": str(self.ontology.ontology_path),
            "document_count": len(self.documents),
            "document_counts_by_type": dict(sorted(counts.items())),
            "graph_text_strategies": sorted({doc.graph_text_strategy for doc in self.documents}),
        }

    def retrieve(
        self,
        *,
        seed: Any,
        channel: str,
        variant: str,
        limit: int = 6,
        walk_depth: int = 2,
    ) -> List[OntologyTextDocument]:
        """Retrieve graph-to-text ontology documents for one scenario seed."""

        seed_dict = seed.to_dict() if hasattr(seed, "to_dict") else dict(seed)
        packet = self.ontology.select_semantic_packet(seed, channel, variant)
        selected_ids = [item.get("id", "") for item in packet.selected_templates + packet.required_rules + packet.evidence_sources]
        selected_ids = [item for item in selected_ids if item]
        query_terms = self._query_terms(seed_dict, channel, variant)

        scored: List[tuple[int, str, OntologyTextDocument]] = []
        for doc in self.documents:
            score = self._score_document(doc, query_terms, selected_ids)
            if score > 0:
                scored.append((score, doc.doc_id, doc))
        ranked = [doc for _, _, doc in sorted(scored, key=lambda item: (-item[0], item[1]))]

        selected: List[OntologyTextDocument] = []
        selected.extend(self._ensure_document_types(ranked, ("scenario_template", "validation_rule", "evidence_source")))
        for doc in ranked:
            if len(selected) >= max(1, limit - 2):
                break
            if doc.doc_id not in {item.doc_id for item in selected}:
                selected.append(doc)

        graph_cot_doc = self._build_graph_cot_document(
            seed_dict=seed_dict,
            channel=channel,
            variant=variant,
            packet=packet,
        )
        if graph_cot_doc:
            selected.append(graph_cot_doc)

        walk_doc = self._build_walk_document(
            selected_ids=selected_ids[:5],
            seed_dict=seed_dict,
            channel=channel,
            variant=variant,
            walk_depth=walk_depth,
        )
        if walk_doc:
            selected.append(walk_doc)

        return selected[:limit]

    def _build_graph_cot_document(
        self,
        *,
        seed_dict: Dict[str, Any],
        channel: str,
        variant: str,
        packet: Any,
    ) -> OntologyTextDocument | None:
        templates = [item for item in packet.selected_templates if item.get("id")]
        rules = [item for item in packet.required_rules if item.get("id")]
        sources = [item for item in packet.evidence_sources if item.get("id")]
        if not templates and not rules and not sources:
            return None

        template_ids = [item["id"] for item in templates[:3]]
        rule_ids = [item["id"] for item in rules[:8]]
        source_ids = [item["id"] for item in sources[:5]]
        all_ids = sorted(set(template_ids + rule_ids + source_ids))
        must_include = "; ".join(packet.must_include[:8])
        must_exclude = "; ".join(packet.must_exclude[:6])

        lines = [
            "PSQ-SCO Graph-CoT trace for ontology-grounded scenario generation.",
            "Graph function definitions:",
            "- RetrieveNode[Text]: identify relevant ontology nodes by semantic and slot matching.",
            "- NodeFeature[NodeID, FeatureName]: read label, definition, type, or relation text for a node.",
            "- NeighborCheck[NodeID, NeighborType]: inspect ontology relations from a node.",
            "- NodeDegree[NodeID, NeighborType]: count relevant neighbor/relation evidence.",
            "- Finish[Controls]: conclude the scenario-control constraints to apply.",
            f"Scenario question: generate a PersonaShield Quest scenario for role={seed_dict.get('role')}, "
            f"stage={seed_dict.get('stage_id')}, macro_stage={seed_dict.get('macro_stage')}, "
            f"micro_stage={seed_dict.get('micro_stage')}, age_group={seed_dict.get('age_group_code')}, "
            f"channel={channel}, variant={variant}.",
            "Reasoning 1: First identify the ontology template nodes that fit the scenario slot.",
            f"Interaction 1: RetrieveNode[channel={channel}; variant={variant}; micro_stage={seed_dict.get('micro_stage')}]",
            f"Execution 1: selected template nodes = {self._describe_records(template_ids)}.",
            "Reasoning 2: Next inspect validation rules that constrain fake/real separation, channel consistency, persona fit, and evidence grounding.",
            f"Interaction 2: NeighborCheck[{template_ids[0] if template_ids else 'selected_template'}, validation_rule]; RetrieveNode[required validation rules]",
            f"Execution 2: selected rule nodes = {self._describe_records(rule_ids)}.",
            "Reasoning 3: Then retrieve evidence/source nodes that ground cybersecurity realism and defensive framing.",
            f"Interaction 3: RetrieveNode[evidence for channel={channel}; variant={variant}; attack_type={packet.attack_type}]",
            f"Execution 3: selected evidence nodes = {self._describe_records(source_ids)}.",
            "Reasoning 4: Summarize the generation constraints before writing scenario JSON.",
            f"Interaction 4: NodeFeature[selected_nodes, label|definition|relations]; NodeDegree[{template_ids[0] if template_ids else 'selected_template'}, relation]",
            f"Execution 4: must_include = {must_include}. must_exclude = {must_exclude}.",
            "Finish[Use the selected template, rules, evidence, must_include, and must_exclude controls. Do not invent ontology IDs.]",
        ]
        return OntologyTextDocument(
            doc_id=f"graph_cot_{channel}_{variant}_{seed_dict.get('stage_id')}_{seed_dict.get('role')}",
            title="PSQ-SCO Graph-CoT reasoning trace",
            text=self._truncate("\n".join(lines), 2600),
            document_type="graph_cot_trace",
            source_ids=all_ids,
            relevance_terms=sorted(self._query_terms(seed_dict, channel, variant)),
            graph_text_strategy="graph_chain_of_thought_reasoning_interaction_execution",
        )

    def export_jsonl(self, path: Path) -> None:
        """Export the transformed ontology text corpus for inspection."""

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for doc in self.documents:
                f.write(json.dumps(doc.as_dict(), ensure_ascii=False) + "\n")

    def _build_record_documents(self) -> List[OntologyTextDocument]:
        documents: List[OntologyTextDocument] = []
        for record in self.ontology.records:
            document_type = self._document_type(record)
            title = record.label or record.identifier
            text = self._verbalize_record(record, document_type)
            terms = self._terms_for_record(record, document_type)
            documents.append(
                OntologyTextDocument(
                    doc_id=f"ontology_record_{record.identifier}",
                    title=title,
                    text=text,
                    document_type=document_type,
                    source_ids=[record.identifier],
                    relevance_terms=terms,
                    graph_text_strategy="record_verbalization",
                )
            )
        return documents

    def _build_walk_document(
        self,
        *,
        selected_ids: Sequence[str],
        seed_dict: Dict[str, Any],
        channel: str,
        variant: str,
        walk_depth: int,
    ) -> OntologyTextDocument | None:
        starts = [identifier for identifier in selected_ids if identifier in self.ontology.by_id]
        if not starts:
            return None
        query_terms = self._query_terms(seed_dict, channel, variant)
        lines: List[str] = [
            "PSQ-SCO deterministic graph-to-text walk for scenario control.",
            f"Scenario slot: role={seed_dict.get('role')}; stage={seed_dict.get('stage_id')}; "
            f"macro_stage={seed_dict.get('macro_stage')}; micro_stage={seed_dict.get('micro_stage')}; "
            f"age_group={seed_dict.get('age_group_code')}; channel={channel}; variant={variant}.",
        ]
        source_ids: List[str] = []
        for start in starts:
            walk_lines, walk_ids = self._walk_from(start, query_terms, walk_depth)
            lines.extend(walk_lines)
            source_ids.extend(walk_ids)
        unique_ids = sorted(set(source_ids))
        if not unique_ids:
            unique_ids = sorted(set(starts))
        text = "\n".join(lines)
        return OntologyTextDocument(
            doc_id=f"ontology_walk_{channel}_{variant}_{seed_dict.get('stage_id')}_{seed_dict.get('role')}",
            title="PSQ-SCO selected subgraph walk",
            text=self._truncate(text, 2200),
            document_type="selected_subgraph_walk",
            source_ids=unique_ids,
            relevance_terms=sorted(query_terms),
            graph_text_strategy="deterministic_random_walk_graph_to_text",
        )

    def _walk_from(self, start_id: str, query_terms: set[str], max_depth: int) -> tuple[List[str], List[str]]:
        lines: List[str] = []
        visited: List[str] = []
        current_id = start_id
        for depth in range(max_depth + 1):
            record = self.ontology.by_id.get(current_id)
            if not record:
                break
            visited.append(record.identifier)
            lines.append(
                f"Walk node {depth}: {record.identifier} ({', '.join(record.types) or 'untyped'}) - "
                f"{self._short_text(record.label or record.definition or record.identifier, 180)}"
            )
            edge = self._best_edge(record, query_terms)
            if not edge:
                break
            prop, target = edge
            lines.append(f"  relation: {record.identifier} --{prop}--> {target}")
            current_id = target
        return lines, visited

    def _best_edge(self, record: OntologyRecord, query_terms: set[str]) -> tuple[str, str] | None:
        candidates: List[tuple[int, str, str]] = []
        for prop, values in record.properties.items():
            for value in values:
                target_record = self.ontology.by_id.get(value)
                haystack = " ".join(
                    [
                        prop,
                        value,
                        target_record.label if target_record else "",
                        target_record.definition if target_record else "",
                        " ".join(target_record.types) if target_record else "",
                    ]
                ).lower()
                score = sum(1 for term in query_terms if term and term in haystack)
                if value in self.ontology.by_id:
                    score += 1
                candidates.append((score, prop, value))
        if not candidates:
            return None
        _, prop, target = sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))[0]
        return prop, target

    def _describe_records(self, identifiers: Sequence[str]) -> str:
        if not identifiers:
            return "none selected"
        descriptions: List[str] = []
        for identifier in identifiers:
            record = self.ontology.by_id.get(identifier)
            if record:
                label = record.label or record.identifier
                definition = self._short_text(record.definition, 120) if record.definition else ""
                descriptions.append(f"{record.identifier} ({label}{': ' + definition if definition else ''})")
            else:
                descriptions.append(identifier)
        return "; ".join(descriptions)

    def _verbalize_record(self, record: OntologyRecord, document_type: str) -> str:
        parts = [
            f"Ontology record {record.identifier}.",
            f"Document type: {document_type}.",
        ]
        if record.types:
            parts.append(f"RDF types: {', '.join(record.types)}.")
        if record.label:
            parts.append(f"Label: {record.label}.")
        if record.definition:
            parts.append(f"Definition: {record.definition}.")
        if record.properties:
            relation_lines = []
            for prop in sorted(record.properties):
                values = ", ".join(record.properties[prop][:8])
                relation_lines.append(f"{prop}: {values}")
            parts.append("Relations: " + "; ".join(relation_lines) + ".")
        if document_type == "scenario_template":
            parts.append("Generation use: constrain scenario template eligibility, channel fit, and variant fit.")
        elif document_type == "validation_rule":
            parts.append("Generation use: enforce required validation behavior before scenario deployment.")
        elif document_type == "evidence_source":
            parts.append("Generation use: ground cues, defensive framing, and provenance metadata.")
        return self._truncate(" ".join(parts), 1800)

    def _ensure_document_types(self, ranked: Sequence[OntologyTextDocument], required_types: Iterable[str]) -> List[OntologyTextDocument]:
        selected: List[OntologyTextDocument] = []
        for document_type in required_types:
            match = next((doc for doc in ranked if doc.document_type == document_type), None)
            if match and match.doc_id not in {item.doc_id for item in selected}:
                selected.append(match)
        return selected

    def _score_document(self, doc: OntologyTextDocument, query_terms: set[str], selected_ids: Sequence[str]) -> int:
        haystack = f"{doc.title} {doc.text} {' '.join(doc.relevance_terms)}".lower()
        score = sum(2 for term in query_terms if term and term in haystack)
        if any(source_id in selected_ids for source_id in doc.source_ids):
            score += 8
        if doc.document_type in {"scenario_template", "validation_rule", "evidence_source"}:
            score += 2
        return score

    @staticmethod
    def _query_terms(seed_dict: Dict[str, Any], channel: str, variant: str) -> set[str]:
        terms = {
            channel.lower(),
            variant.lower(),
            str(seed_dict.get("role", "")).lower(),
            str(seed_dict.get("stage_id", "")).lower(),
            str(seed_dict.get("macro_stage", "")).lower(),
            str(seed_dict.get("micro_stage", "")).lower(),
            str(seed_dict.get("age_group_code", "")).lower(),
            str(seed_dict.get("knowledge_type", "")).lower(),
            ATTACK_CHANNEL_MAP.get(channel, channel).lower() if variant == "fake" else "legitimate",
        }
        for value in seed_dict.get("learning_objectives", [])[:4]:
            terms.update(str(value).lower().replace("-", " ").split())
        return {term for term in terms if term}

    @staticmethod
    def _document_type(record: OntologyRecord) -> str:
        if "ScenarioTemplate" in record.types or record.identifier.startswith("TPL_"):
            return "scenario_template"
        if record.identifier.startswith("Rule_") or any("Rule" in item or "Constraint" in item for item in record.types):
            return "validation_rule"
        if "SourceArtifact" in record.types or "TheorySource" in record.types or record.identifier.startswith("Source_"):
            return "evidence_source"
        if "CompetencyQuestion" in record.types or record.identifier.startswith("CQ"):
            return "competency_question"
        if "Class" in record.types:
            return "class"
        if "ObjectProperty" in record.types:
            return "object_property"
        if "DatatypeProperty" in record.types:
            return "datatype_property"
        return "ontology_record"

    @staticmethod
    def _terms_for_record(record: OntologyRecord, document_type: str) -> List[str]:
        values: List[str] = [record.identifier, record.label, record.definition, document_type, *record.types]
        for prop, items in record.properties.items():
            values.append(prop)
            values.extend(items)
        terms = set()
        for value in values:
            for part in str(value).replace("_", " ").replace("-", " ").replace("/", " ").split():
                cleaned = "".join(ch for ch in part.lower() if ch.isalnum())
                if cleaned:
                    terms.add(cleaned)
        return sorted(terms)

    @staticmethod
    def _short_text(text: str, limit: int) -> str:
        text = " ".join(str(text).split())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."

    @classmethod
    def _truncate(cls, text: str, limit: int) -> str:
        return cls._short_text(text, limit)
