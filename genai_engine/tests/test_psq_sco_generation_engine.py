import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import build_generation_seed
from rag_engine import RAGEngine
from psq_sco_generation.cases import build_all_1350_cases, build_paper_120_cases, case_set_summary
from psq_sco_generation.engine import NullRAGEngine, PSQSCOGenerationEngine
from psq_sco_generation.models import LIGHTWEIGHT_MODEL_PROFILES, THREE_WAY_COMPARISON_MODES
from psq_sco_generation.ontology import DEFAULT_ONTOLOGY_PATH, PSQSCOOntology, REQUIRED_RULE_IDS
from psq_sco_generation.ontology_text import OntologyTextCorpus


class PSQSCOOntologyTests(unittest.TestCase):
    def test_ontology_summary_reads_v9_1_rdf_descriptions(self):
        ontology = PSQSCOOntology(DEFAULT_ONTOLOGY_PATH)
        summary = ontology.summary()
        self.assertGreaterEqual(summary["class_count"], 70)
        self.assertGreaterEqual(summary["named_individual_count"], 120)
        self.assertGreaterEqual(summary["scenario_template_count"], 6)
        self.assertGreaterEqual(summary["rule_count"], 8)

    def test_semantic_packet_contains_required_reviewer_cqs(self):
        ontology = PSQSCOOntology(DEFAULT_ONTOLOGY_PATH)
        seed = build_generation_seed("HR", "BEGINNER_INTRODUCTORY", "22_35", "ENGLISH_GLOBAL")
        packet = ontology.select_semantic_packet(seed, "email", "fake")
        text = " ".join(packet.quality_controls + packet.must_include + packet.must_exclude)
        self.assertIn("CQ1", text)
        self.assertIn("CQ2", text)
        self.assertIn("CQ3", text)
        self.assertIn("CQ4", text)
        self.assertEqual(packet.channel, "email")
        self.assertEqual(packet.variant, "fake")
        self.assertTrue(packet.required_rules)

    def test_required_rule_anchor_order_is_reproducible(self):
        ontology = PSQSCOOntology(DEFAULT_ONTOLOGY_PATH)
        seed = build_generation_seed("HR", "BEGINNER_INTRODUCTORY", "22_35", "ENGLISH_GLOBAL")
        packet = ontology.select_semantic_packet(seed, "email", "fake")
        self.assertEqual(
            [item["id"] for item in packet.required_rules],
            [rule_id for rule_id in REQUIRED_RULE_IDS if rule_id in ontology.by_id],
        )

    def test_ontology_text_corpus_builds_graph_to_text_documents(self):
        ontology = PSQSCOOntology(DEFAULT_ONTOLOGY_PATH)
        corpus = OntologyTextCorpus(ontology)
        summary = corpus.summary()
        self.assertGreaterEqual(summary["document_count"], 100)
        self.assertGreaterEqual(summary["document_counts_by_type"].get("scenario_template", 0), 3)
        self.assertGreaterEqual(summary["document_counts_by_type"].get("validation_rule", 0), 8)
        seed = build_generation_seed("HR", "BEGINNER_INTRODUCTORY", "22_35", "ENGLISH_GLOBAL")
        docs = corpus.retrieve(seed=seed, channel="email", variant="fake", limit=5)
        self.assertTrue(docs)
        self.assertTrue(any(doc.graph_text_strategy == "deterministic_random_walk_graph_to_text" for doc in docs))
        self.assertTrue(any(doc.graph_text_strategy == "graph_chain_of_thought_reasoning_interaction_execution" for doc in docs))
        self.assertTrue(any(doc.document_type == "graph_cot_trace" for doc in docs))


