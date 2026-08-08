"""Command-line interface for the three-layer PSQ-SCO evaluator."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .comparison import (
    decision_summary,
    error_analysis,
    method_summary,
    model_method_decision_summary,
    model_method_matrix,
    model_method_summary,
    paired_statistics,
    paper_labeled_error_analysis,
)
from .bertscore_metrics import bertscore_alignment_analysis
from .diversity_metrics import semantic_diversity_analysis, semantic_diversity_method_summary
from .io import discover_scenario_files, load_jsonl_records, write_json
from .models import CONFORMANCE_WEIGHTS
from .models import METHOD_IMPLEMENTATION_NOTES, METHOD_LABELS
from .ontology_checks import validate_ontology
from .paper120 import (
    condition_manifest_rows,
    dataset_description,
    diversity_analysis,
    final_paper_120_files,
    manual_inspection_sample,
    matched_case_audit,
    metric_definitions_markdown,
    paper_120_graph_walk_v1_files,
    timing_analysis,
    write_research_analysis,
)
from .reporting import write_csv, write_markdown_report
from .scenario_checks import score_records
from .source_linkage import source_linkage_audit, source_linkage_summary
from .standard_metrics import metric_validity_registry, standard_error_analysis, standard_metric_summary


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ONTOLOGY_ROOT = PACKAGE_ROOT / "ontology"
DEFAULT_ONTOLOGY_PATH = DEFAULT_ONTOLOGY_ROOT / "ontology" / "personashield-psq-sco-v9.1.owl"
DEFAULT_QUERY_DIR = DEFAULT_ONTOLOGY_ROOT / "queries" / "v9_1"
DEFAULT_HERMIT_REPORT = DEFAULT_ONTOLOGY_ROOT / "outputs" / "v9_1" / "hermit-reasoner-report.json"
DEFAULT_SCENARIO_OUTPUT_ROOT = ENGINE_ROOT / "output"


ACADEMIC_SOURCES = [
    "OWL 2 Web Ontology Language Document Overview, W3C Recommendation, 2012: https://www.w3.org/TR/owl2-overview/",
    "SPARQL 1.1 Query Language, W3C Recommendation, 2013: https://www.w3.org/TR/sparql11-query/",
    "Shapes Constraint Language (SHACL), W3C Recommendation, 2017: https://www.w3.org/TR/shacl/",
    "PROV-O: The PROV Ontology, W3C Recommendation, 2013: https://www.w3.org/TR/prov-o/",
    "Glimm et al., HermiT: An OWL 2 Reasoner, Journal of Automated Reasoning, 2014: https://doi.org/10.1007/s10817-014-9305-1",
    "Uschold and Gruninger, Ontologies: Principles, methods and applications, Knowledge Engineering Review, 1996: https://doi.org/10.1017/S0269888900007797",
    "Gruninger and Fox, Methodology for the Design and Evaluation of Ontologies, IJCAI Workshop, 1995: https://www.eil.utoronto.ca/wp-content/uploads/enterprise-modelling/papers/gruninger-ijcai95.pdf",
    "Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks, NeurIPS, 2020: https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html",
    "Petroni et al., KILT: a Benchmark for Knowledge Intensive Language Tasks, NAACL, 2021: https://aclanthology.org/2021.naacl-main.200/",
    "Es et al., RAGAS: Automated Evaluation of Retrieval Augmented Generation, EACL System Demonstrations, 2024: https://aclanthology.org/2024.eacl-demo.16/",
    "Saad-Falcon et al., ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems, NAACL, 2024: https://aclanthology.org/2024.naacl-long.20/",
    "Ru et al., RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generation, NeurIPS Datasets and Benchmarks, 2024: https://proceedings.neurips.cc/paper_files/paper/2024/hash/27245589131d17368cccdfa990cbf16e-Abstract-Datasets_and_Benchmarks_Track.html",
    "Thakur et al., BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models, NeurIPS Datasets and Benchmarks, 2021: https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/hash/65b9eea6e1cc6bb9f0cd2a47751a186f-Abstract-round2.html",
    "Jin et al., Graph Chain-of-Thought: Augmenting Large Language Models by Reasoning on Graphs, ACL Findings, 2024: https://aclanthology.org/2024.findings-acl.11/",
    "Zhu et al., Texygen: A Benchmarking Platform for Text Generation Models, SIGIR, 2018: https://arxiv.org/abs/1802.01886",
    "Tevet and Berant, Evaluating the Evaluation of Diversity in Natural Language Generation, EACL, 2021: https://arxiv.org/abs/2004.02990",
    "Han et al., Measuring and Improving Semantic Diversity of Dialogue Generation, EMNLP Findings, 2022: https://arxiv.org/abs/2210.05725",
    "Reimers and Gurevych, Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks, EMNLP-IJCNLP, 2019: https://aclanthology.org/D19-1410/",
    "Zhang et al., BERTScore: Evaluating Text Generation with BERT, ICLR, 2020: https://arxiv.org/abs/1904.09675",
    "Galanis et al., NaturalOWL: Generating Texts from OWL Ontologies, Journal of Artificial Intelligence Research, 2014: https://doi.org/10.1613/jair.4017",
    "Bontcheva and Wilks, Automatic Report Generation from Ontologies: the MIAKT approach, Data & Knowledge Engineering, 2009: https://doi.org/10.1016/j.datak.2009.08.004",
    "Mousavi et al., Investigating the Faithfulness of Knowledge Graph-to-Text Generation, INLG, 2023: https://aclanthology.org/2023.inlg-main.8/",
    "Sokolova and Lapalme, A systematic analysis of performance measures for classification tasks, Information Processing and Management, 2009: https://doi.org/10.1016/j.ipm.2009.03.002",
    "McNemar, Note on the sampling error of the difference between correlated proportions or percentages, Psychometrika, 1947: https://doi.org/10.1007/BF02295996",
    "Cochran, The comparison of percentages in matched samples, Biometrika, 1950: https://doi.org/10.2307/2332378",
    "Wilcoxon, Individual comparisons by ranking methods, Biometrics Bulletin, 1945: https://doi.org/10.2307/3001968",
    "Friedman, The use of ranks to avoid the assumption of normality implicit in analysis of variance, JASA, 1937: https://doi.org/10.1080/01621459.1937.10503522",
    "Holm, A simple sequentially rejective multiple test procedure, Scandinavian Journal of Statistics, 1979: https://www.jstor.org/stable/4615733",
    "Efron, Bootstrap methods: another look at the jackknife, Annals of Statistics, 1979: https://doi.org/10.1214/aos/1176344552",
    "Cameron, Gelbach, and Miller, Robust Inference With Multiway Clustering, Journal of Business & Economic Statistics, 2011: https://doi.org/10.1198/jbes.2010.07136",
    "Feng et al., Language-agnostic BERT Sentence Embedding, ACL, 2022: https://aclanthology.org/2022.acl-long.62/",
    "van der Lee et al., Best practices for the human evaluation of automatically generated text, INLG, 2019: https://aclanthology.org/W19-8643/",
    "Belz et al., Disentangling the Properties of Human Evaluation Methods, ACL, 2021: https://aclanthology.org/2021.acl-long.565/",
    "Pineau et al., Improving Reproducibility in Machine Learning Research, Journal of Machine Learning Research, 2021: https://www.jmlr.org/papers/v22/20-303.html",
    "Chroma documentation, Default Embedding Function: https://docs.trychroma.com/docs/embeddings/embedding-functions",
    "Sentence Transformers, all-MiniLM-L6-v2 model card: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2",
]


def _active_academic_sources(*, include_bertscore: bool) -> List[str]:
    """Return the source list for the metrics actually enabled in this run."""

    if include_bertscore:
        return list(ACADEMIC_SOURCES)
    return [source for source in ACADEMIC_SOURCES if "BERTScore" not in source]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate PSQ-SCO generated scenarios with ontology validation, scenario validation, and method comparison."
    )
    parser.add_argument("--ontology-root", type=Path, default=DEFAULT_ONTOLOGY_ROOT)
    parser.add_argument("--ontology-path", type=Path, default=DEFAULT_ONTOLOGY_PATH)
    parser.add_argument("--queries-dir", type=Path, default=DEFAULT_QUERY_DIR)
    parser.add_argument("--scenario-output-root", type=Path, default=DEFAULT_SCENARIO_OUTPUT_ROOT)
    parser.add_argument(
        "--input-dir",
        action="append",
        type=Path,
        default=[],
        help="Optional generated-output directory or JSONL file. Can be repeated. If omitted, scans --scenario-output-root.",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("output") / "three_layer_evaluation")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum scenario rows to load for smoke tests.")
    parser.add_argument("--include-progress-jsonl", action="store_true", help="Also scan progress.jsonl files.")
    parser.add_argument("--hermit-jar", type=Path, default=None, help="Optional HermiT reasoner jar path.")
    parser.add_argument(
        "--hermit-report",
        type=Path,
        default=DEFAULT_HERMIT_REPORT,
        help="Optional completed HermiT JSON report to import when a standalone HermiT jar is unavailable.",
    )
    parser.add_argument("--java", default="java", help="Java executable for optional HermiT run.")
    parser.add_argument("--list-input-files", action="store_true", help="Print discovered scenario JSONL files and exit.")
    parser.add_argument(
        "--paper-120-final",
        action="store_true",
        help="Evaluate the frozen final 120-case result files for 3 LLMs x 4 modes.",
    )
    parser.add_argument(
        "--paper-120-graph-walk-v1",
        action="store_true",
        help=(
            "Evaluate Conditions 1-3 from the frozen live-recovered set and replace "
            "Condition 4 with paper120_mode4_graph_walk_v1/20260723_030518."
        ),
    )
    parser.add_argument(
        "--manual-sample-size",
        type=int,
        default=24,
        help="Number of rows to export for stratified manual inspection.",
    )
    parser.add_argument(
        "--diversity-embedding-backend",
        choices=("hash", "auto", "sentence_transformers"),
        default="hash",
        help="Embedding backend for semantic diversity. Default is deterministic local hashing.",
    )
    parser.add_argument(
        "--diversity-embedding-model",
        default=None,
        help="Optional sentence-transformers model name for diversity embeddings when that backend is available.",
    )
    parser.add_argument(
        "--reuse-semantic-diversity-dir",
        type=Path,
        default=None,
        help=(
            "Reuse semantic_diversity.csv from a prior evaluation of the exact same scenario files. "
            "The evaluator verifies the frozen file manifest and embedding-model metadata."
        ),
    )
    parser.add_argument(
        "--enable-bertscore",
        action="store_true",
        help="Compute case-reference BERTScore semantic alignment. This can be slower and may require a local Hugging Face model cache.",
    )
    parser.add_argument(
        "--standard-metrics-only",
        action="store_true",
        help=(
            "Use the publication profile built around disclosed pass rates, exact-match controls, "
            "common-oracle P/R/F1, paired tests, Self-BLEU, and embedding diversity. BERTScore is disallowed."
        ),
    )
    parser.add_argument(
        "--smoke-report",
        action="store_true",
        help="Write a compact code-path verification report without frozen-paper claims.",
    )
    parser.add_argument(
        "--bertscore-model",
        default="distilbert-base-uncased",
        help="Transformer model for BERTScore. Use a cached local model for reproducible offline runs.",
    )
    parser.add_argument("--bertscore-lang", default="en", help="BERTScore language code.")
    parser.add_argument("--bertscore-batch-size", type=int, default=8, help="BERTScore CPU batch size.")
    parser.add_argument(
        "--bertscore-max-chars",
        type=int,
        default=1800,
        help="Maximum generated/reference text characters per scenario for BERTScore.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.standard_metrics_only and args.enable_bertscore:
        raise SystemExit("--standard-metrics-only cannot be combined with --enable-bertscore.")
    if args.paper_120_final and args.paper_120_graph_walk_v1:
        raise SystemExit(
            "--paper-120-final and --paper-120-graph-walk-v1 are mutually exclusive."
        )
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    roots = args.input_dir if args.input_dir else [args.scenario_output_root]
    if args.paper_120_final:
        scenario_files = final_paper_120_files()
    elif args.paper_120_graph_walk_v1:
        scenario_files = paper_120_graph_walk_v1_files()
    else:
        scenario_files = discover_scenario_files(roots, include_progress=args.include_progress_jsonl)
    if args.list_input_files:
        for path in scenario_files:
            print(path)
        return
    if not scenario_files:
        raise SystemExit("No scenario JSONL files found. Pass --input-dir or check --scenario-output-root.")

    records = load_jsonl_records(scenario_files, limit=args.limit)
    scores = score_records(records)
    ontology = validate_ontology(
        ontology_path=args.ontology_path,
        query_dir=args.queries_dir,
        records=records,
        hermit_jar=args.hermit_jar,
        hermit_report=args.hermit_report,
        java_executable=args.java,
    )

    score_rows = [score.as_dict() for score in scores]
    method_rows = method_summary(scores)
    model_method_rows = model_method_summary(scores)
    matrix_rows = model_method_matrix(scores)
    error_rows = error_analysis(scores)
    paper_error_rows = paper_labeled_error_analysis(scores)
    decision_rows = decision_summary(scores)
    model_decision_rows = model_method_decision_summary(scores)
    stats = paired_statistics(scores)
    condition_rows = condition_manifest_rows(scenario_files)
    dataset = dataset_description(records)
    matched_rows = matched_case_audit(scores)
    timing_rows = timing_analysis(scores)
    diversity_rows = diversity_analysis(scores)
    if args.reuse_semantic_diversity_dir:
        semantic_diversity_rows = _load_reusable_semantic_diversity(
            args.reuse_semantic_diversity_dir,
            scenario_files=scenario_files,
            expected_embedding_model=args.diversity_embedding_model,
        )
    else:
        semantic_diversity_rows = semantic_diversity_analysis(
            scores,
            embedding_backend=args.diversity_embedding_backend,
            embedding_model=args.diversity_embedding_model,
        )
    semantic_diversity_summary_rows = semantic_diversity_method_summary(semantic_diversity_rows)
    standard_rows = standard_metric_summary(scores, semantic_diversity_summary_rows)
    standard_error_rows = standard_error_analysis(scores)
    validity_registry_rows = metric_validity_registry()
    source_rows = source_linkage_audit(records)
    source_summary_rows = source_linkage_summary(source_rows)
    generation_integrity_rows = [
        {
            key: row.get(key)
            for key in (
                "source_file",
                "line_number",
                "case_id",
                "scenario_id",
                "model_key",
                "method",
                "condition_number",
                "condition_name",
                "used_live_llm",
                "used_fallback",
                "schema_safe_repair_used",
                "live_model_content_retained",
                "generation_integrity_status",
                "engine_validation_passed",
                "engine_validation_issue_count",
                "engine_validation_issues",
            )
        }
        for row in score_rows
    ]
    graph_walk_rows = [
        row
        for row in source_rows
        if row.get("method") == "ontology_text_rag"
    ]
    graph_walk_summary = {
        "experiment_variant": (
            "graph_walk_v1"
            if any(row.get("graph_walk_required") for row in graph_walk_rows)
            else "condition_4_without_declared_graph_walk"
        ),
        "condition_4_source_linkage": next(
            (
                row
                for row in source_summary_rows
                if row.get("method") == "ontology_text_rag"
            ),
            {},
        ),
        "condition_4_standard_metrics": next(
            (
                row
                for row in standard_rows
                if row.get("method") == "ontology_text_rag"
            ),
            {},
        ),
        "condition_4_dataset_profile": dataset.get("evaluated_generation_profile", {}),
    }
    if args.standard_metrics_only:
        bertscore_rows, bertscore_summary_rows = [], []
    else:
        bertscore_rows, bertscore_summary_rows = bertscore_alignment_analysis(
            scores,
            model_type=args.bertscore_model,
            lang=args.bertscore_lang,
            batch_size=args.bertscore_batch_size,
            max_chars=args.bertscore_max_chars,
            enabled=args.enable_bertscore,
        )
    manual_rows = manual_inspection_sample(scores, sample_size=args.manual_sample_size)
    active_sources = _active_academic_sources(include_bertscore=args.enable_bertscore)

    output_files: Dict[str, str] = {
        "ontology_validation_json": str(out_dir / "ontology_validation.json"),
        "scenario_scores_csv": str(out_dir / "scenario_scores.csv"),
        "method_summary_csv": str(out_dir / "method_summary.csv"),
        "model_method_summary_csv": str(out_dir / "model_method_summary.csv"),
        "model_method_matrix_csv": str(out_dir / "model_method_matrix.csv"),
        "error_analysis_csv": str(out_dir / "error_analysis.csv"),
        "error_analysis_paper_labels_csv": str(out_dir / "error_analysis_paper_labels.csv"),
        "paired_statistics_json": str(out_dir / "paired_statistics.json"),
        "condition_manifest_csv": str(out_dir / "condition_manifest.csv"),
        "dataset_description_json": str(out_dir / "dataset_description.json"),
        "dataset_sources_csv": str(out_dir / "dataset_sources.csv"),
        "matched_case_audit_csv": str(out_dir / "matched_case_audit.csv"),
        "timing_analysis_csv": str(out_dir / "timing_analysis.csv"),
        "diversity_analysis_csv": str(out_dir / "diversity_analysis.csv"),
        "semantic_diversity_csv": str(out_dir / "semantic_diversity.csv"),
        "semantic_diversity_method_summary_csv": str(out_dir / "semantic_diversity_method_summary.csv"),
        "standard_metric_summary_csv": str(out_dir / "standard_metric_summary.csv"),
        "metric_validity_registry_csv": str(out_dir / "metric_validity_registry.csv"),
        "standard_error_analysis_csv": str(out_dir / "standard_error_analysis.csv"),
        "scenario_decisions_csv": str(out_dir / "scenario_decisions.csv"),
        "decision_summary_csv": str(out_dir / "decision_summary.csv"),
        "model_method_decision_summary_csv": str(out_dir / "model_method_decision_summary.csv"),
        "source_linkage_audit_csv": str(out_dir / "source_linkage_audit.csv"),
        "source_linkage_summary_csv": str(out_dir / "source_linkage_summary.csv"),
        "generation_integrity_audit_csv": str(out_dir / "generation_integrity_audit.csv"),
        "graph_walk_exposure_audit_csv": str(out_dir / "graph_walk_exposure_audit.csv"),
        "graph_walk_summary_json": str(out_dir / "graph_walk_summary.json"),
        "manual_inspection_sample_csv": str(out_dir / "manual_inspection_sample.csv"),
        "metric_definitions_md": str(out_dir / "metric_definitions.md"),
        "research_paper_results_analysis_md": str(out_dir / "research_paper_results_analysis.md"),
        "evaluation_report_md": str(out_dir / "evaluation_report.md"),
        "run_metadata_json": str(out_dir / "run_metadata.json"),
    }
    if args.enable_bertscore:
        output_files["bertscore_scenario_alignment_csv"] = str(out_dir / "bertscore_scenario_alignment.csv")
        output_files["bertscore_method_summary_csv"] = str(out_dir / "bertscore_method_summary.csv")

    write_json(out_dir / "ontology_validation.json", ontology.as_dict())
    write_csv(out_dir / "scenario_scores.csv", score_rows)
    write_csv(out_dir / "method_summary.csv", method_rows)
    write_csv(out_dir / "model_method_summary.csv", model_method_rows)
    write_csv(out_dir / "model_method_matrix.csv", matrix_rows)
    write_csv(out_dir / "error_analysis.csv", error_rows)
    write_csv(out_dir / "error_analysis_paper_labels.csv", paper_error_rows)
    write_json(out_dir / "paired_statistics.json", stats)
    write_csv(out_dir / "condition_manifest.csv", condition_rows)
    write_json(out_dir / "dataset_description.json", dataset)
    write_csv(
        out_dir / "dataset_sources.csv",
        dataset.get("sources", [])
        or [
            {
                "status": "not_available_in_evaluated_input",
                "note": "No restored external research-corpus catalog was present in this evaluated input.",
            }
        ],
    )
    write_csv(out_dir / "matched_case_audit.csv", matched_rows)
    write_csv(out_dir / "timing_analysis.csv", timing_rows)
    write_csv(out_dir / "diversity_analysis.csv", diversity_rows)
    write_csv(out_dir / "semantic_diversity.csv", semantic_diversity_rows)
    write_csv(out_dir / "semantic_diversity_method_summary.csv", semantic_diversity_summary_rows)
    write_csv(out_dir / "standard_metric_summary.csv", standard_rows)
    write_csv(out_dir / "metric_validity_registry.csv", validity_registry_rows)
    write_csv(out_dir / "standard_error_analysis.csv", standard_error_rows)
    write_csv(
        out_dir / "scenario_decisions.csv",
        [
            {
                key: row.get(key)
                for key in (
                    "case_id",
                    "scenario_id",
                    "model_key",
                    "method",
                    "condition_number",
                    "condition_name",
                    "automated_decision",
                    "decision_scope",
                    "decision_policy_version",
                    "final_human_review_required",
                    "schema_safe_repair_used",
                    "live_model_content_retained",
                    "generation_integrity_status",
                    "engine_validation_passed",
                    "decision_reason_codes",
                    "revision_guidance",
                )
            }
            for row in score_rows
        ],
    )
    write_csv(out_dir / "decision_summary.csv", decision_rows)
    write_csv(out_dir / "model_method_decision_summary.csv", model_decision_rows)
    write_csv(out_dir / "source_linkage_audit.csv", source_rows)
    write_csv(out_dir / "source_linkage_summary.csv", source_summary_rows)
    write_csv(out_dir / "generation_integrity_audit.csv", generation_integrity_rows)
    write_csv(out_dir / "graph_walk_exposure_audit.csv", graph_walk_rows)
    write_json(out_dir / "graph_walk_summary.json", graph_walk_summary)
    if args.enable_bertscore:
        write_csv(out_dir / "bertscore_scenario_alignment.csv", bertscore_rows)
        write_csv(out_dir / "bertscore_method_summary.csv", bertscore_summary_rows)
    write_csv(out_dir / "manual_inspection_sample.csv", manual_rows)
    (out_dir / "metric_definitions.md").write_text(
        metric_definitions_markdown(include_bertscore=args.enable_bertscore),
        encoding="utf-8",
    )
    if args.smoke_report:
        (out_dir / "research_paper_results_analysis.md").write_text(
            "# Research-paper analysis not produced for this smoke run\n\n"
            "This run verifies the portable four-mode code path on a minimal matched case. "
            "It is not the frozen paper experiment and must not be used for paper-level "
            "method-performance or statistical claims. See `evaluation_report.md` for the "
            "bounded smoke-test results.\n",
            encoding="utf-8",
        )
    else:
        write_research_analysis(
            out_dir / "research_paper_results_analysis.md",
            method_rows=method_rows,
            model_matrix=matrix_rows,
            condition_rows=condition_rows,
            dataset=dataset,
            matched_rows=matched_rows,
            timing_rows=timing_rows,
            diversity_rows=diversity_rows,
            semantic_diversity_rows=semantic_diversity_rows,
            semantic_diversity_summary_rows=semantic_diversity_summary_rows,
            standard_metric_rows=standard_rows,
            metric_validity_rows=validity_registry_rows,
            decision_summary_rows=decision_rows,
            model_method_decision_rows=model_decision_rows,
            source_linkage_rows=source_rows,
            source_linkage_summary_rows=source_summary_rows,
            paired_stats=stats,
            bertscore_rows=bertscore_rows,
            bertscore_summary_rows=bertscore_summary_rows,
            sources=active_sources,
        )
    write_json(
        out_dir / "run_metadata.json",
        {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(),
            "ontology_root": str(args.ontology_root),
            "ontology_path": str(args.ontology_path),
            "queries_dir": str(args.queries_dir),
            "hermit_report": str(args.hermit_report) if args.hermit_report else None,
            "scenario_roots": [str(root) for root in roots],
            "scenario_file_count": len(scenario_files),
            "scenario_files": [str(path) for path in scenario_files],
            "scenario_record_count": len(records),
            "scored_record_count": len(scores),
            "paper_120_final": bool(args.paper_120_final),
            "paper_120_graph_walk_v1": bool(args.paper_120_graph_walk_v1),
            "comparison_variant": (
                "graph_walk_v1"
                if args.paper_120_graph_walk_v1
                else "original_four_condition"
            ),
            "manual_sample_size": args.manual_sample_size,
            "diversity_embedding_backend": args.diversity_embedding_backend,
            "diversity_embedding_model": args.diversity_embedding_model,
            "semantic_diversity_reused_from": (
                str(args.reuse_semantic_diversity_dir) if args.reuse_semantic_diversity_dir else None
            ),
            "standard_metrics_only": bool(args.standard_metrics_only),
            "smoke_report": bool(args.smoke_report),
            "evaluation_profile": "standard_no_bertscore" if args.standard_metrics_only else "extended_optional",
            **(
                {}
                if args.standard_metrics_only
                else {
                    "bertscore_enabled": bool(args.enable_bertscore),
                    "bertscore_model": args.bertscore_model,
                    "bertscore_lang": args.bertscore_lang,
                    "bertscore_batch_size": args.bertscore_batch_size,
                    "bertscore_max_chars": args.bertscore_max_chars,
                }
            ),
            "conformance_weights": CONFORMANCE_WEIGHTS,
            "condition_names": METHOD_LABELS,
            "condition_implementation_notes": METHOD_IMPLEMENTATION_NOTES,
            "automated_decision_policy": "technical_gate_v1; non-compensatory technical triage only",
            "source_similarity_policy": "not calculated unless scenario-specific retrieval/query or claim-source evidence is exported",
            "academic_sources": active_sources,
            "output_files": output_files,
        },
    )
    write_markdown_report(
        out_dir / "evaluation_report.md",
        ontology=ontology,
        scenario_count=len(scores),
        method_rows=method_rows,
        model_matrix=matrix_rows,
        error_rows=error_rows,
        paper_error_rows=paper_error_rows,
        stats=stats,
        condition_rows=condition_rows,
        dataset=dataset,
        matched_rows=matched_rows,
        timing_rows=timing_rows,
        diversity_rows=diversity_rows,
        semantic_diversity_rows=semantic_diversity_rows,
        semantic_diversity_summary_rows=semantic_diversity_summary_rows,
        standard_metric_rows=standard_rows,
        metric_validity_rows=validity_registry_rows,
        decision_summary_rows=decision_rows,
        model_method_decision_rows=model_decision_rows,
        source_linkage_rows=source_rows,
        source_linkage_summary_rows=source_summary_rows,
        bertscore_rows=bertscore_rows,
        bertscore_summary_rows=bertscore_summary_rows,
        manual_sample_path=output_files["manual_inspection_sample_csv"],
        output_files=output_files,
        sources=active_sources,
        smoke_report=args.smoke_report,
    )

    print(
        {
            "run_id": run_id,
            "out_dir": str(out_dir),
            "scenario_file_count": len(scenario_files),
            "scenario_record_count": len(records),
            "method_count": len(method_rows),
            "report": output_files["evaluation_report_md"],
        }
    )


def _load_reusable_semantic_diversity(
    prior_dir: Path,
    *,
    scenario_files: List[Path],
    expected_embedding_model: str | None,
) -> List[Dict[str, Any]]:
    """Load collection metrics only after verifying the identical frozen inputs."""

    metadata_path = prior_dir / "run_metadata.json"
    diversity_path = prior_dir / "semantic_diversity.csv"
    if not metadata_path.exists() or not diversity_path.exists():
        raise SystemExit(
            f"Cannot reuse diversity: expected {metadata_path} and {diversity_path}."
        )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    prior_files = {
        str(Path(path).resolve()).lower() for path in metadata.get("scenario_files", [])
    }
    current_files = {str(path.resolve()).lower() for path in scenario_files}
    if prior_files != current_files:
        raise SystemExit("Cannot reuse diversity: the prior and current scenario-file manifests differ.")
    prior_model = metadata.get("diversity_embedding_model")
    if expected_embedding_model and prior_model != expected_embedding_model:
        raise SystemExit(
            "Cannot reuse diversity: embedding model differs "
            f"(prior={prior_model!r}, requested={expected_embedding_model!r})."
        )
    with diversity_path.open("r", encoding="utf-8", newline="") as handle:
        rows = [_coerce_csv_row(row) for row in csv.DictReader(handle)]
    expected_pairs = 3 * 4
    if len(rows) != expected_pairs or sum(int(row.get("n") or 0) for row in rows) != 1440:
        raise SystemExit(
            "Cannot reuse diversity: expected 12 model-condition rows totaling 1,440 scenarios."
        )
    return rows


def _coerce_csv_row(row: Dict[str, str]) -> Dict[str, Any]:
    numeric_ints = {"condition_number", "n"}
    numeric_floats = {
        "mean_pairwise_cosine_similarity",
        "embedding_diversity",
        "self_bleu",
        "self_bleu_diversity",
    }
    payload: Dict[str, Any] = dict(row)
    for key in numeric_ints:
        if payload.get(key) not in (None, ""):
            payload[key] = int(payload[key])
    for key in numeric_floats:
        if payload.get(key) not in (None, ""):
            payload[key] = float(payload[key])
    return payload


if __name__ == "__main__":
    main()
