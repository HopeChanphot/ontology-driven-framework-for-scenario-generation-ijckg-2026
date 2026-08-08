import unittest

from config import filter_seeds, iter_generation_seeds
from prompt_only_generation.engine import PromptOnlyGenerationEngine


class PromptOnlyGenerationEngineTests(unittest.TestCase):
    def _seed(self):
        seeds = iter_generation_seeds(retrieval_modes=["ENGLISH_GLOBAL"])
        matches = filter_seeds(
            seeds,
            role="HR",
            stage_id="BEGINNER_INTRODUCTORY",
            age_group_code="22_35",
            retrieval_mode="ENGLISH_GLOBAL",
            language_mode="en",
        )
        self.assertTrue(matches)
        return matches[0]

    def test_dry_run_uses_no_rag_or_ontology(self):
        engine = PromptOnlyGenerationEngine()
        result = engine.generate_one(seed=self._seed(), channel="email", variant="fake", dry_run=True)

        self.assertTrue(result.validation_passed)
        self.assertFalse(result.scenario["generation_meta"]["rag_used"])
        self.assertFalse(result.scenario["generation_meta"]["ontology_used"])
        self.assertEqual(result.scenario["generation_meta"]["engine"], "prompt_only_generation")
        self.assertEqual(result.scenario["generation_meta"]["template_id"], "prompt_only_default_template_v1")
        self.assertEqual(result.scenario["channel"], "email")
        self.assertEqual(result.scenario["variant"], "fake")


if __name__ == "__main__":
    unittest.main()
