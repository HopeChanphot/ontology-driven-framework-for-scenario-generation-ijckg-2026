from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology" / "personashield-psq-sco-v9.1.owl"
GRAPH_JSON = ROOT / "knowledge_graph" / "v9_1" / "personashield-psq-sco-v9.1-graph.json"
HERMIT_REPORT = ROOT / "outputs" / "v9_1" / "hermit-reasoner-report.json"
REPORT_JSON = ROOT / "outputs" / "v9_1" / "kg-completeness-report.json"
ERROR_CSV = ROOT / "outputs" / "v9_1" / "kg-error-analysis.csv"
DOC_MD = ROOT / "docs" / "PSQ_SCO_v9_1_KG_COMPLETENESS_AND_ERROR_ANALYSIS.md"

BASE = "http://personashield.ait.ac.th/ontology/psq-sco#"
PSQ = URIRef(BASE)

REQUIRED_RULES = [
    "Rule_TemplateEligibility",
    "Rule_RequiredAttackStructure",
    "Rule_LegitimateScenarioSeparation",
    "Rule_ChannelConsistency",
    "Rule_PersonaFit",
    "Rule_EvidenceRequirement",
    "Rule_QualityAcceptance",
    "Rule_QualityRejection",
]

CQ_TEMPLATE_REQUIREMENTS = {
    "CQ1": [
        "scenarioId",
        "scenarioID",
        "scenarioTitle",
        "suitableForStage",
        "suitableForRole",
        "suitableForAgeGroup",
        "usesRetrievalMode",
        "hasDifficultyBand",
        "usesChannel",
        "requiresChannel",
        "hasVariant",
        "representsAttackType",
    ],
    "CQ2": [
        "usesChannel",
        "hasVariant",
        "representsAttackType",
        "hasSafeResponse",
        "hasLegalConsequence",
    ],
    "CQ3": [
        "hasQualityRule",
    ],
    "CQ4": [
        "hasEvidencePack",
        "hasProvenanceRecord",
    ],
}

FAKE_TEMPLATE_REQUIREMENTS = [
    "hasThreatAction",
    "hasRedFlag",
    "usesPersuasionCue",
    "hasSafeResponse",
]

LEGITIMATE_FORBIDDEN_PROPERTIES = [
    "hasThreatAction",
    "hasRedFlag",
    "implementsTechnique",
    "mapsToCAPEC",
]

EVIDENCE_JUSTIFICATION_PROPERTIES = [
    "justifiesAttackClassification",
    "justifiesRedFlag",
    "justifiesSafeIndicator",
    "recommendsSafeResponse",
]

SOURCE_REQUIRED_PROPERTIES = [
    DCTERMS.title,
    DCTERMS.publisher,
    URIRef(BASE + "sourceUrl"),
    URIRef(BASE + "retrievalDate"),
    URIRef(BASE + "evidenceCategory"),
    URIRef(BASE + "verificationStatus"),
    URIRef(BASE + "licenseStatus"),
]

SINGLE_VALUE_TEMPLATE_PROPERTIES = [
    "usesChannel",
    "requiresChannel",
    "hasVariant",
    "representsAttackType",
    "hasDifficultyBand",
    "usesRetrievalMode",
]

FORBIDDEN_SCOPE_TERMS = [
    "PedagogicalKnowledgeEntity",
    "PedagogicalConstraint",
    "BloomLevel",
    "KnowledgeType",
    "LearningObjective",
    "HintStrategy",
    "FeedbackType",
    "CognitiveProcess",
    "DataObject",
    "SupportStrategy",
    "EvidenceOfLearning",
    "hasBloomLevel",
    "hasKnowledgeType",
    "usesFeedbackType",
    "usesHintStrategy",
    "targetsLearningObjective",
    "supportedByTheorySource",
    "importsPedagogicalConstraint",
    "manipulatesDataObject",
    "producesPerformanceEvidence",
    "requiresCognitiveProcess",
    "learning_focus",
    "learning_objectives",
    "knowledge_type",
    "LO_",
]

RESTRICTION_VALUE_PROPERTIES = {
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.hasValue,
    OWL.cardinality,
    OWL.minCardinality,
    OWL.maxCardinality,
    OWL.qualifiedCardinality,
    OWL.minQualifiedCardinality,
    OWL.maxQualifiedCardinality,
}

