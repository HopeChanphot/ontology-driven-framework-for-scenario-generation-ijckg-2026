"""Ontology-layer validation for PSQ-SCO."""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import OntologyValidationResult, ScenarioRecord


def validate_ontology(
    *,
    ontology_path: Path,
    query_dir: Path,
    records: Iterable[ScenarioRecord],
    hermit_jar: Optional[Path] = None,
    hermit_report: Optional[Path] = None,
    java_executable: str = "java",
) -> OntologyValidationResult:
    """Run the compact ontology validation layer for the paper evaluator."""

    notes: List[str] = []
    class_count, named_count, object_prop_count, datatype_prop_count = _count_owl_entities(ontology_path, notes)
    consistency, unsat_count, reasoner_status, reasoner_notes = _run_hermit(
        ontology_path=ontology_path,
        hermit_jar=hermit_jar,
        hermit_report=hermit_report,
        java_executable=java_executable,
    )
    notes.extend(reasoner_notes)
    cq_passed, cq_total, cq_notes = _run_cq_queries(ontology_path, query_dir)
    notes.extend(cq_notes)
    mapping_passed, mapping_total, preserved = _mapping_tests(records)

    return OntologyValidationResult(
        ontology_path=str(ontology_path),
        query_dir=str(query_dir),
        reasoner_consistency=consistency,
        reasoner_status=reasoner_status,
        unsatisfiable_class_count=unsat_count,
        cq_passed=cq_passed,
        cq_total=cq_total,
        mapping_passed=mapping_passed,
        mapping_total=mapping_total,
        runtime_records_preserved=preserved,
        class_count=class_count,
        named_individual_count=named_count,
        object_property_count=object_prop_count,
        datatype_property_count=datatype_prop_count,
        notes=notes,
    )


def _count_owl_entities(ontology_path: Path, notes: List[str]) -> Tuple[int, int, int, int]:
    if not ontology_path.exists():
        notes.append(f"Ontology file not found: {ontology_path}")
        return 0, 0, 0, 0
    try:
        root = ET.parse(ontology_path).getroot()
    except Exception as exc:
        notes.append(f"Could not parse ontology XML for entity counts: {type(exc).__name__}: {exc}")
        return 0, 0, 0, 0
    class_subjects = set()
    named_subjects = set()
    object_prop_subjects = set()
    datatype_prop_subjects = set()
    for node in root.iter():
        tag = _local_name(node.tag)
        subject = node.attrib.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about") or node.attrib.get(
            "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}ID"
        )
        if tag == "Class":
            class_subjects.add(subject or id(node))
        elif tag == "NamedIndividual":
            named_subjects.add(subject or id(node))
        elif tag == "ObjectProperty":
            object_prop_subjects.add(subject or id(node))
        elif tag == "DatatypeProperty":
            datatype_prop_subjects.add(subject or id(node))
        elif tag == "Description":
            for child in node:
                if _local_name(child.tag) != "type":
                    continue
                resource = child.attrib.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource", "")
                if resource.endswith("#Class"):
                    class_subjects.add(subject or id(node))
                elif resource.endswith("#NamedIndividual"):
                    named_subjects.add(subject or id(node))
                elif resource.endswith("#ObjectProperty"):
                    object_prop_subjects.add(subject or id(node))
                elif resource.endswith("#DatatypeProperty"):
                    datatype_prop_subjects.add(subject or id(node))
    return len(class_subjects), len(named_subjects), len(object_prop_subjects), len(datatype_prop_subjects)


