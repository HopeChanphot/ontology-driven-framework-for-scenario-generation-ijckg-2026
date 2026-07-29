import tempfile
import unittest
from pathlib import Path

from three_layer_evaluation.comparison import (
    error_analysis,
    method_summary,
    paired_statistics,
    paper_labeled_error_analysis,
    rank_biserial_from_differences,
    sign_dominance_from_differences,
)
from three_layer_evaluation.models import OntologyValidationResult, ScenarioScore
from three_layer_evaluation.ontology_checks import _expected_ask_result, _load_existing_hermit_report
from three_layer_evaluation.reporting import write_markdown_report
from three_layer_evaluation.scenario_checks import common_case_concept_score, concept_f1_score
from three_layer_evaluation.standard_metrics import metric_validity_registry, standard_error_analysis, standard_metric_summary


def _score(method="prompt_only", *, precision=0.4, recall=0.8, f1=0.53, json_validity=0.875):
    return ScenarioScore(
        source_file="source.jsonl",
        line_number=1,
        case_id="case-1",
        scenario_id="scenario-1",
        model_key="qwen2_5_7b",
        model_name="qwen2.5:7b",
        method=method,
        role="IT",
        stage_id="BEGINNER_INTRODUCTORY",
        age_group_code="15_21",
        channel="sms",
        variant="fake",
        json_validity=json_validity,
        control_adherence=1.0,
        required_concept_precision=precision,
        required_concept_recall=recall,
        required_concept_f1=f1,
        grounding_completeness=0.5,
        contradiction=0,
        common_case_concept_precision=precision,
        common_case_concept_recall=recall,
        common_case_concept_f1=f1,
        json_parse_pass=int(json_validity == 1.0),
        all_controls_exact_match=1,
        contradiction_free_pass=1,
        missing_required_concepts=["red flag"],
        grounding_fields_missing=["source_id"],
    )


