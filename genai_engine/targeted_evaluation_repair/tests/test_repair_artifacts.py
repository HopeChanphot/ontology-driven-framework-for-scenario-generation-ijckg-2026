"""Regression tests for the completed targeted repair artifacts."""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = PACKAGE_ROOT / "evaluation_rerun"
OVERLEAF_DIR = PACKAGE_ROOT / "overleaf"


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class EvaluationArtifactTests(unittest.TestCase):
    def test_frozen_design_cardinality_and_integrity(self) -> None:
        rows = read_csv(EVALUATION_DIR / "component_metrics_by_output.csv")
        self.assertEqual(len(rows), 1440)
        keys = {(row["case_id"], row["model_key"], row["method"]) for row in rows}
        self.assertEqual(len(keys), 1440)
        self.assertEqual(sum(row["used_live_llm"] == "True" for row in rows), 1440)
        self.assertEqual(sum(row["used_fallback"] == "True" for row in rows), 0)
        for field in (
            "expected_trace_ids",
            "resolved_trace_ids",
            "missing_trace_ids",
            "wrong_target_trace_ids",
            "duplicate_or_conflicting_trace_ids",
            "traceability_score",
            "oci_equal_weight",
            "oci_legacy_sensitivity",
        ):
            self.assertIn(field, rows[0])

    def test_exact_equal_weight_condition_means(self) -> None:
        rows = read_csv(EVALUATION_DIR / "method_summary.csv")
        values = {
            row["method"]: float(row["oci_equal_weight_secondary"]) for row in rows
        }
        expected = {
            "prompt_only": 0.7985256195015837,
            "prompt_rag": 0.846074082790186,
            "ontology_prompt_rag": 0.9089496651254056,
            "ontology_text_rag": 0.8792567031015872,
        }
        self.assertEqual(set(values), set(expected))
        for method, value in expected.items():
            self.assertAlmostEqual(values[method], value, places=12)

    def test_five_disclosed_selection_rules_are_present(self) -> None:
        cases = json.loads(
            (EVALUATION_DIR / "five_matched_cases.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [case["selection_type"] for case in cases],
            [
                "representative_median_performing",
                "ontology_to_text_contradiction",
                "external_rag_returned_no_text",
                "legitimate_communication",
                "clearest_precision_recall_tradeoff",
            ],
        )
        for case in cases:
            self.assertEqual(len(case["comparisons"]), 4)
            for comparison in case["comparisons"]:
                word_count = len(comparison["actual_excerpt"].split())
                self.assertGreaterEqual(word_count, 40)
                self.assertLessEqual(word_count, 70)


class ManuscriptArtifactTests(unittest.TestCase):
    def test_protected_blocks_and_static_references(self) -> None:
        manifest = json.loads(
            (OVERLEAF_DIR / "latex_update_manifest.json").read_text(encoding="utf-8")
        )
        self.assertTrue(manifest["protected_blocks_all_byte_identical"])
        self.assertEqual(manifest["citation_check"]["missing_citations"], [])
        self.assertEqual(manifest["citation_check"]["missing_references"], [])
        self.assertTrue(manifest["forbidden_string_check"]["passed"])
        self.assertFalse(manifest["figure_width_check"]["contains_1_10_textwidth"])
        self.assertTrue(manifest["figure_width_check"]["contains_textwidth"])

    def test_required_composite_index_dois_are_present(self) -> None:
        bibliography = (OVERLEAF_DIR / "references.bib").read_text(encoding="utf-8")
        self.assertIn("10.1007/s11205-017-1832-9", bibliography)
        self.assertIn("10.1016/j.ecolind.2017.03.056", bibliography)

    def test_final_build_has_no_overfull_or_undefined_diagnostics(self) -> None:
        log = (OVERLEAF_DIR / "main.log").read_text(encoding="utf-8", errors="replace")
        for marker in (
            "Overfull",
            "undefined citations",
            "undefined references",
            "Citation `",
            "Reference `",
        ):
            self.assertNotIn(marker, log)
        self.assertTrue((OVERLEAF_DIR / "main.pdf").exists())


if __name__ == "__main__":
    unittest.main()
