"""Targeted PSQ-SCO evaluation repair for the frozen 1,440-output study.

This module deliberately wraps, rather than edits, the existing evaluator.  It
adds canonical local provenance resolution, an equal-weight secondary OCI, a
deterministic weight-sensitivity analysis, and matched-case diagnostics.
Generation models are never called.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from psq_sco_generation.ontology import PSQSCOOntology  # noqa: E402
from three_layer_evaluation.io import load_jsonl_records  # noqa: E402
from three_layer_evaluation.models import METHOD_LABELS, METHOD_ORDER, ScenarioRecord  # noqa: E402
from three_layer_evaluation.scenario_checks import (  # noqa: E402
    _concept_matches,
    _has_safe_response,
    _tokenize,
    generated_concepts,
    infer_method,
    required_concepts,
    score_records,
)


DEFAULT_INPUT_ROOT = (
    PROJECT_ROOT
    / "output"
    / "paper120_live_recovered_final"
    / "20260714_031104"
    / "generated_scenarios"
)
DEFAULT_ONTOLOGY_PATH = (
    PACKAGE_ROOT / "ontology" / "ontology" / "personashield-psq-sco-v9.1.owl"
)
DEFAULT_DATASET_CATALOG = (
    PACKAGE_ROOT / "ontology" / "data" / "ontology_bindings" / "dataset-catalog.json"
)
DEFAULT_CORPUS_ROOT = PROJECT_ROOT / "output"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "evaluation_rerun"

EQUAL_WEIGHTS = {
    "json_validity": 0.20,
    "control_adherence": 0.20,
    "required_concept_f1": 0.20,
    "grounding_completeness": 0.20,
    "non_contradiction": 0.20,
}
LEGACY_WEIGHTS = {
    "json_validity": 0.20,
    "control_adherence": 0.25,
    "required_concept_f1": 0.25,
    "grounding_completeness": 0.20,
    "non_contradiction": 0.10,
}
COMPONENT_ORDER = tuple(EQUAL_WEIGHTS)
SENSITIVITY_SEED = 20260723
SENSITIVITY_DRAWS = 10_000
EXPECTED_RECORDS = 1_440
EXPECTED_CASES = 120
EXPECTED_MODELS = 3
EXPECTED_CONDITIONS = 4
CLAIM_SOURCE_SUPPORT_STATUS = "not_evaluated"

TOKEN_RE = re.compile(r"\S+")
ONTOLOGY_RECORD_PREFIX = "PSQ-SCO-v9.1::ontology_record_"
ONTOLOGY_DYNAMIC_PREFIX = "PSQ-SCO-v9.1::"
DATASET_SUFFIX_RE = re.compile(r"_(?:ham|scam)_(?:en|th)$", re.IGNORECASE)


@dataclass(frozen=True)
class TraceabilityResult:
    """Resolution result for one output's declared provenance links."""

    expected_trace_ids: Tuple[str, ...]
    resolved_trace_ids: Tuple[str, ...]
    missing_trace_ids: Tuple[str, ...]
    wrong_target_trace_ids: Tuple[str, ...]
    duplicate_or_conflicting_trace_ids: Tuple[str, ...]
    traceability_score: Optional[float]
    traceability_applicable: bool
    claim_source_support: str = CLAIM_SOURCE_SUPPORT_STATUS

    def export_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        for field in (
            "expected_trace_ids",
            "resolved_trace_ids",
            "missing_trace_ids",
            "wrong_target_trace_ids",
            "duplicate_or_conflicting_trace_ids",
        ):
            payload[field] = json.dumps(payload[field], ensure_ascii=False)
        return payload


class CanonicalTraceRegistry:
    """Frozen local resolver for ontology, dataset, and retrieved-source links."""

    def __init__(
        self,
        ontology_path: Path,
        dataset_catalog_path: Path,
        corpus_root: Path,
    ) -> None:
        self.ontology_path = ontology_path.resolve()
        self.dataset_catalog_path = dataset_catalog_path.resolve()
        self.corpus_root = corpus_root.resolve()
        self.ontology = PSQSCOOntology(self.ontology_path)
        self.ontology_ids = frozenset(self.ontology.by_id)
        self.external_files = self._index_external_files()
        self.dataset_aliases = self._load_dataset_aliases()

    def _index_external_files(self) -> Dict[Tuple[str, str], Path]:
        indexed: Dict[Tuple[str, str], Path] = {}
        for channel in ("email", "sms", "voice"):
            channel_dir = self.corpus_root / channel
            if not channel_dir.exists():
                continue
            for path in channel_dir.glob("*.jsonl"):
                indexed[(channel, path.name.lower())] = path.resolve()
        return indexed

    def _load_dataset_aliases(self) -> frozenset[str]:
        aliases: set[str] = set()
        if self.dataset_catalog_path.exists():
            payload = json.loads(self.dataset_catalog_path.read_text(encoding="utf-8"))
            for collection in payload.get("collections", []):
                aliases.add(_normalize_identifier(collection.get("id", "")))
                for path_value in collection.get("paths", []):
                    aliases.add(_normalize_identifier(Path(path_value).stem))
        for path in self.external_files.values():
            aliases.add(_normalize_identifier(_dataset_stem_from_source_file(path.name)))
        return frozenset(value for value in aliases if value)

    def resolve_external_file(self, channel: str, source_file: str) -> Optional[Path]:
        return self.external_files.get((channel.lower(), Path(source_file).name.lower()))

    def resolve_dataset(self, source_dataset: str, source_file: str) -> bool:
        if not source_dataset:
            return False
        dataset_key = _normalize_identifier(source_dataset)
        file_key = _normalize_identifier(_dataset_stem_from_source_file(source_file))
        return bool(dataset_key and (dataset_key == file_key or dataset_key in self.dataset_aliases))

    def resolve_ontology_id(self, identifier: str) -> bool:
        return identifier in self.ontology_ids

    def provenance_targets(self, template_id: str) -> Tuple[str, ...]:
        record = self.ontology.by_id.get(template_id)
        if record is None:
            return ()
        values: List[str] = []
        for key, property_values in record.properties.items():
            if key.lstrip("}").endswith("hasProvenanceRecord"):
                values.extend(str(value) for value in property_values)
        return tuple(dict.fromkeys(values))

    def ontology_dataset_matches(self, source_dataset: str) -> bool:
        return Path(source_dataset).name.lower() == self.ontology_path.name.lower()