QUALIFIED_CARDINALITY_PROPERTIES = {
    OWL.qualifiedCardinality,
    OWL.minQualifiedCardinality,
    OWL.maxQualifiedCardinality,
}


def psq(name: str) -> URIRef:
    return URIRef(BASE + name)


def local_name(value) -> str:
    text = str(value)
    if text.startswith(BASE):
        return text[len(BASE) :]
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text:
        return text.rsplit("/", 1)[-1]
    return text


def is_local(value) -> bool:
    return isinstance(value, URIRef) and str(value).startswith(BASE)


def load_graph() -> Graph:
    graph = Graph()
    graph.parse(ONTOLOGY, format="xml")
    return graph


def subclass_closure(graph: Graph, class_uri: URIRef) -> set[URIRef]:
    closure = {class_uri}
    changed = True
    while changed:
        changed = False
        for child in graph.subjects(RDFS.subClassOf, None):
            if not is_local(child):
                continue
            parents = set(graph.objects(child, RDFS.subClassOf))
            if parents & closure and child not in closure:
                closure.add(child)
                changed = True
    return closure


def instances_of(graph: Graph, class_name: str) -> list[URIRef]:
    classes = subclass_closure(graph, psq(class_name))
    subjects: set[URIRef] = set()
    for cls in classes:
        for subject in graph.subjects(RDF.type, cls):
            if is_local(subject):
                subjects.add(subject)
    return sorted(subjects, key=local_name)


class Auditor:
    def __init__(self, graph: Graph):
        self.graph = graph
        self.issues: list[dict] = []
        self.required_checks = 0
        self.passed_checks = 0

    def values(self, subject: URIRef, predicate: str | URIRef) -> list:
        pred = predicate if isinstance(predicate, URIRef) else psq(predicate)
        return list(self.graph.objects(subject, pred))

    def has(self, subject: URIRef, predicate: str | URIRef, obj: URIRef | None = None) -> bool:
        pred = predicate if isinstance(predicate, URIRef) else psq(predicate)
        if obj is None:
            return any(True for _ in self.graph.triples((subject, pred, None)))
        return (subject, pred, obj) in self.graph

    def issue(
        self,
        severity: str,
        category: str,
        cq: str,
        subject,
        predicate,
        message: str,
        repair: str,
    ) -> None:
        self.issues.append(
            {
                "severity": severity,
                "category": category,
                "cq": cq,
                "subject": local_name(subject),
                "predicate": local_name(predicate) if predicate else "",
                "issue": message,
                "repair": repair,
            }
        )

    def require(
        self,
        condition: bool,
        category: str,
        cq: str,
        subject,
        predicate,
        message: str,
        repair: str,
    ) -> None:
        self.required_checks += 1
        if condition:
            self.passed_checks += 1
        else:
            self.issue("error", category, cq, subject, predicate, message, repair)

    def warn(
        self,
        condition: bool,
        category: str,
        cq: str,
        subject,
        predicate,
        message: str,
        repair: str,
    ) -> None:
        if not condition:
            self.issue("warning", category, cq, subject, predicate, message, repair)


