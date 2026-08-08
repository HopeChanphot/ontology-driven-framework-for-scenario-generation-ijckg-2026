from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef, RDF, RDFS, OWL

import run_sparql_cq_v9_1 as sparql_runner


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY = ROOT / "ontology" / "personashield-psq-sco-v9.1.owl"
OUTPUT = ROOT / "outputs" / "v9_1" / "release-validation-report.json"
HERMIT_REPORT = ROOT / "outputs" / "v9_1" / "hermit-reasoner-report.json"
KG_CHECK_SCRIPT = ROOT / "scripts" / "check_kg_completeness_v9_1.py"
KG_REPORT = ROOT / "outputs" / "v9_1" / "kg-completeness-report.json"
RUNTIME_ROOT = ROOT / "data" / "ontology_runtime_v9_1"
PSQ = Namespace("http://personashield.ait.ac.th/ontology/psq-sco#")
VERSION = "9.1.0"

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

FORBIDDEN_RUNTIME_FIELDS = [
    "knowledge_type",
    "learning_focus",
    "pedagogical_alignment",
    "learning_objectives",
    "learning_objective",
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


def count_type(graph: Graph, type_uri) -> int:
    return len({s for s in graph.subjects(RDF.type, type_uri) if str(s).startswith(str(PSQ))})


def runtime_counts() -> dict:
    records = 0
    files = 0
    if RUNTIME_ROOT.exists():
        for path in RUNTIME_ROOT.rglob("*.jsonl"):
            files += 1
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        records += 1
    return {"records": records, "files": files}


def scan_removed_scope(graph: Graph) -> dict:
    graph_hits = []
    literal_hits = []
    for term in FORBIDDEN_SCOPE_TERMS:
        resource = URIRef(str(PSQ) + term)
        if any(True for _ in graph.triples((resource, None, None))):
            graph_hits.append({"term": term, "position": "subject"})
        if any(True for _ in graph.triples((None, resource, None))):
            graph_hits.append({"term": term, "position": "predicate"})
        if any(True for _ in graph.triples((None, None, resource))):
            graph_hits.append({"term": term, "position": "object"})
    lowered = [(term, term.lower()) for term in FORBIDDEN_SCOPE_TERMS]
    for s, p, o in graph:
        if isinstance(o, Literal):
            text = str(o).lower()
            for term, lower in lowered:
                if lower in text:
                    literal_hits.append({"term": term, "subject": str(s), "predicate": str(p), "literal": str(o)[:180]})
    return {
        "status": "PASS" if not graph_hits and not literal_hits else "FAIL",
        "graph_hit_count": len(graph_hits),
        "literal_hit_count": len(literal_hits),
        "graph_hits": graph_hits[:25],
        "literal_hits": literal_hits[:25],
    }


def scan_runtime_removed_scope() -> dict:
    field_hits = []
    text_hits = []
    lowered_terms = [(term, term.lower()) for term in FORBIDDEN_SCOPE_TERMS]
    for path in RUNTIME_ROOT.rglob("*.jsonl"):
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                for field in FORBIDDEN_RUNTIME_FIELDS:
                    if field in record:
                        field_hits.append({"file": str(path), "line": line_no, "field": field})
                ontology_ids = record.get("ontology_ids")
                if isinstance(ontology_ids, dict):
                    for field in FORBIDDEN_RUNTIME_FIELDS:
                        if field in ontology_ids:
                            field_hits.append({"file": str(path), "line": line_no, "field": f"ontology_ids.{field}"})
                text = json.dumps(record, ensure_ascii=False).lower()
                for term, lower in lowered_terms:
                    if lower in text:
                        text_hits.append({"file": str(path), "line": line_no, "term": term})
    return {
        "status": "PASS" if not field_hits and not text_hits else "FAIL",
        "field_hit_count": len(field_hits),
        "text_hit_count": len(text_hits),
        "field_hits": field_hits[:25],
        "text_hits": text_hits[:25],
    }


def scan_malformed_restrictions(graph: Graph) -> dict:
    malformed = []
    for restriction in graph.subjects(RDF.type, OWL.Restriction):
        if not isinstance(restriction, BNode):
            continue
        has_on_property = any(True for _ in graph.objects(restriction, OWL.onProperty))
        has_value_constraint = any(
            any(True for _ in graph.objects(restriction, predicate))
            for predicate in RESTRICTION_VALUE_PROPERTIES
        )
        has_qualified_cardinality = any(
            any(True for _ in graph.objects(restriction, predicate))
            for predicate in QUALIFIED_CARDINALITY_PROPERTIES
        )
        has_qualified_target = (
            any(True for _ in graph.objects(restriction, OWL.onClass))
            or any(True for _ in graph.objects(restriction, OWL.onDataRange))
        )
        if not has_on_property or not has_value_constraint or (has_qualified_cardinality and not has_qualified_target):
            malformed.append(
                {
                    "restriction": str(restriction),
                    "attached_to": [str(parent) for parent in graph.subjects(RDFS.subClassOf, restriction)],
                    "has_on_property": has_on_property,
                    "has_value_constraint": has_value_constraint,
                    "has_qualified_target": has_qualified_target,
                }
            )
    return {
        "status": "PASS" if not malformed else "FAIL",
        "malformed_restriction_count": len(malformed),
        "malformed_restrictions": malformed[:25],
    }


def bool_triple(graph: Graph, subject: str, predicate: str, obj: str | None = None) -> bool:
    s = PSQ[subject]
    p = PSQ[predicate]
    if obj is None:
        return any(True for _ in graph.triples((s, p, None)))
    return (s, p, PSQ[obj]) in graph


def run_kg_completeness(errors: list[str], warnings: list[str]) -> dict | None:
    if not KG_CHECK_SCRIPT.exists():
        errors.append("KG completeness checker is missing")
        return None
    result = subprocess.run(
        [sys.executable, str(KG_CHECK_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        errors.append("KG completeness check failed")
        if result.stderr:
            warnings.append(result.stderr.strip())
    if not KG_REPORT.exists():
        errors.append("KG completeness report was not produced")
        return None
    report = json.loads(KG_REPORT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        errors.append("KG completeness report did not pass")
    return report


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    graph = Graph()
    graph.parse(ONTOLOGY, format="xml")

    counts = {
        "classes": count_type(graph, OWL.Class),
        "object_properties": count_type(graph, OWL.ObjectProperty),
        "data_properties": count_type(graph, OWL.DatatypeProperty),
        "annotation_properties": count_type(graph, OWL.AnnotationProperty),
        "individuals": count_type(graph, OWL.NamedIndividual),
    }

    required_classes = [
        "ContentQualityKnowledgeEntity",
        "GeneratedScenario",
        "SemanticPacket",
        "PerformanceState",
        "MoodContext",
        "ContentQualityRule",
        "ValidationDecision",
        "ScenarioQualityScore",
        "ConstraintViolation",
        "ErrorType",
        "LegalConsequence",
    ]
    for cls in required_classes:
        if (PSQ[cls], RDF.type, OWL.Class) not in graph:
            errors.append(f"missing v9.1 class {cls}")

    required_properties = [
        "hasQualityRule",
        "hasValidationDecision",
        "hasScenarioQualityScore",
        "violatesConstraint",
        "targetsLearnerProfile",
        "hasPerformanceState",
        "hasMoodContext",
        "hasLegalConsequence",
        "ruleText",
        "qualityScore",
        "confidenceScore",
        "validationStatus",
    ]
    for prop in required_properties:
        if not any(True for _ in graph.triples((PSQ[prop], RDF.type, None))):
            errors.append(f"missing v9.1 property {prop}")

    required_rules = [
        "Rule_TemplateEligibility",
        "Rule_RequiredAttackStructure",
        "Rule_LegitimateScenarioSeparation",
        "Rule_ChannelConsistency",
        "Rule_PersonaFit",
        "Rule_EvidenceRequirement",
        "Rule_QualityAcceptance",
        "Rule_QualityRejection",
    ]
    for rule in required_rules:
        if (PSQ[rule], RDF.type, OWL.NamedIndividual) not in graph:
            errors.append(f"missing quality rule {rule}")
        if not bool_triple(graph, rule, "ruleText"):
            errors.append(f"missing ruleText for {rule}")

    if not bool_triple(graph, "Learner_HR_Beginner", "hasPerformanceState", "Performance_Stable"):
        errors.append("Learner_HR_Beginner missing Performance_Stable link")
    if not bool_triple(graph, "Learner_HR_Beginner", "hasMoodContext", "Mood_NotModeledNeutral"):
        errors.append("Learner_HR_Beginner missing mood placeholder link")
    if not bool_triple(graph, "TPL_SMS_BankLink_Introductory", "hasQualityRule", "Rule_TemplateEligibility"):
        errors.append("SMS bank-link template missing quality-rule links")
    if not bool_triple(graph, "TPL_SMS_BankLink_Introductory", "hasLegalConsequence", "LegalConsequence_ReportToITOrSecurity"):
        errors.append("SMS bank-link template missing legal consequence")
    if not bool_triple(graph, "Generated_SMS_BankLink_Candidate_v9", "hasValidationDecision", "Decision_Review"):
        errors.append("v9 generated scenario candidate missing review decision")
    if not bool_triple(graph, "Generated_SMS_BankLink_Candidate_v9", "hasScenarioQualityScore", "Score_SMS_BankLink_Candidate"):
        errors.append("v9 generated scenario candidate missing quality score")

    cq_results = []
    for cq in ["1", "2", "3", "4"]:
        result = sparql_runner.run_cq(
            graph,
            cq,
            "Learner_HR_Beginner",
            "TPL_SMS_BankLink_Introductory",
            "TPL_Voice_ITSupport_Advanced",
        )
        row_count = result["result"].get("row_count", 0)
        if row_count <= 0:
            errors.append(f"CQ{cq} returned no rows")
        cq_results.append({"cq": f"CQ{cq}", "row_count": row_count})

    ask_report = sparql_runner.run_validation_cases(graph)
    if ask_report["status"] != "PASS":
        errors.append("SPARQL ASK validation cases failed")

    runtime = runtime_counts()
    if runtime["records"] != 12425:
        errors.append(f"runtime record count expected 12425, observed {runtime['records']}")

    hermit = None
    if HERMIT_REPORT.exists():
        hermit = json.loads(HERMIT_REPORT.read_text(encoding="utf-8-sig"))
        if not hermit.get("consistent") or hermit.get("unsatisfiable_count") not in (0, None):
            errors.append("HermiT report did not pass")
    else:
        warnings.append("HermiT report not found; run run_hermit_reasoner_v8_2.ps1 with the v9.1 ontology for reasoner validation")

    removed_scope = scan_removed_scope(graph)
    if removed_scope["status"] != "PASS":
        errors.append("removed-scope ontology scan failed")
    runtime_removed_scope = scan_runtime_removed_scope()
    if runtime_removed_scope["status"] != "PASS":
        errors.append("removed-scope runtime scan failed")
    owl_restrictions = scan_malformed_restrictions(graph)
    if owl_restrictions["status"] != "PASS":
        errors.append("malformed OWL restriction scan failed")

    kg_report = run_kg_completeness(errors, warnings)
    kg_summary = None
    if kg_report:
        kg_summary = {
            "status": kg_report.get("status"),
            "bounded_completeness_claim": kg_report.get("bounded_completeness_claim"),
            "required_checks": kg_report.get("required_checks"),
            "passed_checks": kg_report.get("passed_checks"),
            "completeness_ratio": kg_report.get("completeness_ratio"),
            "template_count": kg_report.get("template_completeness", {}).get("template_count"),
            "coverage_by_cq": kg_report.get("template_completeness", {}).get("coverage_by_cq"),
            "noise_analysis": kg_report.get("noise_analysis"),
            "removed_scope_analysis": kg_report.get("removed_scope_analysis"),
            "owl_restriction_analysis": kg_report.get("owl_restriction_analysis"),
            "error_analysis": {
                "severity_counts": kg_report.get("error_analysis", {}).get("severity_counts"),
                "category_counts": kg_report.get("error_analysis", {}).get("category_counts"),
            },
            "report_file": str(KG_REPORT),
        }

    report = {
        "version": VERSION,
        "ontology": str(ONTOLOGY),
        "counts": counts,
        "triple_count": len(graph),
        "runtime": runtime,
        "removed_scope": removed_scope,
        "runtime_removed_scope": runtime_removed_scope,
        "owl_restrictions": owl_restrictions,
        "cq_select_results": cq_results,
        "ask_validation": {
            "status": ask_report["status"],
            "passed": ask_report["passed_count"],
            "total": ask_report["case_count"],
        },
        "reasoner": hermit,
        "kg_completeness": kg_summary,
        "errors": errors,
        "warnings": warnings,
        "status": "PASS" if not errors else "FAIL",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
