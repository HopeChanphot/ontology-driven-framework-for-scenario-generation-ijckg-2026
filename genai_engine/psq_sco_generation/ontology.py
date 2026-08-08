"""PSQ-SCO v9.1 ontology loading and semantic-packet selection."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree as ET

from config import ATTACK_CHANNEL_MAP

from .models import OntologyRecord, SemanticPacket

# Portable handover default: the ontology is packaged beside genai_engine.
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ONTOLOGY_PATH = (
    PACKAGE_ROOT / "ontology" / "ontology" / "personashield-psq-sco-v9.1.owl"
)

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
PSQ = "http://personashield.ait.ac.th/ontology/psq-sco#"
DCTERMS = "http://purl.org/dc/terms/"
XML_NS = "http://www.w3.org/XML/1998/namespace"

NS = {
    "rdf": RDF,
    "rdfs": RDFS,
    "owl": OWL,
    "skos": SKOS,
    "psq": PSQ,
    "dcterms": DCTERMS,
}

REQUIRED_RULE_IDS = (
    "Rule_TemplateEligibility",
    "Rule_RequiredAttackStructure",
    "Rule_LegitimateScenarioSeparation",
    "Rule_ChannelConsistency",
    "Rule_PersonaFit",
    "Rule_EvidenceRequirement",
    "Rule_QualityAcceptance",
    "Rule_QualityRejection",
)


def _local_name(uri: str) -> str:
    if not uri:
        return ""
    return uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _node_text(node: ET.Element, tag: str) -> str:
    found = node.find(tag, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


class PSQSCOOntology:
    """Lightweight RDF/XML reader tailored to the PSQ-SCO v9.1 control ontology."""

    def __init__(self, ontology_path: Path | str = DEFAULT_ONTOLOGY_PATH) -> None:
        self.ontology_path = Path(ontology_path)
        if not self.ontology_path.exists():
            raise FileNotFoundError(f"PSQ-SCO ontology file not found: {self.ontology_path}")
        self.records = self._load_records()
        self.by_id = {record.identifier: record for record in self.records}

    def summary(self) -> Dict[str, Any]:
        """Return a compact ontology summary for dry-runs and reports."""

        type_counts: Counter[str] = Counter()
        for record in self.records:
            type_counts.update(record.types)
        return {
            "ontology_path": str(self.ontology_path),
            "record_count": len(self.records),
            "class_count": type_counts.get("Class", 0),
            "named_individual_count": type_counts.get("NamedIndividual", 0),
            "object_property_count": type_counts.get("ObjectProperty", 0),
            "datatype_property_count": type_counts.get("DatatypeProperty", 0),
            "scenario_template_count": sum(1 for r in self.records if self._is_template(r)),
            "rule_count": sum(1 for r in self.records if self._is_rule(r)),
            "source_count": sum(1 for r in self.records if self._is_source(r)),
        }

    def select_semantic_packet(self, seed: Any, channel: str, variant: str) -> SemanticPacket:
        """Select the PSQ-SCO subgraph needed to control one scenario slot."""

        seed_dict = seed.to_dict() if hasattr(seed, "to_dict") else dict(seed)
        attack_type = ATTACK_CHANNEL_MAP.get(channel, channel) if variant == "fake" else "legitimate"
        templates = self._select_templates(channel, variant, seed_dict.get("micro_stage", ""))
        rules = self._select_rules()
        sources = self._select_sources(channel, variant)
        quality_controls = [
            "CQ1: select an eligible template for role, stage, age group, channel, and variant.",
            "CQ2: preserve required attack or legitimate-communication structure.",
            "CQ3: enforce content quality, channel consistency, persona fit, and playable choices.",
            "CQ4: ground scenario cues in retrieved examples and ontology evidence sources.",
        ]
        must_include = [
            f"channel={channel}",
            f"variant={variant}",
            f"attack_type={attack_type}",
            f"role={seed_dict.get('role')}",
            f"stage_id={seed_dict.get('stage_id')}",
            f"age_group_code={seed_dict.get('age_group_code')}",
            "at least one persona workflow/tool reference",
            "at least one evidence-grounded cue from RAG or PSQ-SCO",
            "three playable choices with feedback",
        ]
        if variant == "fake":
            must_include.extend(["red_flags", "psych_triggers", "safe defensive action"])
            must_exclude = ["unsafe operational attack instructions", "safe_indicators-only framing"]
        else:
            must_include.extend(["safe_indicators", "normal workflow verification"])
            must_exclude = ["red_flags", "psych_triggers", "malicious URL pressure", "bypass-approval wording"]

        return SemanticPacket(
            ontology_path=str(self.ontology_path),
            ontology_version="PSQ-SCO v9.1",
            mode="ontology_prompt_rag",
            seed=seed_dict,
            channel=channel,
            variant=variant,
            attack_type=attack_type,
            selected_templates=[self._compact_record(r) for r in templates],
            required_rules=[self._compact_record(r) for r in rules],
            evidence_sources=[self._compact_record(r) for r in sources],
            quality_controls=quality_controls,
            must_include=must_include,
            must_exclude=must_exclude,
            validation_checks=[
                "schema validation",
                "fake/real separation",
                "channel consistency",
                "stage and vocabulary fit",
                "persona binding",
                "grounding evidence check",
                "ontology packet trace present",
            ],
            provenance={
                "selection_method": "local RDF/XML subgraph filtering",
                "template_selection_terms": [channel, variant, seed_dict.get("micro_stage", "")],
                "rule_source": "PSQ-SCO required validation-rule individuals",
            },
        )

    def _load_records(self) -> List[OntologyRecord]:
        tree = ET.parse(self.ontology_path)
        root = tree.getroot()
        records: List[OntologyRecord] = []
        for desc in root.findall("rdf:Description", NS):
            about = desc.attrib.get(f"{{{RDF}}}about", "")
            identifier = _local_name(about)
            if not identifier:
                continue
            types = [
                _local_name(item.attrib.get(f"{{{RDF}}}resource", ""))
                for item in desc.findall("rdf:type", NS)
            ]
            properties: Dict[str, List[str]] = {}
            for child in desc:
                tag = _local_name(child.tag)
                if tag == "type":
                    continue
                value = child.attrib.get(f"{{{RDF}}}resource", "") or child.text or ""
                value = _local_name(value.strip()) if value.strip().startswith("http") else value.strip()
                if value:
                    properties.setdefault(tag, []).append(value)
            records.append(
                OntologyRecord(
                    identifier=identifier,
                    types=types,
                    label=_node_text(desc, "rdfs:label"),
                    definition=_node_text(desc, "skos:definition") or _node_text(desc, "rdfs:comment"),
                    properties=properties,
                )
            )
        return records

    def _select_templates(self, channel: str, variant: str, micro_stage: str) -> List[OntologyRecord]:
        templates = [record for record in self.records if self._is_template(record)]
        scored: List[tuple[int, OntologyRecord]] = []
        terms = {channel.lower(), variant.lower(), micro_stage.lower()}
        if variant == "real":
            terms.update({"legitimate", "safe"})
        else:
            terms.add(ATTACK_CHANNEL_MAP.get(channel, channel).lower())
        for record in templates:
            haystack = f"{record.identifier} {record.label} {record.definition}".lower()
            score = sum(1 for term in terms if term and term in haystack)
            if score:
                scored.append((score, record))
        selected = [record for _, record in sorted(scored, key=lambda item: (-item[0], item[1].identifier))]
        return selected[:3] or templates[:3]

    def _select_rules(self) -> List[OntologyRecord]:
        # Preserve a fixed anchor order because the ontology-text walk uses the
        # first packet records as deterministic traversal starting points.
        return [self.by_id[key] for key in REQUIRED_RULE_IDS if key in self.by_id]

    def _select_sources(self, channel: str, variant: str) -> List[OntologyRecord]:
        sources = [record for record in self.records if self._is_source(record)]
        terms = [ATTACK_CHANNEL_MAP.get(channel, channel), channel]
        if variant == "real":
            terms.extend(["KnowledgeGraphs", "RAG", "PROVO"])
        scored: List[tuple[int, OntologyRecord]] = []
        for record in sources:
            haystack = f"{record.identifier} {record.label} {record.definition}".lower()
            score = sum(1 for term in terms if term and term.lower() in haystack)
            if score:
                scored.append((score, record))
        selected = [record for _, record in sorted(scored, key=lambda item: (-item[0], item[1].identifier))]
        fallback = [record for record in sources if record.identifier in {"Source_MITRE_T1566", "Source_RAG2020", "Source_PROVO"}]
        return (selected + fallback)[:5]

    @staticmethod
    def _is_template(record: OntologyRecord) -> bool:
        return "ScenarioTemplate" in record.types or record.identifier.startswith("TPL_")

    @staticmethod
    def _is_rule(record: OntologyRecord) -> bool:
        return record.identifier.startswith("Rule_") or any("Rule" in t or "Constraint" in t for t in record.types)

    @staticmethod
    def _is_source(record: OntologyRecord) -> bool:
        return "SourceArtifact" in record.types or "TheorySource" in record.types or record.identifier.startswith("Source_")

    @staticmethod
    def _compact_record(record: OntologyRecord) -> Dict[str, Any]:
        return {
            "id": record.identifier,
            "types": record.types,
            "label": record.label,
            "definition": record.definition,
        }
