"""Focused tests for the isolated targeted evaluation repair."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "targeted_evaluation.py"
)
SPEC = importlib.util.spec_from_file_location("targeted_evaluation", MODULE_PATH)
assert SPEC and SPEC.loader
targeted = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = targeted
SPEC.loader.exec_module(targeted)


class OperationalIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.row = {
            "json_validity": 1.0,
            "control_adherence": 1.0,
            "required_concept_f1": 0.5,
            "grounding_completeness": 0.75,
            "contradiction": 0,
        }

    def test_equal_weight_formula(self) -> None:
        self.assertAlmostEqual(
            targeted.operational_index(self.row, targeted.EQUAL_WEIGHTS),
            (1.0 + 1.0 + 0.5 + 0.75 + 1.0) / 5.0,
        )

    def test_legacy_formula_is_sensitivity_only(self) -> None:
        expected = 0.20 + 0.25 + 0.25 * 0.5 + 0.20 * 0.75 + 0.10
        self.assertAlmostEqual(
            targeted.operational_index(self.row, targeted.LEGACY_WEIGHTS),
            expected,
        )

    def test_weight_vectors_are_deterministic_and_sum_to_one(self) -> None:
        first = targeted.deterministic_weight_vectors(draws=5, seed=77)
        second = targeted.deterministic_weight_vectors(draws=5, seed=77)
        self.assertEqual(first, second)
        for vector in first:
            self.assertAlmostEqual(sum(vector), 1.0)
            self.assertTrue(all(value >= 0.0 for value in vector))


class TraceAccumulatorTests(unittest.TestCase):
    def test_empty_contract_is_not_applicable(self) -> None:
        result = targeted.TraceAccumulator().finish()
        self.assertIsNone(result.traceability_score)
        self.assertFalse(result.traceability_applicable)

    def test_resolution_fraction_and_diagnostics(self) -> None:
        accumulator = targeted.TraceAccumulator()
        accumulator.add("source:a", True)
        accumulator.add("source:b", False)
        accumulator.add("source:c", False, wrong_target="source:x")
        accumulator.add("source:a", True)
        result = accumulator.finish()
        self.assertAlmostEqual(result.traceability_score, 1.0 / 3.0)
        self.assertEqual(result.missing_trace_ids, ("source:b",))
        self.assertEqual(result.wrong_target_trace_ids, ("source:c=>source:x",))
        self.assertEqual(
            result.duplicate_or_conflicting_trace_ids,
            ("duplicate:source:a",),
        )


class CanonicalRegistryTests(unittest.TestCase):
    def test_dataset_stem_normalization(self) -> None:
        self.assertEqual(
            targeted._dataset_stem_from_source_file("auto_CEAS_08_scam_en.jsonl"),
            "CEAS_08",
        )
        self.assertEqual(
            targeted._dataset_stem_from_source_file("auto_English_NonScam_ham_en.jsonl"),
            "English_NonScam",
        )


class InputDesignTests(unittest.TestCase):
    def test_duplicate_keys_are_detected(self) -> None:
        raw = {
            "mode": "prompt_only",
            "llm_key": "m",
            "case": {"case_id": "c"},
            "scenario": {"generation_meta": {"mode": "prompt_only"}},
            "used_live_llm": True,
            "used_fallback": False,
        }
        records = [
            targeted.ScenarioRecord("a", 1, raw),
            targeted.ScenarioRecord("b", 1, raw),
        ]
        with self.assertRaises(RuntimeError):
            targeted.validate_input_design(records)


if __name__ == "__main__":
    unittest.main()