class PSQSCOGenerationEngineTests(unittest.TestCase):
    def test_local_lightweight_profiles_include_three_primary_models(self):
        self.assertIn("qwen2_5_7b", LIGHTWEIGHT_MODEL_PROFILES)
        self.assertIn("qwen3_8b", LIGHTWEIGHT_MODEL_PROFILES)
        self.assertIn("mistral_7b", LIGHTWEIGHT_MODEL_PROFILES)
        self.assertIn("phi3_mini", LIGHTWEIGHT_MODEL_PROFILES)

    def test_prompt_rag_dry_run_generates_schema_safe_scenario(self):
        seed = build_generation_seed("HR", "BEGINNER_INTRODUCTORY", "22_35", "ENGLISH_GLOBAL")
        engine = PSQSCOGenerationEngine(ontology_path=DEFAULT_ONTOLOGY_PATH, rag=NullRAGEngine())
        result = engine.generate_one(seed=seed, channel="email", variant="fake", mode="prompt_rag", dry_run=True)
        self.assertEqual(result.mode, "prompt_rag")
        self.assertEqual(result.scenario["channel"], "email")
        self.assertEqual(result.scenario["variant"], "fake")
        self.assertIsNone(result.semantic_packet)

    def test_prompt_only_dry_run_is_clean_baseline_without_rag_or_ontology(self):
        seed = build_generation_seed("HR", "BEGINNER_INTRODUCTORY", "22_35", "ENGLISH_GLOBAL")
        engine = PSQSCOGenerationEngine(ontology_path=DEFAULT_ONTOLOGY_PATH, rag=NullRAGEngine())
        result = engine.generate_one(seed=seed, channel="email", variant="fake", mode="prompt_only", dry_run=True)
        self.assertEqual(result.mode, "prompt_only")
        self.assertEqual(result.rag_examples, [])
        self.assertIsNone(result.semantic_packet)
        self.assertIsNone(result.scenario["generation_meta"]["ontology_trace"])
        self.assertIsNone(result.scenario["generation_meta"]["ontology_text_trace"])

    def test_ontology_prompt_rag_dry_run_adds_ontology_trace(self):
        seed = build_generation_seed("HR", "BEGINNER_INTRODUCTORY", "22_35", "ENGLISH_GLOBAL")
        engine = PSQSCOGenerationEngine(ontology_path=DEFAULT_ONTOLOGY_PATH, rag=NullRAGEngine())
        result = engine.generate_one(seed=seed, channel="email", variant="fake", mode="ontology_prompt_rag", dry_run=True)
        self.assertEqual(result.mode, "ontology_prompt_rag")
        self.assertIsNotNone(result.semantic_packet)
        trace = result.scenario["generation_meta"]["ontology_trace"]
        self.assertEqual(trace["ontology_version"], "PSQ-SCO v9.1")
        self.assertTrue(trace["required_rules"])

    def test_ontology_text_rag_dry_run_adds_graph_text_trace(self):
        seed = build_generation_seed("HR", "BEGINNER_INTRODUCTORY", "22_35", "ENGLISH_GLOBAL")
        engine = PSQSCOGenerationEngine(ontology_path=DEFAULT_ONTOLOGY_PATH, rag=NullRAGEngine())
        result = engine.generate_one(seed=seed, channel="email", variant="fake", mode="ontology_text_rag", dry_run=True)
        self.assertEqual(result.mode, "ontology_text_rag")
        self.assertIsNone(result.semantic_packet)
        self.assertEqual(result.prompt_metadata["external_rag_example_count"], 0)
        self.assertGreaterEqual(result.prompt_metadata["ontology_text_rag_example_count"], 5)
        self.assertEqual(result.prompt_metadata["combined_rag_context_count"], len(result.rag_examples))
        trace = result.scenario["generation_meta"]["ontology_text_trace"]
        self.assertEqual(trace["ontology_version"], "PSQ-SCO v9.1")
        self.assertGreaterEqual(trace["document_count"], 5)
        self.assertEqual(result.scenario["generation_meta"]["grounding_mode"], "ontology_text_rag")
        self.assertTrue(any(item.get("retrieval_tier") == "ontology_text_rag" for item in result.rag_examples))
        self.assertTrue(any(item.get("document_type") == "graph_cot_trace" for item in result.rag_examples))

    def test_jsonl_rag_fallback_retrieves_old_knowledge_base_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = Path(tmp)
            sms_dir = kb / "sms"
            sms_dir.mkdir(parents=True)
            (sms_dir / "scam_en.jsonl").write_text(
                json.dumps(
                    {
                        "channel": "sms",
                        "language": "en",
                        "is_scam": True,
                        "messages": ["Urgent IT support link. Verify your account now."],
                        "red_flags": ["urgent verification link"],
                        "correct_action": "Do not click. Verify with IT through an official channel.",
                        "source": "unit_test_kb",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with patch("rag_engine.KB_DIR", kb), patch("rag_engine.chromadb", None):
                rag = RAGEngine()
                seed = build_generation_seed("IT", "BEGINNER_INTRODUCTORY", "15_21", "ENGLISH_GLOBAL")
                items = rag.retrieve_for_scenario_v2(seed, "sms", "fake", n_results=1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_file"], "scam_en.jsonl")
        self.assertEqual(items[0]["retrieval_backend"], "jsonl_lexical_fallback")


class PSQSCOPaperCaseSetTests(unittest.TestCase):
    def test_paper_120_case_set_is_balanced_and_matched(self):
        cases = build_paper_120_cases()
        summary = case_set_summary(cases)
        self.assertEqual(len(cases), 120)
        self.assertEqual(summary["outputs_when_mode_both"], 240)
        self.assertEqual(summary["outputs_when_mode_three_mode"], 360)
        self.assertEqual(set(summary["counts_by_role"].values()), {24})
        self.assertEqual(set(summary["counts_by_channel"].values()), {40})
        self.assertEqual(summary["counts_by_variant"], {"fake": 60, "real": 60})
        self.assertEqual(set(summary["counts_by_age_group"].values()), {24})
        self.assertEqual(summary["counts_by_difficulty_condition"]["low_foundational"], 30)
        self.assertEqual(summary["counts_by_difficulty_condition"]["medium_applied"], 30)
        self.assertEqual(summary["counts_by_difficulty_condition"]["high_expert"], 30)
        self.assertEqual(summary["counts_by_difficulty_condition"]["balanced_repetition"], 30)
        self.assertTrue(all(case.modes_to_compare == ["prompt_rag", "ontology_prompt_rag"] for case in cases))

    def test_three_mode_case_summary_uses_same_120_cases(self):
        cases = build_paper_120_cases()
        summary = case_set_summary(cases, modes=THREE_WAY_COMPARISON_MODES)
        self.assertEqual(summary["case_count"], 120)
        self.assertEqual(summary["modes_to_compare"], list(THREE_WAY_COMPARISON_MODES))
        self.assertEqual(summary["outputs_for_selected_modes"], 360)

    def test_full_1350_capacity_case_set_supports_three_modes(self):
        cases = build_all_1350_cases()
        summary = case_set_summary(cases, modes=THREE_WAY_COMPARISON_MODES)
        self.assertEqual(len(cases), 1350)
        self.assertEqual(summary["outputs_for_selected_modes"], 4050)


if __name__ == "__main__":
    unittest.main()