def audit_templates(auditor: Auditor, templates: list[URIRef]) -> dict:
    graph = auditor.graph
    coverage_by_cq = {cq: {"passed": 0, "total": 0} for cq in CQ_TEMPLATE_REQUIREMENTS}
    variant_counts = Counter()
    channel_counts = Counter()
    difficulty_counts = Counter()

    auditor.require(
        bool(templates),
        "population",
        "ALL",
        "ScenarioTemplate",
        RDF.type,
        "No scenario templates were found.",
        "Create at least one ScenarioTemplate individual before evaluating KG completeness.",
    )

    for template in templates:
        for cq, predicates in CQ_TEMPLATE_REQUIREMENTS.items():
            for predicate in predicates:
                has_value = auditor.has(template, predicate)
                coverage_by_cq[cq]["total"] += 1
                if has_value:
                    coverage_by_cq[cq]["passed"] += 1
                auditor.require(
                    has_value,
                    "template_required_edge",
                    cq,
                    template,
                    predicate,
                    f"{local_name(template)} is missing required edge {predicate}.",
                    f"Add psq:{predicate} for {local_name(template)}.",
                )

        for predicate in SINGLE_VALUE_TEMPLATE_PROPERTIES:
            count = len(auditor.values(template, predicate))
            auditor.require(
                count == 1,
                "template_cardinality",
                "CQ1",
                template,
                predicate,
                f"{local_name(template)} must have exactly one {predicate}; observed {count}.",
                f"Keep one canonical psq:{predicate} value for scenario selection.",
            )

        channels = auditor.values(template, "usesChannel")
        variants = auditor.values(template, "hasVariant")
        difficulties = auditor.values(template, "hasDifficultyBand")
        if channels:
            channel_counts[local_name(channels[0])] += 1
        if variants:
            variant_counts[local_name(variants[0])] += 1
        if difficulties:
            difficulty_counts[local_name(difficulties[0])] += 1

        if psq("FakeVariant") in variants:
            for predicate in FAKE_TEMPLATE_REQUIREMENTS:
                auditor.require(
                    auditor.has(template, predicate),
                    "fake_template_attack_structure",
                    "CQ2",
                    template,
                    predicate,
                    f"Fake template {local_name(template)} lacks {predicate}.",
                    f"Add psq:{predicate} so the fake scenario has explicit attack structure.",
                )
            auditor.require(
                auditor.has(template, "implementsTechnique") or auditor.has(template, "mapsToCAPEC"),
                "fake_template_attack_structure",
                "CQ2",
                template,
                "implementsTechnique|mapsToCAPEC",
                f"Fake template {local_name(template)} lacks an ATT&CK or CAPEC mapping.",
                "Add psq:implementsTechnique or psq:mapsToCAPEC.",
            )

        if psq("RealVariant") in variants:
            auditor.require(
                auditor.has(template, "hasSafeIndicator"),
                "legitimate_template_structure",
                "CQ2",
                template,
                "hasSafeIndicator",
                f"Legitimate template {local_name(template)} lacks a safe indicator.",
                "Add at least one psq:hasSafeIndicator value.",
            )
            for predicate in LEGITIMATE_FORBIDDEN_PROPERTIES:
                auditor.require(
                    not auditor.has(template, predicate),
                    "legitimate_template_noise",
                    "CQ2",
                    template,
                    predicate,
                    f"Legitimate template {local_name(template)} has noisy malicious edge {predicate}.",
                    f"Remove psq:{predicate} from legitimate templates or reclassify the template.",
                )

    return {
        "template_count": len(templates),
        "coverage_by_cq": {
            cq: {
                "passed": item["passed"],
                "total": item["total"],
                "coverage": round(item["passed"] / item["total"], 4) if item["total"] else 0,
            }
            for cq, item in coverage_by_cq.items()
        },
        "variant_counts": dict(sorted(variant_counts.items())),
        "channel_counts": dict(sorted(channel_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
    }


def audit_quality_rules(auditor: Auditor, templates: list[URIRef], generated: list[URIRef]) -> dict:
    for rule_name in REQUIRED_RULES:
        rule = psq(rule_name)
        auditor.require(
            (rule, RDF.type, OWL.NamedIndividual) in auditor.graph,
            "quality_rule_presence",
            "CQ3",
            rule,
            RDF.type,
            f"Required quality rule {rule_name} is missing.",
            f"Create psq:{rule_name} as a named individual.",
        )
        for predicate in ["qualityRuleCategory", "acceptanceThreshold", "requiredForAcceptance", "ruleText", "ruleLanguage"]:
            auditor.require(
                auditor.has(rule, predicate),
                "quality_rule_metadata",
                "CQ3",
                rule,
                predicate,
                f"Quality rule {rule_name} lacks {predicate}.",
                f"Add psq:{predicate} to psq:{rule_name}.",
            )

    for template in templates:
        linked_rules = set(auditor.values(template, "hasQualityRule"))
        for rule_name in REQUIRED_RULES:
            auditor.require(
                psq(rule_name) in linked_rules,
                "template_quality_rule_coverage",
                "CQ3",
                template,
                "hasQualityRule",
                f"{local_name(template)} is not linked to {rule_name}.",
                f"Add psq:hasQualityRule psq:{rule_name}.",
            )

    auditor.require(
        bool(generated),
        "generated_scenario_population",
        "CQ3",
        "GeneratedScenario",
        RDF.type,
        "No GeneratedScenario individuals were found for content-quality checks.",
        "Add at least one generated candidate example for validation and error analysis.",
    )
    for candidate in generated:
        for predicate in ["basedOnTemplate", "usesChannel", "hasVariant", "hasValidationDecision", "hasScenarioQualityScore", "supportedByEvidence"]:
            auditor.require(
                auditor.has(candidate, predicate),
                "generated_scenario_required_edge",
                "CQ3",
                candidate,
                predicate,
                f"{local_name(candidate)} lacks {predicate}.",
                f"Add psq:{predicate} to the generated scenario candidate.",
            )
        for score in auditor.values(candidate, "hasScenarioQualityScore"):
            for predicate in ["qualityScore", "confidenceScore", "validationStatus"]:
                auditor.require(
                    auditor.has(score, predicate),
                    "quality_score_metadata",
                    "CQ3",
                    score,
                    predicate,
                    f"{local_name(score)} lacks {predicate}.",
                    f"Add psq:{predicate} to the quality score resource.",
                )
        decisions = auditor.values(candidate, "hasValidationDecision")
        violations = auditor.values(candidate, "violatesConstraint")
        if psq("Decision_Accept") in decisions:
            auditor.require(
                not violations,
                "decision_violation_consistency",
                "CQ3",
                candidate,
                "violatesConstraint",
                f"Accepted scenario {local_name(candidate)} still has constraint violations.",
                "Change the decision to review/reject or remove the resolved violation edge.",
            )

    return {"required_rule_count": len(REQUIRED_RULES), "generated_scenario_count": len(generated)}


def audit_evidence(auditor: Auditor, templates: list[URIRef]) -> dict:
    evidence_packs = set()
    sources = set()
    datasets = set()
    provenance_records = set()

    for template in templates:
        packs = auditor.values(template, "hasEvidencePack")
        provenances = auditor.values(template, "hasProvenanceRecord")
        auditor.require(
            len(packs) >= 1,
            "template_evidence_pack",
            "CQ4",
            template,
            "hasEvidencePack",
            f"{local_name(template)} has no evidence pack.",
            "Link the template to a psq:EvidencePack individual.",
        )
        auditor.require(
            len(provenances) >= 1,
            "template_provenance",
            "CQ4",
            template,
            "hasProvenanceRecord",
            f"{local_name(template)} has no provenance record.",
            "Link the template to a psq:ProvenanceRecord individual.",
        )
        provenance_records.update(provenances)

        for provenance in provenances:
            for predicate in ["sourceFile", "sourceRecordId"]:
                auditor.require(
                    auditor.has(provenance, predicate),
                    "provenance_metadata",
                    "CQ4",
                    provenance,
                    predicate,
                    f"{local_name(provenance)} lacks {predicate}.",
                    f"Add psq:{predicate} to the provenance record.",
                )

        for pack in packs:
            evidence_packs.add(pack)
            pack_sources = auditor.values(pack, "supportedBySource")
            pack_datasets = auditor.values(pack, "derivedFromDataset")
            sources.update(pack_sources)
            datasets.update(pack_datasets)
            auditor.require(
                len(pack_sources) >= 1,
                "evidence_pack_source",
                "CQ4",
                pack,
                "supportedBySource",
                f"{local_name(pack)} has no source.",
                "Add at least one psq:supportedBySource edge.",
            )
            auditor.require(
                len(pack_datasets) >= 1,
                "evidence_pack_dataset",
                "CQ4",
                pack,
                "derivedFromDataset",
                f"{local_name(pack)} has no dataset.",
                "Add a psq:derivedFromDataset edge.",
            )
            auditor.require(
                any(auditor.has(pack, predicate) for predicate in EVIDENCE_JUSTIFICATION_PROPERTIES),
                "evidence_pack_justification",
                "CQ4",
                pack,
                "|".join(EVIDENCE_JUSTIFICATION_PROPERTIES),
                f"{local_name(pack)} has no justification edge.",
                "Add at least one attack, red-flag, safe-indicator, or safe-response justification edge.",
            )

    for source in sorted(sources, key=local_name):
        for predicate in SOURCE_REQUIRED_PROPERTIES:
            auditor.require(
                auditor.has(source, predicate),
                "source_metadata",
                "CQ4",
                source,
                predicate,
                f"Source {local_name(source)} lacks {local_name(predicate)}.",
                f"Add {local_name(predicate)} metadata to the source artifact.",
            )

    for dataset in sorted(datasets, key=local_name):
        auditor.require(
            auditor.has(dataset, RDFS.label),
            "dataset_metadata",
            "CQ4",
            dataset,
            RDFS.label,
            f"Dataset {local_name(dataset)} lacks rdfs:label.",
            "Add a human-readable dataset label.",
        )

    return {
        "evidence_pack_count": len(evidence_packs),
        "source_count": len(sources),
        "dataset_count": len(datasets),
        "provenance_record_count": len(provenance_records),
    }


def audit_noise(auditor: Auditor, templates: list[URIRef]) -> dict:
    graph = auditor.graph
    local_subjects = {s for s, _, _ in graph if is_local(s)}
    local_referenced_objects = {o for _, _, o in graph if is_local(o)}
    dangling = sorted(local_referenced_objects - local_subjects, key=local_name)
    for target in dangling:
        auditor.require(
            False,
            "dangling_local_reference",
            "ALL",
            target,
            "",
            f"Local object {local_name(target)} is referenced but never declared as a subject.",
            "Declare the node or remove the edge.",
        )

    local_predicates = {p for _, p, _ in graph if is_local(p)}
    for predicate in sorted(local_predicates, key=local_name):
        auditor.require(
            any(True for _ in graph.triples((predicate, RDF.type, None))),
            "undeclared_property",
            "ALL",
            predicate,
            RDF.type,
            f"Predicate {local_name(predicate)} is used but has no RDF type declaration.",
            "Declare it as an object, datatype, or annotation property.",
        )

    typed_local_subjects = {s for s in local_subjects if any(True for _ in graph.triples((s, RDF.type, None)))}
    for subject in sorted(typed_local_subjects, key=local_name):
        auditor.warn(
            auditor.has(subject, RDFS.label),
            "missing_label",
            "ALL",
            subject,
            RDFS.label,
            f"{local_name(subject)} is typed but has no rdfs:label.",
            "Add rdfs:label for readability in graph tools.",
        )

    scenario_ids: dict[str, list[str]] = defaultdict(list)
    for template in templates:
        for predicate in ["scenarioId", "scenarioID"]:
            for value in auditor.values(template, predicate):
                scenario_ids[str(value)].append(local_name(template))
    duplicate_ids = {sid: names for sid, names in scenario_ids.items() if len(set(names)) > 1}
    for sid, names in duplicate_ids.items():
        auditor.require(
            False,
            "duplicate_scenario_id",
            "CQ1",
            sid,
            "scenarioId|scenarioID",
            f"Scenario ID {sid} is used by multiple templates: {', '.join(sorted(set(names)))}.",
            "Make scenario identifiers unique before engine export.",
        )

    graph_export = {"nodes": [], "edges": []}
    export_status = "not_found"
    if GRAPH_JSON.exists():
        graph_export = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
        node_ids = {node["id"] for node in graph_export.get("nodes", [])}
        export_status = "checked"
        for edge in graph_export.get("edges", []):
            auditor.require(
                edge["source"] in node_ids,
                "graph_export_dangling_source",
                "ALL",
                edge["source"],
                edge.get("predicate", ""),
                f"Graph export edge source {edge['source']} is missing from node list.",
                "Regenerate the graph export from the ontology.",
            )
            target = edge.get("target", "")
            if edge.get("target_type") == "iri" and not str(target).startswith("http"):
                auditor.require(
                    target in node_ids,
                    "graph_export_dangling_target",
                    "ALL",
                    target,
                    edge.get("predicate", ""),
                    f"Graph export local target {target} is missing from node list.",
                    "Regenerate the graph export or declare the target node.",
                )
    else:
        auditor.issue(
            "warning",
            "graph_export_missing",
            "ALL",
            GRAPH_JSON,
            "",
            "Graph JSON export was not found.",
            "Run scripts/build_psq_sco_v9_1_no_pedagogy.py to regenerate graph exports.",
        )

    return {
        "dangling_local_reference_count": len(dangling),
        "graph_export_status": export_status,
        "graph_export_node_count": len(graph_export.get("nodes", [])),
        "graph_export_edge_count": len(graph_export.get("edges", [])),
    }


def audit_removed_scope(auditor: Auditor) -> dict:
    graph = auditor.graph
    literal_hits = []
    graph_export_hits = []

    for term in FORBIDDEN_SCOPE_TERMS:
        resource = psq(term)
        auditor.require(
            not any(True for _ in graph.triples((resource, None, None))),
            "removed_scope_subject_absent",
            "ALL",
            resource,
            "",
            f"Removed-scope term {term} remains as a graph subject.",
            f"Remove declaration and annotations for psq:{term}.",
        )
        auditor.require(
            not any(True for _ in graph.triples((None, resource, None))),
            "removed_scope_predicate_absent",
            "ALL",
            resource,
            "",
            f"Removed-scope property {term} remains as a graph predicate.",
            f"Remove all uses of psq:{term}.",
        )
        auditor.require(
            not any(True for _ in graph.triples((None, None, resource))),
            "removed_scope_object_absent",
            "ALL",
            resource,
            "",
            f"Removed-scope term {term} remains as a graph object.",
            f"Remove references to psq:{term}.",
        )

    lowered_terms = [term.lower() for term in FORBIDDEN_SCOPE_TERMS]
    for s, p, o in graph:
        if hasattr(o, "language") or hasattr(o, "datatype"):
            text = str(o).lower()
            for term, lowered in zip(FORBIDDEN_SCOPE_TERMS, lowered_terms):
                if lowered in text:
                    literal_hits.append({"subject": local_name(s), "predicate": local_name(p), "term": term, "literal": str(o)[:180]})
                    auditor.issue(
                        "error",
                        "removed_scope_literal_absent",
                        "ALL",
                        s,
                        p,
                        f"Removed-scope term {term} remains in a graph literal.",
                        "Rewrite or remove the annotation literal.",
                    )

    if GRAPH_JSON.exists():
        graph_export = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
        for node in graph_export.get("nodes", []):
            node_id = str(node.get("id", ""))
            for term in FORBIDDEN_SCOPE_TERMS:
                if term.lower() in node_id.lower():
                    graph_export_hits.append({"type": "node", "term": term, "id": node_id})
        for edge in graph_export.get("edges", []):
            text = json.dumps(edge, ensure_ascii=False)
            for term in FORBIDDEN_SCOPE_TERMS:
                if term.lower() in text.lower():
                    graph_export_hits.append({"type": "edge", "term": term, "edge": edge})
        auditor.require(
            not graph_export_hits,
            "removed_scope_graph_export_absent",
            "ALL",
            GRAPH_JSON,
            "",
            "Removed-scope terms remain in the exported knowledge graph JSON.",
            "Regenerate the graph export after pruning the removed branch.",
        )

    return {
        "forbidden_term_count": len(FORBIDDEN_SCOPE_TERMS),
        "literal_hit_count": len(literal_hits),
        "graph_export_hit_count": len(graph_export_hits),
        "status": "PASS" if not literal_hits and not graph_export_hits else "FAIL",
        "literal_hits": literal_hits[:20],
        "graph_export_hits": graph_export_hits[:20],
    }


def audit_owl_restrictions(auditor: Auditor) -> dict:
    malformed = []
    for restriction in auditor.graph.subjects(RDF.type, OWL.Restriction):
        if not isinstance(restriction, BNode):
            continue
        has_on_property = any(True for _ in auditor.graph.objects(restriction, OWL.onProperty))
        has_value_constraint = any(
            any(True for _ in auditor.graph.objects(restriction, predicate))
            for predicate in RESTRICTION_VALUE_PROPERTIES
        )
        has_qualified_cardinality = any(
            any(True for _ in auditor.graph.objects(restriction, predicate))
            for predicate in QUALIFIED_CARDINALITY_PROPERTIES
        )
        has_qualified_target = (
            any(True for _ in auditor.graph.objects(restriction, OWL.onClass))
            or any(True for _ in auditor.graph.objects(restriction, OWL.onDataRange))
        )
        if not has_on_property or not has_value_constraint or (has_qualified_cardinality and not has_qualified_target):
            parents = [local_name(parent) for parent in auditor.graph.subjects(RDFS.subClassOf, restriction)]
            malformed.append(
                {
                    "restriction": str(restriction),
                    "attached_to": parents,
                    "has_on_property": has_on_property,
                    "has_value_constraint": has_value_constraint,
                    "has_qualified_target": has_qualified_target,
                }
            )
    auditor.require(
        not malformed,
        "malformed_owl_restriction",
        "ALL",
        "owl:Restriction",
        "rdfs:subClassOf",
        "Malformed anonymous OWL restriction remains in the class hierarchy.",
        "Regenerate the ontology with scripts/build_psq_sco_v9_1_no_pedagogy.py.",
    )
    return {
        "status": "PASS" if not malformed else "FAIL",
        "malformed_restriction_count": len(malformed),
        "malformed_restrictions": malformed[:20],
    }


def read_reasoner_status() -> dict:
    if not HERMIT_REPORT.exists():
        return {
            "status": "MISSING",
            "consistent": None,
            "unsatisfiable_count": None,
            "message": "HermiT report is missing. Run the reasoner before final release.",
        }
    data = json.loads(HERMIT_REPORT.read_text(encoding="utf-8-sig"))
    return {
        "status": data.get("status"),
        "consistent": data.get("consistent"),
        "unsatisfiable_count": data.get("unsatisfiable_count"),
        "ontology": data.get("ontology"),
        "reasoner": data.get("reasoner"),
    }


def write_error_csv(issues: list[dict]) -> None:
    ERROR_CSV.parent.mkdir(parents=True, exist_ok=True)
    fields = ["severity", "category", "cq", "subject", "predicate", "issue", "repair"]
    with ERROR_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for issue in issues:
            writer.writerow({field: issue.get(field, "") for field in fields})


def write_markdown(report: dict) -> None:
    severity_counts = report["error_analysis"]["severity_counts"]
    category_counts = report["error_analysis"]["category_counts"]
    coverage_lines = []
    for cq, item in report["template_completeness"]["coverage_by_cq"].items():
        percent = item["coverage"] * 100
        coverage_lines.append(f"| {cq} | {item['passed']} / {item['total']} | {percent:.1f}% |")

    category_lines = []
    for category, count in category_counts.items():
        category_lines.append(f"| {category} | {count} |")

    status_text = report["status"]
    complete_text = "YES, bounded complete for CQ1-CQ4." if status_text == "PASS" else "NO, gaps remain."
    removed_scope = report["removed_scope_analysis"]
    owl_restrictions = report["owl_restriction_analysis"]
    md = f"""# PSQ-SCO v9.1 Knowledge Graph Completeness and Error Analysis

Generated: {report['generated_at']}

## Direct Answer

Did we prove the knowledge graph is complete?

**{complete_text}**

This is not a claim of universal completeness for all cybersecurity knowledge.
It is a bounded completeness claim: the v9.1 knowledge graph is complete for the
six PSQ-SCO scenario templates and the four competency-question contracts used
by PersonaShield Quest scenario control.

## Scope of the Completeness Claim

- Ontology: `{report['ontology']}`
- Knowledge graph export: `{report['graph_export']['graph_json']}`
- Scenario templates checked: {report['template_completeness']['template_count']}
- Required quality rules checked: {report['quality_control']['required_rule_count']}
- Evidence packs checked: {report['evidence_grounding']['evidence_pack_count']}
- Source artifacts checked: {report['evidence_grounding']['source_count']}
- Removed-scope terms checked: {removed_scope['forbidden_term_count']}
- Malformed anonymous OWL restrictions: {owl_restrictions['malformed_restriction_count']}

The KG is treated as complete only if every required edge pattern for CQ1, CQ2,
CQ3, and CQ4 is present, graph-export edges do not point to missing local nodes,
the removed learning-design branch is absent, and the ontology reasoner report
is consistent.

## CQ Completeness Coverage

| CQ | Required edges passed | Coverage |
|---|---:|---:|
{chr(10).join(coverage_lines)}

## Error Analysis Summary

| Severity | Count |
|---|---:|
| error | {severity_counts.get('error', 0)} |
| warning | {severity_counts.get('warning', 0)} |

| Category | Count |
|---|---:|
{chr(10).join(category_lines) if category_lines else '| none | 0 |'}

Full machine-readable error table:
`outputs/v9_1/kg-error-analysis.csv`

## Removed-Scope Check

- Status: {removed_scope['status']}
- Literal hits: {removed_scope['literal_hit_count']}
- Graph export hits: {removed_scope['graph_export_hit_count']}

## OWL Restriction Structural Check

- Status: {owl_restrictions['status']}
- Malformed anonymous restrictions: {owl_restrictions['malformed_restriction_count']}

## Ontology Consistency

- HermiT status: {report['reasoner']['status']}
- Consistent: {report['reasoner']['consistent']}
- Unsatisfiable classes: {report['reasoner']['unsatisfiable_count']}

## Noise and Correctness Checks

- Dangling local references: {report['noise_analysis']['dangling_local_reference_count']}
- Graph export status: {report['noise_analysis']['graph_export_status']}
- Graph export nodes: {report['noise_analysis']['graph_export_node_count']}
- Graph export edges: {report['noise_analysis']['graph_export_edge_count']}
- Variant distribution: {json.dumps(report['template_completeness']['variant_counts'], ensure_ascii=False)}
- Channel distribution: {json.dumps(report['template_completeness']['channel_counts'], ensure_ascii=False)}
- Difficulty distribution: {json.dumps(report['template_completeness']['difficulty_counts'], ensure_ascii=False)}

## Reviewer-Safe Wording

Use this wording in the paper or presentation:

> We do not claim that the knowledge graph is universally complete. We validate
> bounded completeness against the PSQ-SCO competency-question contract. The KG
> is complete for the v9.1 test scope when each scenario template has the required
> CQ1 selection edges, CQ2 attack/legitimate structure edges, CQ3 quality-control
> rules, and CQ4 evidence/provenance links; when the removed learning-design
> branch is absent; and when graph-noise and reasoner checks pass.

## Output Files

- JSON completeness report: `outputs/v9_1/kg-completeness-report.json`
- CSV error analysis: `outputs/v9_1/kg-error-analysis.csv`
- HermiT report: `outputs/v9_1/hermit-reasoner-report.json`
- Release validation report: `outputs/v9_1/release-validation-report.json`
"""
    DOC_MD.write_text(md, encoding="utf-8")


def main() -> int:
    graph = load_graph()
    auditor = Auditor(graph)
    templates = instances_of(graph, "ScenarioTemplate")
    generated = instances_of(graph, "GeneratedScenario")

    template_report = audit_templates(auditor, templates)
    quality_report = audit_quality_rules(auditor, templates, generated)
    evidence_report = audit_evidence(auditor, templates)
    noise_report = audit_noise(auditor, templates)
    removed_scope_report = audit_removed_scope(auditor)
    owl_restriction_report = audit_owl_restrictions(auditor)
    reasoner = read_reasoner_status()

    if reasoner["status"] != "PASS" or reasoner["consistent"] is not True:
        auditor.issue(
            "error",
            "ontology_consistency",
            "ALL",
            ONTOLOGY,
            "HermiT",
            "Ontology consistency has not passed.",
            "Run HermiT and resolve any inconsistent or unsatisfiable classes.",
        )

    severity_counts = Counter(issue["severity"] for issue in auditor.issues)
    category_counts = Counter(issue["category"] for issue in auditor.issues)
    status = "PASS" if severity_counts.get("error", 0) == 0 else "FAIL"
    completeness_ratio = (
        round(auditor.passed_checks / auditor.required_checks, 4)
        if auditor.required_checks
        else 0
    )

    report = {
        "version": "9.1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "ontology": str(ONTOLOGY),
        "bounded_completeness_claim": "complete_for_CQ1_CQ2_CQ3_CQ4_only",
        "status": status,
        "required_checks": auditor.required_checks,
        "passed_checks": auditor.passed_checks,
        "completeness_ratio": completeness_ratio,
        "template_completeness": template_report,
        "quality_control": quality_report,
        "evidence_grounding": evidence_report,
        "noise_analysis": noise_report,
        "removed_scope_analysis": removed_scope_report,
        "owl_restriction_analysis": owl_restriction_report,
        "graph_export": {
            "graph_json": str(GRAPH_JSON),
            "nodes": noise_report["graph_export_node_count"],
            "edges": noise_report["graph_export_edge_count"],
        },
        "reasoner": reasoner,
        "error_analysis": {
            "severity_counts": dict(sorted(severity_counts.items())),
            "category_counts": dict(sorted(category_counts.items())),
            "issues": auditor.issues,
        },
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_error_csv(auditor.issues)
    write_markdown(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
