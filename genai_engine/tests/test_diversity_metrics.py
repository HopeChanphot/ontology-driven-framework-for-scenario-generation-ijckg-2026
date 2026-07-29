import unittest

from three_layer_evaluation.diversity_metrics import (
    corpus_self_bleu,
    embed_texts,
    pairwise_embedding_diversity,
    semantic_diversity_method_summary,
)


class DiversityMetricTests(unittest.TestCase):
    def test_embedding_diversity_is_higher_for_different_texts(self):
        repeated = [
            "urgent payroll link verify by clicking",
            "urgent payroll link verify by clicking",
            "urgent payroll link verify by clicking",
        ]
        varied = [
            "urgent payroll link verify by clicking",
            "voice call requests bank detail change",
            "legitimate calendar workflow approval notice",
        ]
        repeated_embeddings, _, _ = embed_texts(repeated)
        varied_embeddings, _, _ = embed_texts(varied)
        _, repeated_diversity = pairwise_embedding_diversity(repeated_embeddings)
        _, varied_diversity = pairwise_embedding_diversity(varied_embeddings)
        self.assertIsNotNone(repeated_diversity)
        self.assertIsNotNone(varied_diversity)
        self.assertGreater(varied_diversity, repeated_diversity)

    def test_self_bleu_is_higher_for_repeated_texts(self):
        repeated = [
            "urgent payroll link verify by clicking",
            "urgent payroll link verify by clicking",
            "urgent payroll link verify by clicking",
        ]
        varied = [
            "urgent payroll link verify by clicking",
            "voice call requests bank detail change",
            "legitimate calendar workflow approval notice",
        ]
        self.assertGreater(corpus_self_bleu(repeated), corpus_self_bleu(varied))

    def test_semantic_diversity_method_summary_averages_model_rows(self):
        rows = [
            {
                "granularity": "model_method",
                "model_key": "a",
                "method": "prompt_only",
                "n": 2,
                "embedding_diversity": 0.4,
                "mean_pairwise_cosine_similarity": 0.6,
                "self_bleu": 0.8,
                "self_bleu_diversity": 0.2,
                "embedding_backend": "hash",
                "embedding_model": "test",
            },
            {
                "granularity": "model_method",
                "model_key": "b",
                "method": "prompt_only",
                "n": 2,
                "embedding_diversity": 0.6,
                "mean_pairwise_cosine_similarity": 0.4,
                "self_bleu": 0.4,
                "self_bleu_diversity": 0.6,
                "embedding_backend": "hash",
                "embedding_model": "test",
            },
        ]
        summary = semantic_diversity_method_summary(rows)
        self.assertEqual(summary[0]["method"], "prompt_only")
        self.assertAlmostEqual(summary[0]["embedding_diversity_mean"], 0.5)
        self.assertAlmostEqual(summary[0]["self_bleu_mean"], 0.6)


if __name__ == "__main__":
    unittest.main()