class ThreeLayerReportingAlignmentTests(unittest.TestCase):
    def test_negative_control_ask_defaults_to_expected_true(self):
        query = """
PREFIX psq: <http://example.test#>
ASK {
  FILTER NOT EXISTS { psq:SafeTemplate psq:hasUnsafeAction ?action . }
}
"""
        self.assertTrue(_expected_ask_result(Path("CQ3-NEG-001.ask.rq"), query))

    def test_ask_expected_comment_can_override_default(self):
        query = """
# expected: false
ASK { ?s ?p ?o }
"""
        self.assertFalse(_expected_ask_result(Path("custom.ask.rq"), query))

    def test_existing_hermit_report_can_be_imported_for_same_ontology(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ontology = root / "ontology.owl"
            ontology.write_text("<rdf:RDF/>", encoding="utf-8")
            report = root / "hermit-report.json"
            report.write_text(
                """
{
  "ontology": "%s",
  "status": "PASS",
  "consistent": true,
  "unsatisfiable_count": 0,
  "duration_seconds": 3.636
}
"""
                % str(ontology).replace("\\", "\\\\"),
                encoding="utf-8",
            )
            imported = _load_existing_hermit_report(ontology, report)
        self.assertIsNotNone(imported)
        self.assertEqual(imported[0], True)
        self.assertEqual(imported[1], 0)
        self.assertEqual(imported[2], "completed_from_existing_hermit_report")

    def test_method_summary_exports_precision_and_recall(self):
        rows = method_summary([_score(), _score(precision=0.6, recall=0.4, f1=0.48)])
        self.assertEqual(rows[0]["method"], "prompt_only")
        self.assertIn("required_concept_precision", rows[0])
        self.assertIn("required_concept_recall", rows[0])
        self.assertAlmostEqual(rows[0]["required_concept_precision"], 0.5)
        self.assertAlmostEqual(rows[0]["required_concept_recall"], 0.6)

    def test_common_oracle_is_method_invariant_and_excludes_traces(self):
        case = {
            "role": "IT",
            "channel": "sms",
            "variant": "fake",
            "age_group_code": "15_21",
            "stage_id": "BEGINNER_INTRODUCTORY",
            "difficulty_band": "easy",
        }
        scenario = {
            "role": "IT",
            "channel": "sms",
            "variant": "fake",
            "attack_type": "smishing",
            "correct_action": "Pause and verify through an approved channel.",
            "red_flags": ["Urgent link", "persuasion cue"],
            "generation_meta": {
                "rag_trace": [{"text_preview": "trace-only concept"}],
                "ontology_trace": {"evidence_sources": [{"label": "trace-only ontology label"}]},
            },
        }
        direct_raw = {"semantic_packet": {"must_include": ["unique packet constraint"]}}
        prompt_raw = {}
        self.assertEqual(
            common_case_concept_score(scenario, case),
            common_case_concept_score(dict(scenario), dict(case)),
        )
        self.assertNotEqual(
            concept_f1_score(direct_raw, scenario, case)[2],
            concept_f1_score(prompt_raw, scenario, case)[2],
        )

    def test_rank_biserial_uses_magnitude_ranks_not_only_signs(self):
        differences = [1.0, 2.0, -3.0]
        self.assertAlmostEqual(rank_biserial_from_differences(differences), 0.0)
        self.assertAlmostEqual(sign_dominance_from_differences(differences), 1.0 / 3.0)

    def test_standard_metric_registry_marks_project_constructs(self):
        rows = metric_validity_registry()
        by_metric = {row["metric"]: row for row in rows}
        self.assertIn("standard P/R/F1", by_metric["common_case_concept_precision_recall_f1"]["classification"])
        self.assertEqual(by_metric["legacy_overall_conformance"]["primary_or_secondary"], "secondary sensitivity/backward-compatibility only")
        for row in rows:
            self.assertTrue(row["display_name"])
            self.assertTrue(row["construct"])
            self.assertTrue(row["direction"])
            self.assertTrue(row["unit_of_analysis"])
            self.assertTrue(row["why_used"])
            self.assertTrue(row["interpretation"])
            self.assertTrue(row["threshold_status"])
            self.assertTrue(row["reporting_rule"])
        self.assertIn("OECD/JRC", by_metric["legacy_overall_conformance"]["reference"])
        self.assertIn("uncalibrated", by_metric["legacy_overall_conformance"]["threshold_status"])

    def test_standard_summary_and_case_clustered_statistics(self):
        scores = []
        for model in ("a", "b", "c"):
            for case_index in range(2):
                for method, value in zip(
                    ("prompt_only", "prompt_rag", "ontology_prompt_rag", "ontology_text_rag"),
                    (0.4, 0.5, 0.6, 0.7),
                ):
                    item = _score(method=method, f1=value)
                    item.model_key = model
                    item.case_id = f"case-{case_index}"
                    item.common_case_concept_f1 = value
                    scores.append(item)
        summary = standard_metric_summary(scores)
        self.assertEqual(len(summary), 4)
        self.assertIn("common_case_concept_f1", summary[0])
        stats = paired_statistics(scores)
        self.assertEqual(stats["primary_case_clustered_analysis"]["complete_case_n"], 2)
        self.assertEqual(stats["primary_model_case_analysis"]["complete_block_n"], 6)
        self.assertIn("all_method_friedman_primary_case_clustered", stats)
        self.assertEqual(stats["all_method_friedman"]["metric"], "overall_conformance")
        self.assertTrue(stats["all_method_friedman"]["deprecated_alias"])
        errors = standard_error_analysis(scores)
        self.assertEqual(errors[1]["prompt_only"], 0)

    def test_paper_labeled_error_analysis_preserves_raw_compatibility(self):
        scores = [_score()]
        raw_rows = error_analysis(scores)
        paper_rows = paper_labeled_error_analysis(scores)
        raw_error_types = {row["error_type"] for row in raw_rows}
        paper_error_types = {row["error_type"] for row in paper_rows}
        self.assertIn("invalid_json_or_schema", raw_error_types)
        self.assertIn("schema_provenance_incomplete", paper_error_types)
        self.assertIn("common_case_concept_not_perfect_recall", paper_error_types)
        self.assertIn("legacy_method_conditioned_concept_not_perfect_recall", paper_error_types)

    def test_markdown_report_contains_reviewer_safe_sections(self):
        ontology = OntologyValidationResult(
            ontology_path="ontology.owl",
            query_dir="queries",
            reasoner_consistency=True,
            reasoner_status="PASS",
            unsatisfiable_class_count=0,
            cq_passed=4,
            cq_total=8,
            mapping_passed=1,
            mapping_total=1,
            runtime_records_preserved=1,
            class_count=1,
            named_individual_count=1,
            object_property_count=1,
            datatype_property_count=1,
            notes=[],
        )
        scores = [_score()]
        method_rows = method_summary(scores)
        error_rows = error_analysis(scores)
        paper_error_rows = paper_labeled_error_analysis(scores)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evaluation_report.md"
            write_markdown_report(
                path,
                ontology=ontology,
                scenario_count=1,
                method_rows=method_rows,
                model_matrix=[{"model_key": "qwen2_5_7b", "prompt_only": 0.74}],
                error_rows=error_rows,
                paper_error_rows=paper_error_rows,
                stats={},
                output_files={"error_analysis_paper_labels_csv": "error_analysis_paper_labels.csv"},
                sources=["Saad-Falcon et al., ARES: https://arxiv.org/abs/2311.09476"],
            )
            text = path.read_text(encoding="utf-8")
        self.assertIn("Paper-Safe Main Claim", text)
        self.assertIn("Required-Concept Precision/Recall Diagnostic", text)
        self.assertIn("schema/provenance incompleteness", text)
        self.assertIn("Paper-Facing Error Analysis", text)
        self.assertIn("ARES", text)


if __name__ == "__main__":
    unittest.main()