class TraceAccumulator:
    """Mutable helper that preserves link order while recording diagnostics."""

    def __init__(self) -> None:
        self.expected: List[str] = []
        self.resolved: List[str] = []
        self.missing: List[str] = []
        self.wrong: List[str] = []
        self.duplicates: List[str] = []
        self._seen: set[str] = set()

    def add(self, trace_id: str, resolved: bool, *, wrong_target: Optional[str] = None) -> None:
        if trace_id in self._seen:
            self.duplicates.append(f"duplicate:{trace_id}")
            return
        self._seen.add(trace_id)
        self.expected.append(trace_id)
        if resolved:
            self.resolved.append(trace_id)
        elif wrong_target:
            self.wrong.append(f"{trace_id}=>{wrong_target}")
        else:
            self.missing.append(trace_id)

    def conflict(self, message: str) -> None:
        self.duplicates.append(f"conflict:{message}")

    def finish(self) -> TraceabilityResult:
        expected = tuple(self.expected)
        score = len(self.resolved) / len(expected) if expected else None
        return TraceabilityResult(
            expected_trace_ids=expected,
            resolved_trace_ids=tuple(self.resolved),
            missing_trace_ids=tuple(self.missing),
            wrong_target_trace_ids=tuple(self.wrong),
            duplicate_or_conflicting_trace_ids=tuple(dict.fromkeys(self.duplicates)),
            traceability_score=score,
            traceability_applicable=bool(expected),
        )


def traceability_for_record(
    record: ScenarioRecord,
    registry: CanonicalTraceRegistry,
) -> TraceabilityResult:
    """Resolve all declared source, dataset, provenance, and context links locally.

    The contract is conditional on links actually declared by the method.  A
    prompt-only row, or a RAG row with no retrieved context, therefore receives
    ``traceability_score=None`` rather than a misleading zero or vacuous one.
    Completeness remains represented by G.
    """

    raw = record.raw or {}
    scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
    case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
    channel = str(case.get("channel", scenario.get("channel", ""))).lower()
    meta = scenario.get("generation_meta") if isinstance(scenario.get("generation_meta"), dict) else {}
    raw_context = raw.get("rag_examples") if isinstance(raw.get("rag_examples"), list) else []
    final_context = meta.get("rag_trace") if isinstance(meta.get("rag_trace"), list) else []
    packet = raw.get("semantic_packet") if isinstance(raw.get("semantic_packet"), dict) else {}
    acc = TraceAccumulator()

    seen_context_targets: Dict[str, int] = {}
    for index, item in enumerate(raw_context):
        if not isinstance(item, dict):
            acc.add(f"ordered_context:{index}:object", False)
            continue
        source_file = str(item.get("source_file", "")).strip()
        source_dataset = str(item.get("source_dataset", "")).strip()
        ontology_ids = tuple(str(value) for value in (item.get("ontology_ids") or []) if str(value))

        context_id = f"ordered_context:{index}:{source_file or '<missing-source>'}"
        final_item = final_context[index] if index < len(final_context) and isinstance(final_context[index], dict) else {}
        final_source = str(final_item.get("source_file", "")).strip()
        ordered_ok = bool(source_file and final_source == source_file)
        wrong_target = final_source or "<missing-final-trace>"
        acc.add(context_id, ordered_ok, wrong_target=wrong_target if not ordered_ok else None)

        if source_file:
            if source_file in seen_context_targets:
                acc.conflict(
                    f"source repeated at positions {seen_context_targets[source_file]} and {index}:"
                    f"{source_file}"
                )
            else:
                seen_context_targets[source_file] = index

        if source_file.startswith(ONTOLOGY_DYNAMIC_PREFIX):
            _add_ontology_context_links(
                acc=acc,
                registry=registry,
                index=index,
                item=item,
                source_file=source_file,
                source_dataset=source_dataset,
                ontology_ids=ontology_ids,
            )
        else:
            source_id = f"source_file:{channel}:{source_file or '<missing>'}"
            resolved_path = registry.resolve_external_file(channel, source_file) if source_file else None
            acc.add(source_id, resolved_path is not None)
            dataset_id = f"dataset:{source_dataset or '<missing>'}@context:{index}"
            dataset_ok = bool(
                resolved_path is not None
                and registry.resolve_dataset(source_dataset, source_file)
            )
            acc.add(
                dataset_id,
                dataset_ok,
                wrong_target=(
                    f"source_file={source_file or '<missing>'}"
                    if resolved_path is not None and not dataset_ok
                    else None
                ),
            )

    if packet:
        ontology_path_value = str(packet.get("ontology_path", "")).strip()
        packet_dataset_id = f"dataset:ontology:{Path(ontology_path_value).name or '<missing>'}"
        packet_dataset_ok = bool(
            ontology_path_value
            and Path(ontology_path_value).resolve() == registry.ontology_path
        )
        acc.add(
            packet_dataset_id,
            packet_dataset_ok,
            wrong_target=ontology_path_value if ontology_path_value and not packet_dataset_ok else None,
        )
        for section in ("selected_templates", "required_rules", "evidence_sources"):
            values = packet.get(section) if isinstance(packet.get(section), list) else []
            section_seen: set[str] = set()
            for index, item in enumerate(values):
                identifier = str(item.get("id", "")) if isinstance(item, dict) else ""
                trace_id = f"ordered_packet:{section}:{index}:{identifier or '<missing>'}"
                acc.add(trace_id, bool(identifier and registry.resolve_ontology_id(identifier)))
                if identifier in section_seen:
                    acc.conflict(f"duplicate packet identifier in {section}:{identifier}")
                section_seen.add(identifier)
                if section == "selected_templates" and identifier:
                    provenance_targets = registry.provenance_targets(identifier)
                    if not provenance_targets:
                        acc.add(f"provenance_record:{identifier}:<missing>", False)
                    for provenance_id in provenance_targets:
                        provenance_trace_id = f"provenance_record:{identifier}:{provenance_id}"
                        acc.add(
                            provenance_trace_id,
                            registry.resolve_ontology_id(provenance_id),
                        )

    text_trace = meta.get("ontology_text_trace") if isinstance(meta.get("ontology_text_trace"), dict) else {}
    for index, identifier in enumerate(text_trace.get("source_ids") or []):
        identifier = str(identifier)
        acc.add(
            f"ontology_trace_source:{index}:{identifier}",
            registry.resolve_ontology_id(identifier),
        )

    if len(final_context) != len(raw_context) and (raw_context or final_context):
        acc.conflict(f"ordered context length raw={len(raw_context)} final={len(final_context)}")
    return acc.finish()


def _add_ontology_context_links(
    *,
    acc: TraceAccumulator,
    registry: CanonicalTraceRegistry,
    index: int,
    item: Mapping[str, Any],
    source_file: str,
    source_dataset: str,
    ontology_ids: Sequence[str],
) -> None:
    dataset_id = f"dataset:ontology_text:{source_dataset or '<missing>'}@context:{index}"
    dataset_ok = registry.ontology_dataset_matches(source_dataset)
    acc.add(
        dataset_id,
        dataset_ok,
        wrong_target=source_dataset if source_dataset and not dataset_ok else None,
    )

    if source_file.startswith(ONTOLOGY_RECORD_PREFIX):
        record_id = source_file[len(ONTOLOGY_RECORD_PREFIX) :]
        correct_target = record_id in ontology_ids
        acc.add(
            f"ontology_record:{record_id}@context:{index}",
            bool(registry.resolve_ontology_id(record_id) and correct_target),
            wrong_target=("|".join(ontology_ids) or "<missing-ontology-ids>") if not correct_target else None,
        )
    else:
        document_type = str(item.get("document_type", "")).strip()
        dynamic_ok = bool(
            document_type in {"graph_cot_trace", "selected_subgraph_walk"}
            and ontology_ids
            and all(registry.resolve_ontology_id(identifier) for identifier in ontology_ids)
        )
        acc.add(
            f"ontology_document:{source_file}@context:{index}",
            dynamic_ok,
        )

    local_seen: set[str] = set()
    for ontology_index, identifier in enumerate(ontology_ids):
        trace_id = f"ontology_id:{index}:{ontology_index}:{identifier}"
        acc.add(trace_id, registry.resolve_ontology_id(identifier))
        if identifier in local_seen:
            acc.conflict(f"duplicate ontology id in context {index}:{identifier}")
        local_seen.add(identifier)


