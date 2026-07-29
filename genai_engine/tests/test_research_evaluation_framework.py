import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from personashield_layer1_layer2_evaluator import write_outputs
from scenario_evaluation.consensus import JudgeScore, aggregate_judge_scores
from scenario_evaluation.decisions import determine_final_decision
from scenario_evaluation.guidance import generate_revision_guidance
from scenario_evaluation.judges import (
    hardware_warnings,
    load_judge_config,
    select_judges,
)
from scenario_evaluation.qualifiers import qualify_score
from scenario_evaluation.weights import (
    DEFAULT_BASELINE_WEIGHTS,
    WeightConfigError,
    build_regression_dataset,
    normalized_learning_gain,
    validate_weights,
)


class WeightValidationTests(unittest.TestCase):
    def test_valid_weights_sum_to_one(self):
        self.assertEqual(validate_weights(DEFAULT_BASELINE_WEIGHTS), DEFAULT_BASELINE_WEIGHTS)

    def test_invalid_sum_raises(self):
        with self.assertRaises(WeightConfigError):
            validate_weights(
                {
                    "pedagogical_quality": 0.4,
                    "cybersecurity_realism": 0.4,
                    "usability_game_clarity": 0.2,
                    "ethical_safety": 0.2,
                }
            )

    def test_missing_criterion_raises(self):
        with self.assertRaises(WeightConfigError):
            validate_weights({"pedagogical_quality": 1.0})

    def test_negative_weight_raises(self):
        with self.assertRaises(WeightConfigError):
            validate_weights(
                {
                    "pedagogical_quality": -0.1,
                    "cybersecurity_realism": 0.7,
                    "usability_game_clarity": 0.3,
                    "ethical_safety": 0.1,
                }
            )

    def test_weight_above_one_raises(self):
        with self.assertRaises(WeightConfigError):
            validate_weights(
                {
                    "pedagogical_quality": 1.1,
                    "cybersecurity_realism": 0.0,
                    "usability_game_clarity": 0.0,
                    "ethical_safety": -0.1,
                }
            )


class LearningGainTests(unittest.TestCase):
    def test_normal_learning_gain(self):
        self.assertAlmostEqual(normalized_learning_gain(40, 70), 0.5)

    def test_pretest_100_returns_none(self):
        self.assertIsNone(normalized_learning_gain(100, 100))

    def test_missing_posttest_returns_none(self):
        self.assertIsNone(normalized_learning_gain(50, None))

    def test_negative_gain_allowed(self):
        self.assertAlmostEqual(normalized_learning_gain(80, 70), -0.5)

    def test_invalid_rows_excluded(self):
        dataset = build_regression_dataset(
            [
                {
                    "scenario_id": "ok",
                    "pre_test_score": 20,
                    "post_test_score": 60,
                    "P score": 0.7,
                    "C score": 0.8,
                    "U score": 0.6,
                    "E score": 0.9,
                },
                {
                    "scenario_id": "bad",
                    "pre_test_score": 100,
                    "post_test_score": 100,
                    "P score": 0.7,
                    "C score": 0.8,
                    "U score": 0.6,
                    "E score": 0.9,
                },
            ]
        )
        self.assertEqual(dataset.valid_rows, 1)
        self.assertEqual(dataset.excluded_rows, 1)


class QualifierAndDecisionTests(unittest.TestCase):
    def test_qualifier_mapping(self):
        self.assertEqual(qualify_score(0.92).qualifier, "Excellent")
        self.assertEqual(qualify_score(0.75).qualifier, "Good")
        self.assertEqual(qualify_score(0.65).qualifier, "Adequate")
        self.assertEqual(qualify_score(0.4733).qualifier, "Poor")
        self.assertEqual(qualify_score(0.10).qualifier, "Fail")

    def _scores_for_fws(self, score):
        return {
            "pedagogical_quality": score,
            "cybersecurity_realism": score,
            "usability_game_clarity": score,
            "ethical_safety": score,
        }

    def test_final_decision_thresholds(self):
        self.assertEqual(determine_final_decision(self._scores_for_fws(0.80)).final_decision, "ACCEPTED")
        self.assertEqual(determine_final_decision(self._scores_for_fws(0.65)).final_decision, "MINOR_REVISION")
        self.assertEqual(determine_final_decision(self._scores_for_fws(0.50)).final_decision, "MAJOR_REVISION")
        self.assertEqual(determine_final_decision(self._scores_for_fws(0.30)).final_decision, "REJECT_REGENERATE")

    def test_veto_logic(self):
        scores = {
            "pedagogical_quality": 0.20,
            "cybersecurity_realism": 1.0,
            "usability_game_clarity": 1.0,
            "ethical_safety": 1.0,
        }
        self.assertNotEqual(determine_final_decision(scores).final_decision, "ACCEPTED")

        scores = {
            "pedagogical_quality": 1.0,
            "cybersecurity_realism": 1.0,
            "usability_game_clarity": 1.0,
            "ethical_safety": 0.20,
        }
        self.assertEqual(determine_final_decision(scores).final_decision, "REJECT_REGENERATE")

        scores = self._scores_for_fws(0.80)
        self.assertEqual(determine_final_decision(scores).final_decision, "ACCEPTED")


