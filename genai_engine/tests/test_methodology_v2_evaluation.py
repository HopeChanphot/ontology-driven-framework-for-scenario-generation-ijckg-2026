import csv
import json
import tempfile
import unittest
from pathlib import Path

from three_layer_evaluation.models import METHOD_LABELS, ScenarioRecord
from three_layer_evaluation.comparison import _cochran_q_optional, _friedman_optional
from three_layer_evaluation.cli import _load_reusable_semantic_diversity
from three_layer_evaluation.scenario_checks import (
    common_case_concept_score,
    control_adherence_score,
    generation_integrity,
    game_schema_completeness_score,
)
from three_layer_evaluation.source_linkage import source_linkage_audit, source_linkage_summary
from three_layer_evaluation.standard_metrics import metric_validity_registry
from three_layer_evaluation.technical_decisions import (
    ACCEPTED,
    MAJOR_REVISION,
    MINOR_REVISION,
    REJECT_REGENERATE,
    determine_technical_decision,
)


class MethodologyV2EvaluationTests(unittest.TestCase):
    def test_condition_names_are_exact_and_stable(self):
        self.assertEqual(METHOD_LABELS["prompt_only"], "Prompt-Only Generation")
        self.assertEqual(METHOD_LABELS["prompt_rag"], "Text-RAG Generation")
        self.assertEqual(
            METHOD_LABELS["ontology_prompt_rag"],
            "Ontology-Derived Structured Prompting RAG",
        )
        self.assertEqual(METHOD_LABELS["ontology_text_rag"], "Ontology-to-Text Vector RAG")

    def test_four_state_non_compensatory_decision_policy(self):
        accepted = determine_technical_decision(
            json_parse_pass=True,
            game_schema_missing=(),
            failed_controls=(),
            common_case_concepts_missing=(),
            contradiction_reasons=(),
        )
        minor = determine_technical_decision(
            json_parse_pass=True,
            game_schema_missing=(),
            failed_controls=("role",),
            common_case_concepts_missing=(),
            contradiction_reasons=(),
        )
        major = determine_technical_decision(
            json_parse_pass=True,
            game_schema_missing=(),
            failed_controls=("channel",),
            common_case_concepts_missing=(),
            contradiction_reasons=(),
        )
        rejected = determine_technical_decision(
            json_parse_pass=True,
            game_schema_missing=(),
            failed_controls=(),
            common_case_concepts_missing=(),
            contradiction_reasons=("unsafe_correct_action",),
        )
        self.assertEqual(accepted.decision, ACCEPTED)
        self.assertEqual(minor.decision, MINOR_REVISION)
        self.assertEqual(major.decision, MAJOR_REVISION)
        self.assertEqual(rejected.decision, REJECT_REGENERATE)
        self.assertTrue(accepted.final_human_review_required)

    def test_game_schema_excludes_provenance_fields(self):
        scenario = {
            "scenario_id": "s-1",
            "channel": "sms",
            "variant": "fake",
            "game_choices": [{"label": "Report"}],
            "correct_action": "Pause and verify through an approved channel.",
            "difficulty": {"band": "easy"},
            "red_flags": ["Urgent link"],
        }
        score, missing = game_schema_completeness_score(scenario)
        self.assertEqual(score, 1.0)
        self.assertEqual(missing, [])

    def test_safe_response_uses_correct_choice_and_verification_synonyms(self):
        scenario = {
            "role": "HR",
            "age_group_code": "22_35",
            "stage_id": "BEGINNER_INTRODUCTORY",
            "channel": "email",
            "variant": "real",
            "difficulty_band": "easy",
            "attack_type": "legitimate",
            "correct_action": "Check the HRIS portal for the leave request.",
            "safe_indicators": ["The request appears in the approved HRIS workflow."],
            "game_choices": [
                {
                    "label": "Verify through the HRIS portal.",
                    "is_correct": True,
                    "outcome": "safe",
                    "feedback": "Use the approved process.",
                }
            ],
        }
        case = {
            key: scenario[key]
            for key in (
                "role",
                "age_group_code",
                "stage_id",
                "channel",
                "variant",
                "difficulty_band",
            )
        }
        score, failed = control_adherence_score(scenario, case)
        self.assertEqual(score, 1.0)
        self.assertEqual(failed, [])
        precision, recall, f1, _matched, missing = common_case_concept_score(scenario, case)
        self.assertEqual((precision, recall, f1), (1.0, 1.0, 1.0))
        self.assertEqual(missing, [])

    def test_source_similarity_is_not_invented_without_query_and_scores(self):
        record = ScenarioRecord(
            source_file="f.jsonl",
            line_number=1,
            raw={
                "llm_key": "qwen2_5_7b",
                "mode": "prompt_rag",
                "case": {"case_id": "c-1"},
                "rag_examples": [{"source_record_id": "doc-1", "text": "example"}],
                "scenario": {"scenario_id": "s-1"},
            },
        )
        row = source_linkage_audit([record])[0]
        self.assertEqual(row["source_linkage_status"], "SCENARIO_TO_CONTEXT_SET_ONLY")
        self.assertEqual(row["source_similarity_status"], "NOT_ESTIMABLE_FROM_FROZEN_EXPORT")
        self.assertIn("ordered context set", row["source_mapping_unit"])
        summary = source_linkage_summary([row])[0]
        self.assertEqual(summary["rows_similarity_not_estimable"], 1)

    def test_retrieval_score_is_not_mislabeled_as_faithfulness(self):
        record = ScenarioRecord(
            source_file="f.jsonl",
            line_number=1,
            raw={
                "llm_key": "qwen2_5_7b",
                "mode": "prompt_rag",
                "case": {"case_id": "c-1"},
                "retrieval_query": "sms fake IT",
                "rag_examples": [
                    {"source_record_id": "doc-1", "distance": 0.2, "text": "example"}
                ],
                "scenario": {"scenario_id": "s-1"},
            },
        )
        row = source_linkage_audit([record])[0]
        self.assertEqual(
            row["source_similarity_status"],
            "RAW_RETRIEVAL_SCORE_AVAILABLE_NOT_A_SOURCE_FAITHFULNESS_SCORE",
        )

    def test_source_audit_separates_external_and_ontology_context_without_duplicates(self):
        external = {
            "source_file": "external.jsonl",
            "source_dataset": "dataset_external",
            "document_type": "email",
            "retrieval_tier": "strict",
        }
        ontology = {
            "source_file": "PSQ-SCO-v9.1::ontology_record_TPL_SMS",
            "source_dataset": "personashield-psq-sco-v9.1.owl",
            "retrieval_tier": "ontology_text_rag",
            "document_type": "scenario_template",
            "ontology_ids": ["TPL_SMS"],
        }
        record = ScenarioRecord(
            source_file="f.jsonl",
            line_number=1,
            raw={
                "llm_key": "qwen2_5_7b",
                "mode": "ontology_text_rag",
                "case": {"case_id": "c-1"},
                "rag_examples": [external, ontology],
                "scenario": {
                    "scenario_id": "s-1",
                    "generation_meta": {
                        "ontology_text_trace": {
                            "documents": [
                                {
                                    "doc_id": "ontology_record_TPL_SMS",
                                    "document_type": "scenario_template",
                                }
                            ]
                        }
                    },
                },
            },
        )
        row = source_linkage_audit([record])[0]
        self.assertEqual(row["retrieved_context_count"], 2)
        self.assertEqual(row["external_vector_context_count"], 1)
        self.assertEqual(row["ontology_text_context_count"], 1)
        self.assertTrue(row["full_nominal_treatment_exposure"])

    def test_source_audit_reports_incomplete_nominal_rag_exposure(self):
        record = ScenarioRecord(
            source_file="f.jsonl",
            line_number=1,
            raw={
                "llm_key": "mistral_7b",
                "mode": "prompt_rag",
                "case": {"case_id": "c-1"},
                "rag_examples": [],
                "scenario": {"scenario_id": "s-1"},
            },
        )
        row = source_linkage_audit([record])[0]
        self.assertFalse(row["full_nominal_treatment_exposure"])

    def test_graph_walk_exposure_is_a_separate_condition4_audit(self):
        record = ScenarioRecord(
            source_file="graph-walk.jsonl",
            line_number=1,
            raw={
                "llm_key": "qwen3_8b",
                "mode": "ontology_text_rag",
                "case": {"case_id": "PSQ-SCO-120-001"},
                "prompt_metadata": {
                    "external_rag_example_count": 1,
                    "ontology_text_document_types": [
                        "scenario_template",
                        "validation_rule",
                        "evidence_source",
                        "graph_cot_trace",
                        "selected_subgraph_walk",
                    ],
                    "ontology_text_graph_strategy": [
                        "deterministic_random_walk_graph_to_text"
                    ],
                },
                "rag_examples": [
                    {"source_file": "external.jsonl", "corpus_mode": "ENGLISH_GLOBAL"},
                    {
                        "source_file": "PSQ-SCO-v9.1::ontology_record_TPL_SMS",
                        "corpus_mode": "ontology_text",
                        "document_type": "scenario_template",
                    },
                    {
                        "source_file": "PSQ-SCO-v9.1::ontology_walk_sms_fake_IT",
                        "corpus_mode": "ontology_text",
                        "document_type": "selected_subgraph_walk",
                        "graph_text_strategy": "deterministic_random_walk_graph_to_text",
                    },
                ],
                "scenario": {"scenario_id": "s-1"},
            },
        )
        row = source_linkage_audit([record])[0]
        self.assertTrue(row["graph_walk_required"])
        self.assertEqual(row["graph_walk_context_count"], 1)
        self.assertTrue(row["graph_walk_exposure_verified"])
        self.assertTrue(row["full_nominal_treatment_exposure"])
        summary = source_linkage_summary([row])[0]
        self.assertEqual(summary["rows_requiring_graph_walk"], 1)
        self.assertEqual(summary["graph_walk_exposure_rate"], 1.0)

    def test_graph_walk_does_not_hide_missing_external_rag_treatment(self):
        record = ScenarioRecord(
            source_file="graph-walk.jsonl",
            line_number=1,
            raw={
                "llm_key": "mistral_7b",
                "mode": "ontology_text_rag",
                "case": {"case_id": "PSQ-SCO-120-001"},
                "rag_examples": [
                    {
                        "source_file": "PSQ-SCO-v9.1::ontology_walk_sms_fake_IT",
                        "corpus_mode": "ontology_text",
                        "document_type": "selected_subgraph_walk",
                    }
                ],
                "scenario": {"scenario_id": "s-1"},
            },
        )
        row = source_linkage_audit([record])[0]
        self.assertTrue(row["graph_walk_exposure_verified"])
        self.assertFalse(row["full_nominal_treatment_exposure"])

    def test_generation_integrity_separates_live_call_from_schema_safe_repair(self):
        repaired = generation_integrity(
            {"used_live_llm": True, "used_fallback": False},
            {
                "llm_source": "offline_fallback",
                "generation_meta": {
                    "repair_note": "LLM output could not be repaired; schema-safe fallback used."
                },
            },
        )
        self.assertTrue(repaired["schema_safe_repair_used"])
        self.assertFalse(repaired["live_model_content_retained"])
        self.assertEqual(
            repaired["generation_integrity_status"],
            "LIVE_CALL_SCHEMA_SAFE_REPAIR",
        )
        retained = generation_integrity(
            {"used_live_llm": True, "used_fallback": False},
            {"llm_source": "qwen3_8b:ollama"},
        )
        self.assertTrue(retained["live_model_content_retained"])

    def test_every_metric_has_complete_operational_definition(self):
        required = {
            "formal_input",
            "formal_output",
            "threshold",
            "workflow_layer",
            "calculation_time",
            "frequency",
            "metric_role",
        }
        rows = metric_validity_registry()
        self.assertGreaterEqual(len(rows), 13)
        for row in rows:
            self.assertTrue(required.issubset(row))
            for key in required:
                self.assertTrue(str(row[key]).strip(), f"{row['metric']} missing {key}")

    def test_degenerate_friedman_is_reported_without_nan(self):
        result = _friedman_optional([[0.5, 0.5, 0.5, 0.5] for _ in range(5)])
        self.assertEqual(result["status"], "not_run_all_blocks_tied")
        self.assertEqual(result["p_value"], 1.0)

    def test_cochran_q_has_no_statsmodels_dependency(self):
        result = _cochran_q_optional(
            [
                [1, 1, 1, 0],
                [1, 1, 1, 1],
                [1, 1, 1, 1],
                [1, 1, 1, 1],
            ]
        )
        self.assertEqual(result["status"], "completed_asymptotic")
        self.assertIsNotNone(result["p_value"])

    def test_diversity_reuse_requires_and_accepts_identical_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scenario_file = root / "scenarios.jsonl"
            scenario_file.write_text("{}\n", encoding="utf-8")
            (root / "run_metadata.json").write_text(
                json.dumps(
                    {
                        "scenario_files": [str(scenario_file)],
                        "diversity_embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
                    }
                ),
                encoding="utf-8",
            )
            with (root / "semantic_diversity.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["model_key", "method", "n", "embedding_diversity"])
                writer.writeheader()
                for model in ("mistral", "qwen25", "qwen3"):
                    for method in ("prompt_only", "prompt_rag", "ontology_prompt_rag", "ontology_text_rag"):
                        writer.writerow(
                            {
                                "model_key": model,
                                "method": method,
                                "n": 120,
                                "embedding_diversity": 0.3,
                            }
                        )
            rows = _load_reusable_semantic_diversity(
                root,
                scenario_files=[scenario_file],
                expected_embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            )
        self.assertEqual(len(rows), 12)
        self.assertEqual(sum(row["n"] for row in rows), 1440)


if __name__ == "__main__":
    unittest.main()
