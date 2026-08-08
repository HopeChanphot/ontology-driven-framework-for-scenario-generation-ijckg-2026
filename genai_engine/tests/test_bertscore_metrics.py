import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from three_layer_evaluation.bertscore_metrics import bertscore_alignment_analysis
from three_layer_evaluation.models import ScenarioScore


class BERTScoreMetricsTests(unittest.TestCase):
    def test_disabled_bertscore_returns_empty_rows(self):
        rows, summary = bertscore_alignment_analysis([], enabled=False)
        self.assertEqual(rows, [])
        self.assertEqual(summary, [])

    def test_bertscore_rows_use_case_reference_metadata(self):
        payload = {
            "case": {
                "case_id": "PSQ-SCO-120-001",
                "role": "FINANCE",
                "stage_id": "BEGINNER_INTRODUCTORY",
                "age_group_code": "A2235",
                "channel": "email",
                "variant": "fake",
                "difficulty_condition": "low_foundational",
            },
            "scenario": {
                "scenario_id": "S1",
                "title": "Vendor Bank Detail Verification",
                "opening_hook": "A finance employee receives an urgent vendor email.",
                "channel": "email",
                "variant": "fake",
                "attack_type": "phishing",
                "correct_action": "Pause and verify through an approved trusted channel.",
                "red_flags": ["urgent bank detail change", "external sender"],
                "game_choices": [
                    {"label": "Verify independently", "feedback": "Correct defensive action."},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "scenarios.jsonl"
            source.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            score = ScenarioScore(
                source_file=str(source),
                line_number=1,
                case_id="PSQ-SCO-120-001",
                scenario_id="S1",
                model_key="qwen2_5_7b",
                model_name="qwen2.5:7b-instruct",
                method="prompt_rag",
                role="FINANCE",
                stage_id="BEGINNER_INTRODUCTORY",
                age_group_code="A2235",
                channel="email",
                variant="fake",
                json_validity=1.0,
                control_adherence=1.0,
                required_concept_precision=1.0,
                required_concept_recall=1.0,
                required_concept_f1=1.0,
                grounding_completeness=1.0,
                contradiction=0,
            )
            with patch(
                "three_layer_evaluation.bertscore_metrics._compute_bertscore",
                return_value=([0.81], [0.82], [0.815], "mock_bert_score"),
            ):
                rows, summary = bertscore_alignment_analysis([score], enabled=True)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reference_kind"], "automatic_case_reference")
        self.assertEqual(rows[0]["bertscore_backend"], "mock_bert_score")
        self.assertAlmostEqual(rows[0]["bertscore_f1"], 0.815)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["method"], "prompt_rag")
        self.assertAlmostEqual(summary[0]["bertscore_f1_mean"], 0.815)


if __name__ == "__main__":
    unittest.main()