class RevisionGuidanceTests(unittest.TestCase):
    def test_low_pedagogy_guidance(self):
        scores = {
            "pedagogical_quality": 0.4733,
            "cybersecurity_realism": 0.9,
            "usability_game_clarity": 0.9,
            "ethical_safety": 0.9,
        }
        guidance = " ".join(generate_revision_guidance({}, scores))
        self.assertIn("Bloom Level 3+", guidance)
        self.assertIn("LO-linked", guidance)
        self.assertIn("wrong-choice explanations", guidance)

    def test_high_ethical_safety_guidance(self):
        scores = {
            "pedagogical_quality": 0.9,
            "cybersecurity_realism": 0.9,
            "usability_game_clarity": 0.9,
            "ethical_safety": 0.92,
        }
        guidance = " ".join(generate_revision_guidance({}, scores))
        self.assertIn("Ethical Safety achieved an Excellent rating", guidance)
        self.assertIn("no ethical revision needed", guidance)

    def test_low_cyber_and_usability_guidance(self):
        scores = {
            "pedagogical_quality": 0.9,
            "cybersecurity_realism": 0.40,
            "usability_game_clarity": 0.40,
            "ethical_safety": 0.9,
        }
        guidance = " ".join(generate_revision_guidance({}, scores))
        self.assertIn("Cybersecurity Realism is weak", guidance)
        self.assertIn("Usability / Game Clarity is weak", guidance)


class JudgeConfigTests(unittest.TestCase):
    def test_loading_open_weight_judge_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "judges.yaml"
            path.write_text(
                """
judges:
  - judge_id: mock_local
    model_name: Qwen2.5-7B-Instruct quantized
    model_family: qwen
    provider_type: mock_test
    endpoint_url: ""
    local_runtime: none
    role: multilingual_json
    enabled: true
    cost_mode: mock_test
""",
                encoding="utf-8",
            )
            judges = load_judge_config(path)
            self.assertEqual(judges[0].judge_id, "mock_local")
            self.assertFalse(judges[0].requires_api_key)

    def test_rejecting_paid_judges_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paid.yaml"
            path.write_text(
                """
judges:
  - judge_id: paid
    model_name: PaidModel
    model_family: paid
    provider_type: paid_api
    endpoint_url: https://example.invalid/v1
    local_runtime: none
    role: baseline
    enabled: true
    cost_mode: paid_api
""",
                encoding="utf-8",
            )
            with self.assertRaises(Exception):
                select_judges(judge_config=path, disable_paid_judges=True)

    def test_selecting_profiles_and_hardware_warning(self):
        research = select_judges("open_weight_research", disable_paid_judges=True)
        low = select_judges("local_low_spec", disable_paid_judges=True)
        self.assertEqual(len(research), 3)
        self.assertGreaterEqual(len(low), 3)
        self.assertTrue(any("70B+" in warning for warning in hardware_warnings(research)))
        self.assertTrue(all(not judge.requires_api_key for judge in low))


class ConsensusTests(unittest.TestCase):
    def test_aggregate_and_high_disagreement(self):
        judge_scores = [
            JudgeScore("a", "A", "a", "mock_test", "none", "p", {}, {"pedagogical_quality": 0.75, "cybersecurity_realism": 0.8, "usability_game_clarity": 0.8, "ethical_safety": 0.9}),
            JudgeScore("b", "B", "b", "mock_test", "none", "p", {}, {"pedagogical_quality": 0.50, "cybersecurity_realism": 0.8, "usability_game_clarity": 0.8, "ethical_safety": 0.9}),
            JudgeScore("c", "C", "c", "mock_test", "none", "p", {}, {"pedagogical_quality": 0.25, "cybersecurity_realism": 0.8, "usability_game_clarity": 0.8, "ethical_safety": 0.9}),
        ]
        consensus = aggregate_judge_scores(judge_scores)
        self.assertAlmostEqual(consensus.criterion_stats["pedagogical_quality"]["mean"], 0.5)
        self.assertAlmostEqual(consensus.criterion_stats["pedagogical_quality"]["median"], 0.5)
        self.assertTrue(consensus.judge_disagreement)
        self.assertIn("pedagogical_quality", consensus.high_disagreement_criteria)
        decision = determine_final_decision(consensus.aggregated_scores, judge_disagreement=consensus.judge_disagreement)
        self.assertTrue(decision.needs_human_review)


class ReportGenerationTests(unittest.TestCase):
    def test_report_and_exports_include_new_fields(self):
        judges = select_judges("local_low_spec", disable_paid_judges=True)
        judge_score = JudgeScore(
            "mock",
            "Mock",
            "mock",
            "mock_test",
            "none",
            "test",
            {"pedagogical_quality": 4, "cybersecurity_realism": 4, "usability_game_clarity": 4, "ethical_safety": 4},
            {"pedagogical_quality": 0.9, "cybersecurity_realism": 0.9, "usability_game_clarity": 0.9, "ethical_safety": 0.9},
        )
        df = pd.DataFrame(
            [
                {
                    "source_file": "pool.json",
                    "model_name": "m",
                    "channel": "sms",
                    "variant": "fake",
                    "scenario_id": "s1",
                    "role": "IT",
                    "macro_stage": "Beginner",
                    "micro_stage": "Introductory",
                    "age_group": "A1521",
                    "layer1_pass": True,
                    "layer1_error_count": 0,
                    "readability_score": 0.9,
                    "learning_alignment_score": 0.9,
                    "cybersecurity_realism_score": 0.9,
                    "safety_score": 0.9,
                    "game_usability_score": 0.9,
                    "openai_pedagogy_quality_score": 0.9,
                    "claude_cybersecurity_safety_score": 0.9,
                    "gemini_game_usability_score": 0.9,
                    "combined_layer2_score": 0.9,
                    "final_weighted_score": 0.9,
                    "final_decision": "ACCEPTED",
                    "needs_human_review": False,
                    "veto_applied": False,
                    "veto_reason": "",
                    "judge_disagreement": False,
                    "weakest_criterion": "pedagogical_quality",
                    "weakest_criterion_qualifier": "Excellent",
                    "revision_guidance": json.dumps([]),
                    "pedagogical_quality_score": 0.9,
                    "cybersecurity_realism_pc_score": 0.9,
                    "usability_game_clarity_score": 0.9,
                    "ethical_safety_score": 0.9,
                    "judge_scores_json": json.dumps([judge_score.as_dict()]),
                },
                {
                    "source_file": "pool.json",
                    "model_name": "m",
                    "channel": "email",
                    "variant": "real",
                    "scenario_id": "s2",
                    "role": "HR",
                    "macro_stage": "Expert",
                    "micro_stage": "Advanced",
                    "age_group": "A6090",
                    "layer1_pass": True,
                    "layer1_error_count": 0,
                    "readability_score": 0.5,
                    "learning_alignment_score": 0.5,
                    "cybersecurity_realism_score": 0.5,
                    "safety_score": 0.9,
                    "game_usability_score": 0.5,
                    "openai_pedagogy_quality_score": 0.5,
                    "claude_cybersecurity_safety_score": 0.5,
                    "gemini_game_usability_score": 0.5,
                    "combined_layer2_score": 0.5,
                    "final_weighted_score": 0.55,
                    "final_decision": "MAJOR_REVISION",
                    "needs_human_review": False,
                    "veto_applied": False,
                    "veto_reason": "",
                    "judge_disagreement": False,
                    "weakest_criterion": "pedagogical_quality",
                    "weakest_criterion_qualifier": "Adequate",
                    "revision_guidance": json.dumps(["Improve pedagogy"]),
                    "pedagogical_quality_score": 0.5,
                    "cybersecurity_realism_pc_score": 0.5,
                    "usability_game_clarity_score": 0.5,
                    "ethical_safety_score": 0.9,
                    "judge_scores_json": json.dumps([judge_score.as_dict()]),
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                df,
                Path(tmp),
                excel=False,
                issue_threshold=0.55,
                judge_profile="local_low_spec",
                judges=judges,
                weighting_metadata={"weighting_phase": "phase_1_fixed_baseline", "weights_used": DEFAULT_BASELINE_WEIGHTS},
                paid_judges_enabled=False,
            )
            detailed = pd.read_csv(outputs["detailed_csv"])
            self.assertIn("final_decision", detailed.columns)
            self.assertIn("final_weighted_score", detailed.columns)
            report = json.loads(outputs["research_report_json"].read_text(encoding="utf-8"))
            self.assertEqual(report["executive_summary"]["accepted"]["count"], 1)
            self.assertEqual(report["executive_summary"]["major_revision"]["count"], 1)
            self.assertIn("llm_judge_section", report)
            self.assertFalse(report["llm_judge_section"]["paid_judge_enabled"])
            long_csv = pd.read_csv(outputs["judge_scores_long_csv"])
            self.assertIn("qualifier", long_csv.columns)


if __name__ == "__main__":
    unittest.main()