def operational_index(
    row: Mapping[str, Any],
    weights: Mapping[str, float],
) -> float:
    """Calculate the five-component descriptive operational index."""

    components = {
        "json_validity": float(row["json_validity"]),
        "control_adherence": float(row["control_adherence"]),
        "required_concept_f1": float(row["required_concept_f1"]),
        "grounding_completeness": float(row["grounding_completeness"]),
        "non_contradiction": 1.0 - float(row["contradiction"]),
    }
    return sum(weights[key] * components[key] for key in COMPONENT_ORDER)


def deterministic_weight_vectors(
    draws: int = SENSITIVITY_DRAWS,
    seed: int = SENSITIVITY_SEED,
) -> List[Tuple[float, ...]]:
    """Sample uniform-simplex weights using normalized exponential draws."""

    rng = random.Random(seed)
    vectors: List[Tuple[float, ...]] = []
    for _ in range(draws):
        values = [-math.log(max(rng.random(), sys.float_info.min)) for _ in COMPONENT_ORDER]
        denominator = sum(values)
        vectors.append(tuple(value / denominator for value in values))
    return vectors


def _rank_descending(values: Mapping[str, float]) -> Dict[str, int]:
    rounded = {key: round(value, 12) for key, value in values.items()}
    return {
        key: 1 + sum(1 for other_value in rounded.values() if other_value > value)
        for key, value in rounded.items()
    }


def _condition_component_means(
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[str, float]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["method"])].append(row)
    output: Dict[str, Dict[str, float]] = {}
    for method in METHOD_ORDER:
        method_rows = grouped[method]
        output[method] = {
            "json_validity": _mean(method_rows, "json_validity"),
            "control_adherence": _mean(method_rows, "control_adherence"),
            "required_concept_f1": _mean(method_rows, "required_concept_f1"),
            "grounding_completeness": _mean(method_rows, "grounding_completeness"),
            "non_contradiction": 1.0 - _mean(method_rows, "contradiction"),
        }
    return output