def _run_hermit(
    *,
    ontology_path: Path,
    hermit_jar: Optional[Path],
    hermit_report: Optional[Path],
    java_executable: str,
) -> Tuple[Optional[bool], Optional[int], str, List[str]]:
    notes: List[str] = []
    if not hermit_jar:
        imported = _load_existing_hermit_report(ontology_path, hermit_report)
        if imported:
            consistency, unsat_count, status, note = imported
            return consistency, unsat_count, status, [note]
        return None, None, "not_run_no_hermit_jar", []
    if not hermit_jar.exists():
        imported = _load_existing_hermit_report(ontology_path, hermit_report)
        if imported:
            consistency, unsat_count, status, note = imported
            note = f"HermiT jar not found at {hermit_jar}; {note}"
            return consistency, unsat_count, status, [note]
        return None, None, f"not_run_hermit_jar_not_found:{hermit_jar}", []
    try:
        completed = subprocess.run(
            [java_executable, "-jar", str(hermit_jar), str(ontology_path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        imported = _load_existing_hermit_report(ontology_path, hermit_report)
        if imported:
            consistency, unsat_count, status, note = imported
            note = f"Direct HermiT jar call failed ({type(exc).__name__}: {str(exc)[:180]}); {note}"
            return consistency, unsat_count, status, [note]
        return None, None, f"not_run_hermit_error:{type(exc).__name__}:{str(exc)[:300]}", []
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    lowered = output.lower()
    if completed.returncode == 0 and "inconsistent" not in lowered:
        return True, 0 if "unsatisfiable" not in lowered else None, "completed", notes
    if "inconsistent" in lowered:
        return False, None, "completed_inconsistent", notes
    imported = _load_existing_hermit_report(ontology_path, hermit_report)
    if imported:
        consistency, unsat_count, status, note = imported
        note = f"Direct evaluator call to {hermit_jar} returned completed_unclear_exit_{completed.returncode}; {note}"
        return consistency, unsat_count, status, [note]
    return None, None, f"completed_unclear_exit_{completed.returncode}", notes


def _load_existing_hermit_report(
    ontology_path: Path, hermit_report: Optional[Path]
) -> Optional[Tuple[Optional[bool], Optional[int], str, str]]:
    """Import a completed HermiT report produced by the ontology project.

    The HermiT jar bundled with Protege-style distributions is not always a
    standalone command-line jar. For reproducible paper reporting, the
    evaluator can import the ontology repository's own reasoner report when it
    refers to the same ontology path.
    """

    if not hermit_report or not hermit_report.exists():
        return None
    payload = _read_json_report(hermit_report)
    if not payload:
        return None
    report_ontology = str(payload.get("ontology") or "")
    if report_ontology and Path(report_ontology).resolve() == ontology_path.resolve():
        same_ontology = True
        match_basis = "same ontology path"
    elif payload.get("ontology_sha256"):
        actual_sha256 = hashlib.sha256(ontology_path.read_bytes()).hexdigest()
        same_ontology = actual_sha256.lower() == str(payload["ontology_sha256"]).lower()
        match_basis = "same ontology content (SHA-256)"
    else:
        same_ontology = not report_ontology
        match_basis = "report contains no ontology path"
    if not same_ontology:
        return None
    status = str(payload.get("status") or "").upper()
    consistency = payload.get("consistent")
    unsat_count = payload.get("unsatisfiable_count")
    if status == "PASS" and consistency is True:
        reasoner_status = "completed_from_existing_hermit_report"
    elif consistency is False:
        reasoner_status = "completed_from_existing_hermit_report_inconsistent"
    else:
        reasoner_status = "completed_from_existing_hermit_report_unclear"
    note = (
        f"Formal HermiT result imported from {hermit_report} for the {match_basis}: "
        f"status={payload.get('status')}, consistent={payload.get('consistent')}, "
        f"unsatisfiable_count={payload.get('unsatisfiable_count')}, "
        f"duration_seconds={payload.get('duration_seconds')}."
    )
    return consistency if isinstance(consistency, bool) else None, unsat_count, reasoner_status, note


def _read_json_report(path: Path) -> Optional[Dict[str, object]]:
    """Read JSON reports that may have been emitted by Python or PowerShell."""

    for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le"):
        try:
            payload = json.loads(path.read_text(encoding=encoding))
            return payload if isinstance(payload, dict) else None
        except Exception:
            continue
    return None


def _run_cq_queries(ontology_path: Path, query_dir: Path) -> Tuple[int, int, List[str]]:
    notes: List[str] = []
    validation_dir = query_dir / "validation"
    query_files = sorted(validation_dir.glob("*.ask.rq")) if validation_dir.exists() else []
    if not query_files:
        notes.append(f"No CQ ASK validation queries found under {validation_dir}")
        return 0, 0, notes
    try:
        rdflib = _import_rdflib(notes)
    except Exception:
        notes.append(f"rdflib is not installed; {len(query_files)} CQ ASK queries were found but not executed.")
        return 0, 0, notes
    graph = rdflib.Graph()
    try:
        graph.parse(str(ontology_path))
    except Exception as exc:
        notes.append(f"rdflib could not parse ontology: {type(exc).__name__}: {exc}")
        return 0, 0, notes
    passed = 0
    for query_file in query_files:
        query_text = query_file.read_text(encoding="utf-8")
        expected = _expected_ask_result(query_file, query_text)
        try:
            result = bool(graph.query(query_text))
        except Exception as exc:
            notes.append(f"CQ query failed: {query_file.name}: {type(exc).__name__}: {exc}")
            continue
        if result == expected:
            passed += 1
        else:
            notes.append(f"CQ query expectation mismatch: {query_file.name}; expected {expected}, got {result}")
    return passed, len(query_files), notes


def _import_rdflib(notes: List[str]):
    """Import rdflib, using the local optional dependency folder if needed."""

    try:
        import rdflib  # type: ignore

        notes.append(f"SPARQL CQ execution completed with rdflib {getattr(rdflib, '__version__', 'unknown')}.")
        return rdflib
    except Exception:
        candidate_dirs = [
            Path.cwd() / ".codex_pydeps",
            Path(__file__).resolve().parents[1] / ".codex_pydeps",
        ]
        for candidate in candidate_dirs:
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
        import rdflib  # type: ignore

        notes.append(
            f"SPARQL CQ execution completed with rdflib {getattr(rdflib, '__version__', 'unknown')} "
            "loaded from the local optional dependency folder."
        )
        return rdflib


def _expected_ask_result(query_file: Path, query_text: str) -> bool:
    """Return the expected boolean result for a SPARQL ASK validation query.

    PSQ-SCO v9.1 uses both positive checks and negative-control checks. The
    negative controls are written as absence checks, for example `FILTER NOT
    EXISTS { ... }`. A passing absence check therefore returns `true`; the
    `NEG` filename label means "negative-control case", not "expected false".

    A query can override the default by adding a comment such as:
    `# expected: false`.
    """

    for line in query_text.splitlines()[:8]:
        stripped = line.strip().lower()
        if not stripped.startswith("#") or "expected" not in stripped:
            continue
        if "false" in stripped:
            return False
        if "true" in stripped:
            return True
    return True


def _mapping_tests(records: Iterable[ScenarioRecord]) -> Tuple[int, int, int]:
    critical_fields = ("role", "stage_id", "age_group_code", "channel", "variant")
    total = 0
    passed = 0
    preserved = 0
    for record in records:
        raw = record.raw or {}
        scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
        case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
        if not scenario or not case:
            continue
        total += 1
        field_results: List[bool] = []
        for field in critical_fields:
            expected = case.get(field)
            actual = scenario.get(field)
            field_results.append(str(expected).lower() == str(actual).lower())
        if all(field_results):
            passed += 1
        if all(scenario.get(field) is not None for field in critical_fields):
            preserved += 1
    return passed, total, preserved


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag
