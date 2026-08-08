"""Audit source-to-scenario linkage without inventing unsupported similarity scores."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .models import METHOD_CONDITION_NUMBERS, METHOD_LABELS, METHOD_ORDER, ScenarioRecord
from .scenario_checks import infer_method


SCORE_FIELDS = ("similarity", "distance", "retrieval_score", "score")
SOURCE_ID_FIELDS = ("source_record_id", "doc_id", "id", "source_id", "source_file")
CONTEXT_EXTERNAL = "external_vector_context"
CONTEXT_ONTOLOGY_TEXT = "ontology_text_context"
CONTEXT_STRUCTURED_ONTOLOGY = "structured_ontology_source"


def source_linkage_audit(records: Iterable[ScenarioRecord]) -> List[Dict[str, Any]]:
    """Return one row per scenario describing source evidence and estimability."""

    rows: List[Dict[str, Any]] = []
    for record in records:
        raw = record.raw or {}
        scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
        case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
        method = infer_method(raw, scenario)
        items = _context_items(raw, scenario)
        external = [item for item in items if _context_kind(item) == CONTEXT_EXTERNAL]
        ontology_text = [item for item in items if _context_kind(item) == CONTEXT_ONTOLOGY_TEXT]
        structured_ontology = [
            item for item in items if _context_kind(item) == CONTEXT_STRUCTURED_ONTOLOGY
        ]
        graph_walk = [item for item in ontology_text if _is_graph_walk_item(item)]
        graph_walk_required = _graph_walk_required(raw, scenario, graph_walk)
        ontology = [*ontology_text, *structured_ontology]
        source_ids = [_source_id(item) for item in items]
        source_ids = [value for value in source_ids if value]
        scored = [item for item in items if any(item.get(field) is not None for field in SCORE_FIELDS)]
        exact_ids = [item for item in items if _source_id(item)]
        retrieval_query = _retrieval_query(raw, scenario, items)
        claim_map = _claim_source_map(raw, scenario)

        if not items:
            linkage_status = "NO_RETRIEVED_CONTEXT_EXPORTED"
        elif claim_map:
            linkage_status = "CLAIM_LEVEL_SOURCE_MAPPING_AVAILABLE"
        elif exact_ids:
            linkage_status = "SCENARIO_TO_CONTEXT_SET_ONLY"
        else:
            linkage_status = "CONTEXT_PRESENT_WITHOUT_STABLE_SOURCE_ID"

        if not items:
            similarity_status = "NOT_APPLICABLE_NO_RETRIEVED_CONTEXT"
        elif retrieval_query and len(scored) == len(items):
            similarity_status = "RAW_RETRIEVAL_SCORE_AVAILABLE_NOT_A_SOURCE_FAITHFULNESS_SCORE"
        else:
            similarity_status = "NOT_ESTIMABLE_FROM_FROZEN_EXPORT"

        full_treatment_exposure, exposure_reason = _full_treatment_exposure(
            method,
            external_count=len(external),
            ontology_text_count=len(ontology_text),
            structured_ontology_count=len(structured_ontology),
            graph_walk_count=len(graph_walk),
            graph_walk_required=graph_walk_required,
        )

        rows.append(
            {
                "source_file": record.source_file,
                "line_number": record.line_number,
                "case_id": case.get("case_id") or raw.get("result_key") or "",
                "scenario_id": scenario.get("scenario_id", ""),
                "model_key": raw.get("llm_key") or raw.get("model", {}).get("key", ""),
                "method": method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
                "condition_name": METHOD_LABELS.get(method, method),
                "retrieved_context_count": len(items),
                "external_context_count": len(external),
                "external_vector_context_count": len(external),
                "ontology_context_count": len(ontology),
                "ontology_text_context_count": len(ontology_text),
                "structured_ontology_source_count": len(structured_ontology),
                "graph_walk_required": graph_walk_required,
                "graph_walk_context_count": len(graph_walk),
                "graph_walk_exposure_verified": bool(graph_walk_required and graph_walk),
                "graph_walk_strategy_labels": "; ".join(
                    _dedupe(str(item.get("graph_text_strategy", "")) for item in graph_walk)
                ),
                "full_nominal_treatment_exposure": full_treatment_exposure,
                "treatment_exposure_reason": exposure_reason,
                "stable_source_id_count": len(exact_ids),
                "retrieval_score_count": len(scored),
                "retrieval_query_exported": bool(retrieval_query),
                "claim_source_map_exported": bool(claim_map),
                "source_linkage_status": linkage_status,
                "source_similarity_status": similarity_status,
                "source_mapping_unit": "one scenario to an ordered context set; not necessarily one scenario to one document",
                "source_role_separation": (
                    "external vector context, ontology-text context, and structured ontology source are counted separately"
                ),
                "source_ids": "; ".join(_dedupe(source_ids)),
            }
        )
    return rows


def source_linkage_summary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Summarize linkage coverage and source-similarity estimability by condition."""

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("method", ""))].append(row)

    summaries: List[Dict[str, Any]] = []
    for method in METHOD_ORDER:
        group = grouped.get(method, [])
        if not group:
            continue
        n = len(group)
        graph_walk_required_n = _count(group, lambda row: bool(row.get("graph_walk_required")))
        graph_walk_verified_n = _count(
            group, lambda row: bool(row.get("graph_walk_exposure_verified"))
        )
        summaries.append(
            {
                "method": method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
                "condition_name": METHOD_LABELS.get(method, method),
                "n": n,
                "rows_with_context": _count(group, lambda row: int(row.get("retrieved_context_count") or 0) > 0),
                "rows_with_external_context": _count(group, lambda row: int(row.get("external_context_count") or 0) > 0),
                "rows_with_external_vector_context": _count(
                    group, lambda row: int(row.get("external_vector_context_count") or 0) > 0
                ),
                "rows_with_ontology_context": _count(group, lambda row: int(row.get("ontology_context_count") or 0) > 0),
                "rows_with_ontology_text_context": _count(
                    group, lambda row: int(row.get("ontology_text_context_count") or 0) > 0
                ),
                "rows_with_structured_ontology_source": _count(
                    group, lambda row: int(row.get("structured_ontology_source_count") or 0) > 0
                ),
                "rows_requiring_graph_walk": graph_walk_required_n,
                "rows_with_graph_walk_context": _count(
                    group, lambda row: int(row.get("graph_walk_context_count") or 0) > 0
                ),
                "rows_with_verified_graph_walk_exposure": graph_walk_verified_n,
                "graph_walk_exposure_rate": (
                    graph_walk_verified_n / graph_walk_required_n
                    if graph_walk_required_n
                    else None
                ),
                "rows_with_full_nominal_treatment_exposure": _count(
                    group, lambda row: bool(row.get("full_nominal_treatment_exposure"))
                ),
                "full_nominal_treatment_exposure_rate": (
                    _count(group, lambda row: bool(row.get("full_nominal_treatment_exposure"))) / n
                    if n
                    else 0.0
                ),
                "rows_with_stable_source_id": _count(group, lambda row: int(row.get("stable_source_id_count") or 0) > 0),
                "rows_with_retrieval_score": _count(group, lambda row: int(row.get("retrieval_score_count") or 0) > 0),
                "rows_with_exported_query": _count(group, lambda row: bool(row.get("retrieval_query_exported"))),
                "rows_with_claim_source_map": _count(group, lambda row: bool(row.get("claim_source_map_exported"))),
                "rows_similarity_not_estimable": _count(
                    group,
                    lambda row: str(row.get("source_similarity_status", "")).startswith("NOT_ESTIMABLE"),
                ),
                "interpretation": (
                    "Source identifiers show which context set was attached to a scenario. They do not establish "
                    "query relevance, claim support, or source faithfulness without qrels and claim-level mapping."
                ),
            }
        )
    return summaries


def _context_items(raw: Dict[str, Any], scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    prompt_contexts = [item for item in raw.get("rag_examples") or [] if isinstance(item, dict)]
    meta = scenario.get("generation_meta") if isinstance(scenario.get("generation_meta"), dict) else {}
    if not prompt_contexts:
        prompt_contexts = [item for item in meta.get("rag_trace") or [] if isinstance(item, dict)]
    for item in prompt_contexts:
        candidates.append(_tag_context(item, _inferred_prompt_context_kind(item)))

    packet = raw.get("semantic_packet") or scenario.get("generation_meta", {}).get("ontology_trace") or {}
    if isinstance(packet, dict):
        for item in packet.get("evidence_sources") or []:
            if isinstance(item, dict):
                candidates.append(_tag_context(item, CONTEXT_STRUCTURED_ONTOLOGY))

    # The full ontology_text_trace duplicates the compact prompt contexts in
    # current exports. Use it only when no ontology-text prompt item survived
    # into rag_examples/rag_trace, otherwise context counts are inflated.
    text_trace = meta.get("ontology_text_trace") if isinstance(meta.get("ontology_text_trace"), dict) else {}
    if not any(_context_kind(item) == CONTEXT_ONTOLOGY_TEXT for item in candidates):
        for item in text_trace.get("documents") or []:
            if isinstance(item, dict):
                candidates.append(_tag_context(item, CONTEXT_ONTOLOGY_TEXT))

    return _dedupe_items(candidates)


def _retrieval_query(
    raw: Dict[str, Any],
    scenario: Dict[str, Any],
    context_items: Sequence[Dict[str, Any]] = (),
) -> str:
    meta = raw.get("prompt_metadata") if isinstance(raw.get("prompt_metadata"), dict) else {}
    scenario_meta = scenario.get("generation_meta") if isinstance(scenario.get("generation_meta"), dict) else {}
    nested = scenario_meta.get("prompt_metadata") if isinstance(scenario_meta.get("prompt_metadata"), dict) else {}
    for payload in (raw, meta, nested):
        for key in ("retrieval_query", "rag_query", "query_text"):
            if payload.get(key):
                return str(payload[key])
    for item in context_items:
        if item.get("retrieval_query"):
            return str(item["retrieval_query"])
    return ""


def _claim_source_map(raw: Dict[str, Any], scenario: Dict[str, Any]) -> List[Any]:
    meta = scenario.get("generation_meta") if isinstance(scenario.get("generation_meta"), dict) else {}
    for payload in (raw, scenario, meta):
        value = payload.get("claim_source_map")
        if isinstance(value, list) and value:
            return value
    return []


def _context_kind(item: Dict[str, Any]) -> str:
    tagged = str(item.get("_psq_context_kind", ""))
    if tagged in {CONTEXT_EXTERNAL, CONTEXT_ONTOLOGY_TEXT, CONTEXT_STRUCTURED_ONTOLOGY}:
        return tagged
    return _inferred_prompt_context_kind(item)


def _inferred_prompt_context_kind(item: Dict[str, Any]) -> str:
    """Classify context using explicit provenance markers, not generic fields.

    External datasets can legitimately carry ``document_type`` metadata, so
    that field alone is not evidence that an item came from PSQ-SCO.
    """

    retrieval_tier = str(item.get("retrieval_tier", "")).lower()
    corpus_mode = str(item.get("corpus_mode", "")).lower()
    source_dataset = str(item.get("source_dataset", "")).lower()
    source_file = str(item.get("source_file", ""))
    doc_id = str(item.get("doc_id", ""))
    if (
        retrieval_tier == "ontology_text_rag"
        or corpus_mode == "ontology_text"
        or "personashield-psq-sco" in source_dataset
        or source_file.startswith("PSQ-SCO-v9.1::")
        or bool(item.get("ontology_ids"))
        or doc_id.startswith(("ontology_record_", "graph_cot_", "ontology_walk_"))
    ):
        return CONTEXT_ONTOLOGY_TEXT
    return CONTEXT_EXTERNAL


def _tag_context(item: Dict[str, Any], kind: str) -> Dict[str, Any]:
    tagged = dict(item)
    tagged["_psq_context_kind"] = kind
    return tagged


def _full_treatment_exposure(
    method: str,
    *,
    external_count: int,
    ontology_text_count: int,
    structured_ontology_count: int,
    graph_walk_count: int = 0,
    graph_walk_required: bool = False,
) -> Tuple[bool, str]:
    if method == "prompt_only":
        passed = external_count == 0 and ontology_text_count == 0 and structured_ontology_count == 0
        return passed, "no retrieval or ontology context expected"
    if method == "prompt_rag":
        return external_count > 0, "at least one external vector-retrieved context required"
    if method == "ontology_prompt_rag":
        passed = external_count > 0 and structured_ontology_count > 0
        return passed, "external vector context plus structured ontology source required"
    if method == "ontology_text_rag":
        passed = external_count > 0 and ontology_text_count > 0
        reason = "external vector context plus ontology-text context required"
        if graph_walk_required:
            passed = passed and graph_walk_count > 0
            reason += "; selected-subgraph graph-walk context also required by this experiment variant"
        return passed, reason
    return False, "unknown condition"


def _is_graph_walk_item(item: Dict[str, Any]) -> bool:
    document_type = str(item.get("document_type", "")).lower()
    strategy = str(item.get("graph_text_strategy", "")).lower()
    source_file = str(item.get("source_file", "")).lower()
    doc_id = str(item.get("doc_id", "")).lower()
    return (
        document_type == "selected_subgraph_walk"
        or "deterministic_random_walk_graph_to_text" in strategy
        or "deterministic_greedy" in strategy
        or "::ontology_walk_" in source_file
        or doc_id.startswith("ontology_walk_")
    )


def _graph_walk_required(
    raw: Dict[str, Any],
    scenario: Dict[str, Any],
    graph_walk_items: Sequence[Dict[str, Any]] = (),
) -> bool:
    if graph_walk_items:
        return True
    scenario_meta = (
        scenario.get("generation_meta")
        if isinstance(scenario.get("generation_meta"), dict)
        else {}
    )
    nested_prompt = (
        scenario_meta.get("prompt_metadata")
        if isinstance(scenario_meta.get("prompt_metadata"), dict)
        else {}
    )
    raw_prompt = raw.get("prompt_metadata") if isinstance(raw.get("prompt_metadata"), dict) else {}
    for prompt in (raw_prompt, nested_prompt):
        document_types = {
            str(value).lower() for value in (prompt.get("ontology_text_document_types") or [])
        }
        strategies = {
            str(value).lower() for value in (prompt.get("ontology_text_graph_strategy") or [])
        }
        if "selected_subgraph_walk" in document_types:
            return True
        if any(
            "deterministic_random_walk_graph_to_text" in value
            or "deterministic_greedy" in value
            for value in strategies
        ):
            return True
    return False


def _source_id(item: Dict[str, Any]) -> str:
    for field in SOURCE_ID_FIELDS:
        value = item.get(field)
        if value:
            return str(value)
    return ""


def _dedupe_items(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        stable_id = _source_id(item)
        if stable_id:
            key: Tuple[str, str] = ("id", stable_id)
        else:
            encoded = json.dumps(item, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")
            key = ("sha256", hashlib.sha256(encoded).hexdigest())
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _dedupe(values: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _count(rows: Sequence[Dict[str, Any]], predicate: Any) -> int:
    return sum(1 for row in rows if predicate(row))