def sensitivity_analysis(
    rows: Sequence[Mapping[str, Any]],
    *,
    draws: int = SENSITIVITY_DRAWS,
    seed: int = SENSITIVITY_SEED,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return nominal ranks, first-place probability, and pairwise stability."""

    scopes: Dict[str, Sequence[Mapping[str, Any]]] = {"overall": rows}
    for model_key in sorted({str(row["model_key"]) for row in rows}):
        scopes[f"model:{model_key}"] = [
            row for row in rows if str(row["model_key"]) == model_key
        ]

    vectors = deterministic_weight_vectors(draws=draws, seed=seed)
    csv_rows: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        "draws": draws,
        "seed": seed,
        "distribution": "Dirichlet(1,1,1,1,1) via normalized exponential draws",
        "component_order": list(COMPONENT_ORDER),
        "scopes": {},
    }
    for scope, scope_rows in scopes.items():
        component_means = _condition_component_means(scope_rows)
        equal_scores = {
            method: sum(EQUAL_WEIGHTS[key] * values[key] for key in COMPONENT_ORDER)
            for method, values in component_means.items()
        }
        legacy_scores = {
            method: sum(LEGACY_WEIGHTS[key] * values[key] for key in COMPONENT_ORDER)
            for method, values in component_means.items()
        }
        equal_ranks = _rank_descending(equal_scores)
        legacy_ranks = _rank_descending(legacy_scores)
        first_place = Counter({method: 0.0 for method in METHOD_ORDER})
        sampled_scores: Dict[str, List[float]] = {method: [] for method in METHOD_ORDER}
        pair_matches = Counter()

        for vector in vectors:
            draw_scores = {
                method: sum(
                    vector[index] * component_means[method][component]
                    for index, component in enumerate(COMPONENT_ORDER)
                )
                for method in METHOD_ORDER
            }
            for method, value in draw_scores.items():
                sampled_scores[method].append(value)
            draw_ranks = _rank_descending(draw_scores)
            winners = [method for method, rank in draw_ranks.items() if rank == 1]
            for method in winners:
                first_place[method] += 1.0 / len(winners)
            for left, right in combinations(METHOD_ORDER, 2):
                expected_relation = _sign(equal_scores[left] - equal_scores[right])
                observed_relation = _sign(draw_scores[left] - draw_scores[right])
                if observed_relation == expected_relation:
                    pair_matches[(left, right)] += 1

        scope_payload: Dict[str, Any] = {
            "equal_scores": equal_scores,
            "legacy_scores": legacy_scores,
            "equal_ranks": equal_ranks,
            "legacy_ranks": legacy_ranks,
            "rank_reversals": {
                method: equal_ranks[method] != legacy_ranks[method]
                for method in METHOD_ORDER
            },
            "first_place_proportions": {
                method: first_place[method] / draws for method in METHOD_ORDER
            },
            "pairwise_rank_stability": {},
        }
        for method in METHOD_ORDER:
            values = sorted(sampled_scores[method])
            csv_rows.append(
                {
                    "scope": scope,
                    "analysis_type": "nominal_and_distribution",
                    "condition_a": method,
                    "condition_b": "",
                    "equal_weight_score": equal_scores[method],
                    "legacy_weight_score": legacy_scores[method],
                    "equal_weight_rank": equal_ranks[method],
                    "legacy_weight_rank": legacy_ranks[method],
                    "rank_reversal": equal_ranks[method] != legacy_ranks[method],
                    "value": first_place[method] / draws,
                    "value_definition": "first_place_proportion",
                    "sample_score_min": values[0],
                    "sample_score_p05": _quantile(values, 0.05),
                    "sample_score_mean": statistics.fmean(values),
                    "sample_score_p95": _quantile(values, 0.95),
                    "sample_score_max": values[-1],
                    "draws": draws,
                    "seed": seed,
                }
            )
        for left, right in combinations(METHOD_ORDER, 2):
            stability = pair_matches[(left, right)] / draws
            if equal_scores[left] > equal_scores[right]:
                equal_order = f"{left}>{right}"
            elif equal_scores[right] > equal_scores[left]:
                equal_order = f"{right}>{left}"
            else:
                equal_order = f"{left}={right}"
            scope_payload["pairwise_rank_stability"][f"{left}_vs_{right}"] = {
                "equal_weight_order": equal_order,
                "stability": stability,
            }
            csv_rows.append(
                {
                    "scope": scope,
                    "analysis_type": "pairwise_rank_stability",
                    "condition_a": left,
                    "condition_b": right,
                    "equal_weight_score": equal_scores[left] - equal_scores[right],
                    "legacy_weight_score": legacy_scores[left] - legacy_scores[right],
                    "equal_weight_rank": "",
                    "legacy_weight_rank": "",
                    "rank_reversal": "",
                    "value": stability,
                    "value_definition": (
                        "proportion_of_sampled_weights_preserving_equal_weight_pair_order"
                    ),
                    "sample_score_min": "",
                    "sample_score_p05": "",
                    "sample_score_mean": "",
                    "sample_score_p95": "",
                    "sample_score_max": "",
                    "draws": draws,
                    "seed": seed,
                }
            )
        summary["scopes"][scope] = scope_payload
    return csv_rows, summary


def build_component_rows(
    records: Sequence[ScenarioRecord],
    registry: CanonicalTraceRegistry,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run the existing evaluator and augment each row with repaired metrics."""

    scores = score_records(records)
    if len(scores) != len(records):
        raise RuntimeError("Existing evaluator changed record cardinality.")
    export_rows: List[Dict[str, Any]] = []
    working_rows: List[Dict[str, Any]] = []
    for record, score in zip(records, scores):
        method = infer_method(
            record.raw,
            record.raw.get("scenario") if isinstance(record.raw.get("scenario"), dict) else {},
        )
        if method != score.method:
            raise RuntimeError(
                f"Method mismatch for {score.case_id}/{score.model_key}: {method} != {score.method}"
            )
        trace = traceability_for_record(record, registry)
        score_payload = score.as_dict()
        score_payload["oci_equal_weight"] = operational_index(score_payload, EQUAL_WEIGHTS)
        score_payload["oci_legacy_sensitivity"] = operational_index(score_payload, LEGACY_WEIGHTS)
        score_payload.update(trace.export_dict())
        score_payload["claim_source_support"] = CLAIM_SOURCE_SUPPORT_STATUS
        export_rows.append(score_payload)
        working = dict(score_payload)
        working["_record"] = record
        working["_trace"] = trace
        working_rows.append(working)
    return export_rows, working_rows


def summarize_methods(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped = _group_by(rows, "method")
    summaries: List[Dict[str, Any]] = []
    equal_scores: Dict[str, float] = {}
    legacy_scores: Dict[str, float] = {}
    for method in METHOD_ORDER:
        group = grouped[method]
        trace_values = [
            float(row["traceability_score"])
            for row in group
            if row.get("traceability_score") not in (None, "")
        ]
        decisions = Counter(str(row["automated_decision"]) for row in group)
        summary = {
            "condition_number": METHOD_ORDER.index(method) + 1,
            "method": method,
            "condition_name": METHOD_LABELS[method],
            "n": len(group),
            "json_validity_J_up": _mean(group, "json_validity"),
            "schema_completeness_up": _mean(group, "schema_completeness"),
            "game_schema_completeness_up": _mean(group, "game_schema_completeness"),
            "control_adherence_A_up": _mean(group, "control_adherence"),
            "required_concept_precision_P_up": _mean(group, "required_concept_precision"),
            "required_concept_recall_R_up": _mean(group, "required_concept_recall"),
            "required_concept_f1_F1req_up": _mean(group, "required_concept_f1"),
            "provenance_field_completeness_G_up": _mean(group, "grounding_completeness"),
            "traceability_T_up": statistics.fmean(trace_values) if trace_values else None,
            "traceability_applicable_n": len(trace_values),
            "traceability_applicable_rate": len(trace_values) / len(group),
            "contradiction_rate_E_down": _mean(group, "contradiction"),
            "ontology_scope_up": _mean(group, "ontology_semantic_scope"),
            "oci_equal_weight_secondary": _mean(group, "oci_equal_weight"),
            "oci_legacy_sensitivity_only": _mean(group, "oci_legacy_sensitivity"),
            "accepted_for_human_review_n": (
                decisions.get("ACCEPTED", 0)
                + decisions.get("ACCEPTED_FOR_HUMAN_REVIEW", 0)
            ),
            "minor_revision_n": decisions.get("MINOR_REVISION", 0),
            "major_revision_n": decisions.get("MAJOR_REVISION", 0),
            "reject_regenerate_n": decisions.get("REJECT_REGENERATE", 0),
            "schema_safe_repair_n": sum(bool(row["schema_safe_repair_used"]) for row in group),
            "live_model_content_retained_n": sum(
                bool(row["live_model_content_retained"]) for row in group
            ),
            "claim_source_support": CLAIM_SOURCE_SUPPORT_STATUS,
        }
        equal_scores[method] = float(summary["oci_equal_weight_secondary"])
        legacy_scores[method] = float(summary["oci_legacy_sensitivity_only"])
        summaries.append(summary)
    equal_ranks = _rank_descending(equal_scores)
    legacy_ranks = _rank_descending(legacy_scores)
    for summary in summaries:
        method = str(summary["method"])
        summary["oci_equal_weight_rank"] = equal_ranks[method]
        summary["oci_legacy_rank"] = legacy_ranks[method]
        summary["nominal_rank_reversal"] = equal_ranks[method] != legacy_ranks[method]
    return summaries


def summarize_models(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    for model_key in sorted({str(row["model_key"]) for row in rows}):
        model_rows = [row for row in rows if str(row["model_key"]) == model_key]
        method_rows = summarize_methods(model_rows)
        for summary in method_rows:
            summaries.append(
                {
                    "model_key": model_key,
                    "model_name": next(
                        str(row["model_name"]) for row in model_rows if row["model_name"]
                    ),
                    **summary,
                }
            )
    return summaries


def select_five_matched_cases(
    rows: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Select five disclosed diagnostic pairs and compare all four conditions."""

    pair_map: Dict[Tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        pair_map[(str(row["case_id"]), str(row["model_key"]))].append(row)
    complete_pairs = {
        key: value
        for key, value in pair_map.items()
        if {str(row["method"]) for row in value} == set(METHOD_ORDER)
    }
    selected_keys: set[Tuple[str, str]] = set()

    contradiction_candidates = sorted(
        (
            (str(row["case_id"]), str(row["model_key"]))
            for row in rows
            if row["method"] == "ontology_text_rag" and int(row["contradiction"]) == 1
        )
    )
    if not contradiction_candidates:
        raise RuntimeError("No ontology-to-text contradiction case exists in the frozen experiment.")
    contradiction_key = contradiction_candidates[0]
    selected_keys.add(contradiction_key)

    no_rag_candidates: List[Tuple[str, str]] = []
    for key, pair_rows in complete_pairs.items():
        prompt_rag_row = next(row for row in pair_rows if row["method"] == "prompt_rag")
        raw = prompt_rag_row["_record"].raw
        if not (raw.get("rag_examples") or []):
            no_rag_candidates.append(key)
    no_rag_key = next(key for key in sorted(no_rag_candidates) if key not in selected_keys)
    selected_keys.add(no_rag_key)

    tradeoff_candidates: List[Tuple[float, str, str, str]] = []
    for key, pair_rows in complete_pairs.items():
        if key in selected_keys:
            continue
        for row in pair_rows:
            gap = abs(
                float(row["required_concept_precision"])
                - float(row["required_concept_recall"])
            )
            tradeoff_candidates.append((gap, key[0], key[1], str(row["method"])))
    tradeoff_entry = sorted(
        tradeoff_candidates,
        key=lambda value: (-value[0], value[1], value[2], value[3]),
    )[0]
    tradeoff_key = (tradeoff_entry[1], tradeoff_entry[2])
    selected_keys.add(tradeoff_key)

    pair_means = {
        key: statistics.fmean(float(row["oci_equal_weight"]) for row in pair_rows)
        for key, pair_rows in complete_pairs.items()
    }
    overall_median = statistics.median(pair_means.values())
    median_key = sorted(
        (
            (abs(value - overall_median), key[0], key[1])
            for key, value in pair_means.items()
            if key not in selected_keys
        )
    )[0][1:]
    selected_keys.add(median_key)

    legitimate_candidates: List[Tuple[float, str, str]] = []
    legitimate_values = [
        value
        for key, value in pair_means.items()
        if str(complete_pairs[key][0]["variant"]).lower() == "real"
        and key not in selected_keys
    ]
    legitimate_median = statistics.median(legitimate_values)
    for key, value in pair_means.items():
        if (
            str(complete_pairs[key][0]["variant"]).lower() == "real"
            and key not in selected_keys
        ):
            legitimate_candidates.append((abs(value - legitimate_median), key[0], key[1]))
    legitimate_key = sorted(legitimate_candidates)[0][1:]

    selections = [
        (
            "representative_median_performing",
            median_key,
            (
                "Pair mean OCI_eq is nearest the median across complete case-model pairs "
                f"(global median={overall_median:.6f})."
            ),
        ),
        (
            "ontology_to_text_contradiction",
            contradiction_key,
            "The frozen ontology-to-text output triggered the deterministic contradiction rule.",
        ),
        (
            "external_rag_returned_no_text",
            no_rag_key,
            "The Text-RAG condition stored no retrieved external context for this matched pair.",
        ),
        (
            "legitimate_communication",
            legitimate_key,
            "A real/legitimate case nearest the median of eligible legitimate pairs.",
        ),
        (
            "clearest_precision_recall_tradeoff",
            tradeoff_key,
            (
                "Contains the largest remaining absolute method-conditioned precision/recall "
                f"gap ({tradeoff_entry[0]:.6f}, method={tradeoff_entry[3]})."
            ),
        ),
    ]

    output: List[Dict[str, Any]] = []
    for selection_type, key, reason in selections:
        pair_rows = sorted(
            complete_pairs[key],
            key=lambda row: METHOD_ORDER.index(str(row["method"])),
        )
        comparisons: List[Dict[str, Any]] = []
        for row in pair_rows:
            record: ScenarioRecord = row["_record"]
            raw = record.raw
            scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
            case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
            required = required_concepts(raw, scenario, case)
            detected = generated_concepts(scenario)
            extras = _extra_concepts(required, detected)
            comparisons.append(
                {
                    "condition_number": METHOD_ORDER.index(str(row["method"])) + 1,
                    "method": row["method"],
                    "condition_name": METHOD_LABELS[str(row["method"])],
                    "actual_excerpt": _actual_excerpt(scenario),
                    "required_concepts": required,
                    "detected_concepts": detected,
                    "missing_concepts": _json_list(row.get("missing_required_concepts")),
                    "extra_method_conditioned_concepts": extras,
                    "required_concept_precision": row["required_concept_precision"],
                    "required_concept_recall": row["required_concept_recall"],
                    "required_concept_f1": row["required_concept_f1"],
                    "provenance_field_completeness_G": row["grounding_completeness"],
                    "traceability_T": row["traceability_score"],
                    "traceability_applicable": row["traceability_applicable"],
                    "contradiction_E": row["contradiction"],
                    "contradiction_reasons": _semicolon_list(row.get("contradiction_reasons")),
                    "safe_action_result": _has_safe_response(scenario),
                    "external_context_count": len(raw.get("rag_examples") or []),
                    "automated_decision": row["automated_decision"],
                    "concise_interpretation": _diagnostic_interpretation(row, raw),
                }
            )
        first = pair_rows[0]
        output.append(
            {
                "selection_type": selection_type,
                "selection_reason": reason,
                "case_id": key[0],
                "model_key": key[1],
                "role": first["role"],
                "stage_id": first["stage_id"],
                "age_group_code": first["age_group_code"],
                "channel": first["channel"],
                "variant": first["variant"],
                "comparisons": comparisons,
            }
        )
    return output


def _extra_concepts(required: Sequence[str], detected: Sequence[str]) -> List[str]:
    required_tokens = [_tokenize(value) for value in required]
    extras: List[str] = []
    for value in detected:
        generated_tokens = _tokenize(value)
        if generated_tokens and not any(
            _concept_matches(reference_tokens, generated_tokens)
            for reference_tokens in required_tokens
        ):
            extras.append(value)
    return list(dict.fromkeys(extras))


def _actual_excerpt(scenario: Mapping[str, Any], target_words: int = 58) -> str:
    preferred_fields = (
        "title",
        "opening_hook",
        "message_text",
        "sms_text",
        "email_subject",
        "email_body",
        "voice_script",
        "body",
        "scenario_text",
        "correct_action",
        "hint_text",
    )
    fragments: List[str] = []
    for field in preferred_fields:
        value = scenario.get(field)
        if isinstance(value, str) and value.strip():
            fragments.append(value.strip())
        elif isinstance(value, list):
            fragments.extend(str(item).strip() for item in value if str(item).strip())
    for choice in scenario.get("game_choices") or []:
        if isinstance(choice, dict):
            for field in ("label", "feedback", "outcome"):
                value = choice.get(field)
                if isinstance(value, str) and value.strip():
                    fragments.append(value.strip())
    text = " ".join(fragments)
    words = TOKEN_RE.findall(text)
    if len(words) < 40:
        for key, value in scenario.items():
            if key in preferred_fields or key in {"generation_meta", "game_choices"}:
                continue
            if isinstance(value, str) and value.strip():
                words.extend(TOKEN_RE.findall(value))
            elif isinstance(value, list):
                words.extend(TOKEN_RE.findall(" ".join(str(item) for item in value)))
            if len(words) >= 40:
                break
    return " ".join(words[: min(70, max(40, target_words))])


def _diagnostic_interpretation(row: Mapping[str, Any], raw: Mapping[str, Any]) -> str:
    notes: List[str] = []
    if int(row["contradiction"]):
        notes.append("The deterministic contradiction gate failed.")
    else:
        notes.append("No deterministic contradiction was detected.")
    if row["method"] == "prompt_rag" and not (raw.get("rag_examples") or []):
        notes.append("No external context was retrieved, so traceability is not applicable.")
    elif row.get("traceability_score") is None:
        notes.append("The method declared no trace links; T is not applicable.")
    else:
        notes.append(
            f"Declared trace links resolved at T={float(row['traceability_score']):.3f}."
        )
    notes.append(
        "The method-conditioned P/R/F1 diagnostic describes exposed control vocabulary, "
        "not general text quality."
    )
    return " ".join(notes)


def write_five_case_markdown(path: Path, cases: Sequence[Mapping[str, Any]]) -> None:
    lines = [
        "# Five Matched Diagnostic Cases",
        "",
        (
            "These cases were selected deterministically from stored outputs. Each comparison "
            "holds case ID and model fixed across all four generation conditions. Excerpts are "
            "verbatim 40–70-word slices assembled from player-facing scenario fields."
        ),
        "",
    ]
    for case in cases:
        lines.extend(
            [
                f"## {case['selection_type']}: {case['case_id']} / {case['model_key']}",
                "",
                f"**Selection reason:** {case['selection_reason']}",
                "",
                (
                    f"Controls: role={case['role']}; stage={case['stage_id']}; "
                    f"age={case['age_group_code']}; channel={case['channel']}; "
                    f"variant={case['variant']}."
                ),
                "",
                "| Condition | P | R | F1_req | G | T | E | Safe action | Decision |",
                "|---|---:|---:|---:|---:|---:|---:|:---:|---|",
            ]
        )
        for comparison in case["comparisons"]:
            t_value = (
                f"{comparison['traceability_T']:.3f}"
                if comparison["traceability_T"] is not None
                else "n/a"
            )
            lines.append(
                "| {condition} | {p:.3f} | {r:.3f} | {f1:.3f} | {g:.3f} | {t} | "
                "{e} | {safe} | {decision} |".format(
                    condition=comparison["condition_name"],
                    p=comparison["required_concept_precision"],
                    r=comparison["required_concept_recall"],
                    f1=comparison["required_concept_f1"],
                    g=comparison["provenance_field_completeness_G"],
                    t=t_value,
                    e=comparison["contradiction_E"],
                    safe="pass" if comparison["safe_action_result"] else "fail",
                    decision=comparison["automated_decision"],
                )
            )
        lines.append("")
        for comparison in case["comparisons"]:
            lines.extend(
                [
                    f"**{comparison['condition_name']} excerpt:**",
                    "",
                    f"> {comparison['actual_excerpt']}",
                    "",
                    f"- Required concepts: {', '.join(comparison['required_concepts']) or 'none'}",
                    f"- Detected concepts: {', '.join(comparison['detected_concepts']) or 'none'}",
                    f"- Missing concepts: {', '.join(comparison['missing_concepts']) or 'none'}",
                    (
                        "- Extra method-conditioned concepts: "
                        f"{', '.join(comparison['extra_method_conditioned_concepts']) or 'none'}"
                    ),
                    f"- Interpretation: {comparison['concise_interpretation']}",
                    "",
                ]
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_report(
    *,
    method_summary: Sequence[Mapping[str, Any]],
    model_summary: Sequence[Mapping[str, Any]],
    sensitivity: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    five_cases: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# Targeted PSQ-SCO Evaluation Repair",
        "",
        "## Scope",
        "",
        (
            "This rerun evaluates the frozen 1,440 stored live outputs used by the "
            "manuscript. It does not call a generation model and does not substitute "
            "the later Graph-Walk v1 ablation for the paper's protected frozen experiment."
        ),
        "",
        "## Metric contract",
        "",
        "- J: JSON parse/object validity (validation component; higher is better).",
        "- Schema completeness: required executable fields (validation component; higher is better).",
        "- A: exact adherence to eight frozen case controls (validation component; higher is better).",
        (
            "- P, R, F1_req: method-conditioned required-concept diagnostic. The reference "
            "vocabulary may differ by method, so this is a mechanism audit rather than a "
            "cross-method accuracy claim."
        ),
        (
            "- G: presence of six source/provenance fields. It does not prove that a link "
            "resolves or that a source supports a generated claim."
        ),
        (
            "- T: fraction of a method's declared source, dataset, provenance-record, and "
            "ordered-context links that resolve to the correct frozen local record. T is "
            "not applicable when a method declares no trace links."
        ),
        "- E: contradiction rate; lower is better.",
        "- Ontology scope: project-defined trace/control coverage, not OWL entailment accuracy.",
        (
            "- OCI_eq: equal-weight secondary descriptive index over J, A, F1_req, G, "
            "and 1-E. It is not a quality percentage, threshold, or learner-effect measure."
        ),
        "- Claim-source support/entailment: not evaluated.",
        "",
        "## Condition results",
        "",
        "| Condition | J | A | P | R | F1_req | G | T | E | Ont. scope | OCI_eq | OCI_legacy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in method_summary:
        t_value = (
            f"{row['traceability_T_up']:.3f}"
            if row["traceability_T_up"] is not None
            else "n/a"
        )
        lines.append(
            "| {condition} | {j:.3f} | {a:.3f} | {p:.3f} | {r:.3f} | {f1:.3f} | "
            "{g:.3f} | {t} | {e:.3f} | {scope:.3f} | {eq:.6f} | {legacy:.6f} |".format(
                condition=row["condition_name"],
                j=row["json_validity_J_up"],
                a=row["control_adherence_A_up"],
                p=row["required_concept_precision_P_up"],
                r=row["required_concept_recall_R_up"],
                f1=row["required_concept_f1_F1req_up"],
                g=row["provenance_field_completeness_G_up"],
                t=t_value,
                e=row["contradiction_rate_E_down"],
                scope=row["ontology_scope_up"],
                eq=row["oci_equal_weight_secondary"],
                legacy=row["oci_legacy_sensitivity_only"],
            )
        )
    lines.extend(
        [
            "",
            "## Model stability",
            "",
            "| Model | Condition | OCI_eq | Eq. rank | OCI_legacy | Legacy rank | Reversal |",
            "|---|---|---:|---:|---:|---:|:---:|",
        ]
    )
    for row in model_summary:
        lines.append(
            "| {model} | {condition} | {eq:.6f} | {eq_rank} | {legacy:.6f} | "
            "{legacy_rank} | {reversal} |".format(
                model=row["model_key"],
                condition=row["condition_name"],
                eq=row["oci_equal_weight_secondary"],
                eq_rank=row["oci_equal_weight_rank"],
                legacy=row["oci_legacy_sensitivity_only"],
                legacy_rank=row["oci_legacy_rank"],
                reversal="yes" if row["nominal_rank_reversal"] else "no",
            )
        )
    overall_sensitivity = sensitivity["scopes"]["overall"]
    lines.extend(
        [
            "",
            "## Weight sensitivity",
            "",
            (
                f"{sensitivity['draws']:,} nonnegative weight vectors summing to one were "
                f"sampled with seed {sensitivity['seed']} from "
                f"{sensitivity['distribution']}."
            ),
            "",
            "| Condition | First-place proportion |",
            "|---|---:|",
        ]
    )
    for method in METHOD_ORDER:
        lines.append(
            f"| {METHOD_LABELS[method]} | "
            f"{overall_sensitivity['first_place_proportions'][method]:.6f} |"
        )
    lines.extend(
        [
            "",
            "Pairwise order stability relative to the equal-weight order:",
            "",
        ]
    )
    for pair, payload in overall_sensitivity["pairwise_rank_stability"].items():
        lines.append(
            f"- `{pair}` (equal-weight order `{payload['equal_weight_order']}`): "
            f"{payload['stability']:.6f}"
        )

    trace_applicable = sum(bool(row["traceability_applicable"]) for row in rows)
    trace_diagnostic_rows = sum(
        bool(
            _json_list(row.get("missing_trace_ids"))
            or _json_list(row.get("wrong_target_trace_ids"))
            or _json_list(row.get("duplicate_or_conflicting_trace_ids"))
        )
        for row in rows
    )
    unresolved_rows = sum(
        bool(
            _json_list(row.get("missing_trace_ids"))
            or _json_list(row.get("wrong_target_trace_ids"))
        )
        for row in rows
    )
    missing_links = sum(
        len(_json_list(row.get("missing_trace_ids"))) for row in rows
    )
    wrong_target_links = sum(
        len(_json_list(row.get("wrong_target_trace_ids"))) for row in rows
    )
    duplicate_conflicts = sum(
        len(_json_list(row.get("duplicate_or_conflicting_trace_ids")))
        for row in rows
    )
    lines.extend(
        [
            "",
            "## Traceability findings",
            "",
            f"- Applicable outputs: {trace_applicable}/{len(rows)}.",
            f"- Outputs with unresolved ordered/context targets: {unresolved_rows}.",
            f"- Outputs with any trace diagnostic: {trace_diagnostic_rows}.",
            f"- Missing canonical links: {missing_links}.",
            f"- Wrong/mismatched ordered-context links: {wrong_target_links}.",
            f"- Duplicate/conflicting declarations: {duplicate_conflicts}.",
            "- T is conditional resolution; G remains the separate completeness diagnostic.",
            "- Claim-source support remains not evaluated.",
            "",
            "## Technical decisions and generation integrity",
            "",
        ]
    )
    decisions = Counter(str(row["automated_decision"]) for row in rows)
    for decision, count in sorted(decisions.items()):
        lines.append(f"- {decision}: {count}")
    lines.extend(
        [
            f"- Stored live-call records: {sum(bool(row['used_live_llm']) for row in rows)}",
            f"- Stored fallback records: {sum(bool(row['used_fallback']) for row in rows)}",
            (
                "- Live calls finalized with deterministic schema-safe repair: "
                f"{sum(bool(row['schema_safe_repair_used']) for row in rows)}"
            ),
            (
                "- Live model content retained in finalized scenario: "
                f"{sum(bool(row['live_model_content_retained']) for row in rows)}"
            ),
            "",
            "The zero fallback count is not equivalent to unmodified live-model content. "
            "Schema-safe repairs are therefore reported separately.",
            "",
            "## Five matched cases",
            "",
        ]
    )
    for case in five_cases:
        lines.append(
            f"- {case['case_id']} / {case['model_key']}: "
            f"{case['selection_type']} — {case['selection_reason']}"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            (
                "The component metrics are the primary scientific results. OCI_eq only "
                "summarizes the five legacy components under equal nominal weights because "
                "no empirically validated differential weighting model is available. "
                "Neither the component diagnostics nor OCI_eq establish learner gains, "
                "expert-rated realism, or universal scenario quality."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def validate_input_design(records: Sequence[ScenarioRecord]) -> Dict[str, Any]:
    keys: List[Tuple[str, str, str]] = []
    cases: set[str] = set()
    models: set[str] = set()
    methods: set[str] = set()
    fallback = 0
    live = 0
    for record in records:
        raw = record.raw
        scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
        case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
        method = infer_method(raw, scenario)
        case_id = str(case.get("case_id", ""))
        model_key = str(raw.get("llm_key", ""))
        keys.append((case_id, model_key, method))
        cases.add(case_id)
        models.add(model_key)
        methods.add(method)
        fallback += int(bool(raw.get("used_fallback")))
        live += int(bool(raw.get("used_live_llm")))
    counts = Counter(keys)
    duplicates = [key for key, count in counts.items() if count > 1]
    missing = [
        (case_id, model_key, method)
        for case_id in sorted(cases)
        for model_key in sorted(models)
        for method in METHOD_ORDER
        if (case_id, model_key, method) not in counts
    ]
    checks = {
        "record_count": len(records),
        "case_count": len(cases),
        "model_count": len(models),
        "condition_count": len(methods),
        "live_record_count": live,
        "fallback_record_count": fallback,
        "duplicate_key_count": len(duplicates),
        "missing_key_count": len(missing),
        "duplicate_keys": ["|".join(key) for key in duplicates],
        "missing_keys": ["|".join(key) for key in missing],
    }
    expected = {
        "record_count": EXPECTED_RECORDS,
        "case_count": EXPECTED_CASES,
        "model_count": EXPECTED_MODELS,
        "condition_count": EXPECTED_CONDITIONS,
        "live_record_count": EXPECTED_RECORDS,
        "fallback_record_count": 0,
        "duplicate_key_count": 0,
        "missing_key_count": 0,
    }
    failures = [
        f"{key}: observed={checks[key]} expected={value}"
        for key, value in expected.items()
        if checks[key] != value
    ]
    if failures:
        raise RuntimeError("Frozen design verification failed: " + "; ".join(failures))
    return checks


def run_evaluation(
    *,
    input_root: Path,
    ontology_path: Path,
    dataset_catalog_path: Path,
    corpus_root: Path,
    output_dir: Path,
    sensitivity_draws: int,
    sensitivity_seed: int,
) -> Dict[str, Any]:
    input_files = sorted(
        path
        for path in input_root.glob("*.jsonl")
        if "paper_120_live_recovered" in path.name
    )
    if len(input_files) != 12:
        raise FileNotFoundError(
            f"Expected 12 frozen JSONL files under {input_root}; found {len(input_files)}."
        )
    records = load_jsonl_records(input_files, dedupe=False)
    design_checks = validate_input_design(records)
    registry = CanonicalTraceRegistry(ontology_path, dataset_catalog_path, corpus_root)
    output_dir.mkdir(parents=True, exist_ok=False)

    export_rows, working_rows = build_component_rows(records, registry)
    method_summary = summarize_methods(working_rows)
    model_summary = summarize_models(working_rows)
    sensitivity_rows, sensitivity_summary = sensitivity_analysis(
        working_rows,
        draws=sensitivity_draws,
        seed=sensitivity_seed,
    )
    five_cases = select_five_matched_cases(working_rows)

    _write_csv(output_dir / "component_metrics_by_output.csv", export_rows)
    _write_csv(output_dir / "method_summary.csv", method_summary)
    _write_csv(output_dir / "model_summary.csv", model_summary)
    _write_csv(output_dir / "oci_weight_sensitivity.csv", sensitivity_rows)

    trace_failures = [
        row
        for row in export_rows
        if (
            _json_list(row.get("missing_trace_ids"))
            or _json_list(row.get("wrong_target_trace_ids"))
            or _json_list(row.get("duplicate_or_conflicting_trace_ids"))
        )
    ]
    trace_summary = {
        "applicable_output_count": sum(
            bool(row["traceability_applicable"]) for row in export_rows
        ),
        "not_applicable_output_count": sum(
            not bool(row["traceability_applicable"]) for row in export_rows
        ),
        "unresolved_output_count": sum(
            bool(
                _json_list(row.get("missing_trace_ids"))
                or _json_list(row.get("wrong_target_trace_ids"))
            )
            for row in export_rows
        ),
        "any_diagnostic_output_count": len(trace_failures),
        "missing_link_count": sum(
            len(_json_list(row.get("missing_trace_ids"))) for row in export_rows
        ),
        "wrong_target_link_count": sum(
            len(_json_list(row.get("wrong_target_trace_ids"))) for row in export_rows
        ),
        "duplicate_or_conflicting_link_count": sum(
            len(_json_list(row.get("duplicate_or_conflicting_trace_ids")))
            for row in export_rows
        ),
    }
    trace_failure_fields = list(export_rows[0]) if export_rows else []
    _write_csv(
        output_dir / "provenance_trace_failures.csv",
        trace_failures,
        fieldnames=trace_failure_fields,
    )
    (output_dir / "five_matched_cases.json").write_text(
        json.dumps(five_cases, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_five_case_markdown(output_dir / "five_matched_cases.md", five_cases)
    (output_dir / "weight_sensitivity_summary.json").write_text(
        json.dumps(sensitivity_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = build_report(
        method_summary=method_summary,
        model_summary=model_summary,
        sensitivity=sensitivity_summary,
        rows=working_rows,
        five_cases=five_cases,
    )
    (output_dir / "evaluation_repair_report.md").write_text(report, encoding="utf-8")

    input_hashes = {str(path.resolve()): _sha256(path) for path in input_files}
    input_hashes[str(ontology_path.resolve())] = _sha256(ontology_path)
    input_hashes[str(dataset_catalog_path.resolve())] = _sha256(dataset_catalog_path)
    output_hashes = {
        path.name: _sha256(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "run_manifest.json"
    }
    manifest = {
        "run_id": output_dir.parent.name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "targeted_repair_existing_outputs_only",
        "generation_model_calls": 0,
        "frozen_experiment_note": (
            "Uses the manuscript's paper120_live_recovered_final condition files. "
            "The later Graph-Walk v1 mode-4 ablation is a separate experiment and is not "
            "silently substituted into this protected frozen design."
        ),
        "input_root": str(input_root.resolve()),
        "ontology_path": str(ontology_path.resolve()),
        "dataset_catalog_path": str(dataset_catalog_path.resolve()),
        "corpus_root": str(corpus_root.resolve()),
        "output_dir": str(output_dir.resolve()),
        "design_checks": design_checks,
        "metric_configuration": {
            "primary_components": [
                "json_validity_J",
                "schema_completeness",
                "control_adherence_A",
                "method_conditioned_precision_recall_f1_req",
                "provenance_field_completeness_G",
                "canonical_traceability_T",
                "contradiction_rate_E",
                "ontology_scope",
                "existing_diversity_diagnostics",
            ],
            "oci_equal_weight": EQUAL_WEIGHTS,
            "oci_equal_weight_status": (
                "secondary_descriptive_not_calibrated_not_quality_percentage_"
                "not_threshold_not_learner_effect"
            ),
            "oci_legacy_sensitivity_only": LEGACY_WEIGHTS,
            "claim_source_support": CLAIM_SOURCE_SUPPORT_STATUS,
            "traceability_empty_contract_policy": (
                "null_not_applicable_when_method_declares_no_trace_links"
            ),
        },
        "sensitivity": {
            "draws": sensitivity_draws,
            "seed": sensitivity_seed,
            "distribution": sensitivity_summary["distribution"],
        },
        "traceability_summary": trace_summary,
        "software": {
            "python": sys.version,
            "platform": platform.platform(),
            "implementation": platform.python_implementation(),
        },
        "input_sha256": input_hashes,
        "output_sha256_excluding_manifest": output_hashes,
        "selected_five_cases": [
            {
                "selection_type": case["selection_type"],
                "case_id": case["case_id"],
                "model_key": case["model_key"],
                "selection_reason": case["selection_reason"],
            }
            for case in five_cases
        ],
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "manifest": manifest,
        "method_summary": method_summary,
        "model_summary": model_summary,
        "sensitivity_summary": sensitivity_summary,
        "five_cases": five_cases,
        "trace_failure_count": len(trace_failures),
    }


def _group_by(
    rows: Sequence[Mapping[str, Any]],
    key: str,
) -> Dict[str, List[Mapping[str, Any]]]:
    output: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        output[str(row[key])].append(row)
    return output


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot calculate a quantile for an empty sequence.")
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def _sign(value: float, tolerance: float = 1e-12) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _dataset_stem_from_source_file(source_file: str) -> str:
    stem = Path(source_file).stem
    if stem.lower().startswith("auto_"):
        stem = stem[5:]
    return DATASET_SUFFIX_RE.sub("", stem)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fieldnames: Optional[Sequence[str]] = None,
) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _json_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return _semicolon_list(stripped)
        return [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]
    return []


def _semicolon_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [part.strip() for part in value.split(";") if part.strip()]
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reevaluate the frozen PSQ-SCO 1,440-output experiment without generation calls."
    )
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY_PATH)
    parser.add_argument("--dataset-catalog", type=Path, default=DEFAULT_DATASET_CATALOG)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sensitivity-draws", type=int, default=SENSITIVITY_DRAWS)
    parser.add_argument("--sensitivity-seed", type=int, default=SENSITIVITY_SEED)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_evaluation(
        input_root=args.input_root,
        ontology_path=args.ontology,
        dataset_catalog_path=args.dataset_catalog,
        corpus_root=args.corpus_root,
        output_dir=args.out_dir,
        sensitivity_draws=args.sensitivity_draws,
        sensitivity_seed=args.sensitivity_seed,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.out_dir.resolve()),
                "record_count": result["manifest"]["design_checks"]["record_count"],
                "trace_failure_count": result["trace_failure_count"],
                "oci_equal_weight": {
                    row["method"]: row["oci_equal_weight_secondary"]
                    for row in result["method_summary"]
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
