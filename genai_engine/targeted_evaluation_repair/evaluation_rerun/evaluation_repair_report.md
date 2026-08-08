# Targeted PSQ-SCO Evaluation Repair

## Scope

This rerun evaluates the frozen 1,440 stored live outputs used by the manuscript. It does not call a generation model and does not substitute the later Graph-Walk v1 ablation for the paper's protected frozen experiment.

## Metric contract

- J: JSON parse/object validity (validation component; higher is better).
- Schema completeness: required executable fields (validation component; higher is better).
- A: exact adherence to eight frozen case controls (validation component; higher is better).
- P, R, F1_req: method-conditioned required-concept diagnostic. The reference vocabulary may differ by method, so this is a mechanism audit rather than a cross-method accuracy claim.
- G: presence of six source/provenance fields. It does not prove that a link resolves or that a source supports a generated claim.
- T: fraction of a method's declared source, dataset, provenance-record, and ordered-context links that resolve to the correct frozen local record. T is not applicable when a method declares no trace links.
- E: contradiction rate; lower is better.
- Ontology scope: project-defined trace/control coverage, not OWL entailment accuracy.
- OCI_eq: equal-weight secondary descriptive index over J, A, F1_req, G, and 1-E. It is not a quality percentage, threshold, or learner-effect measure.
- Claim-source support/entailment: not evaluated.

## Condition results

| Condition | J | A | P | R | F1_req | G | T | E | Ont. scope | OCI_eq | OCI_legacy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Prompt-Only Generation | 1.000 | 1.000 | 0.382 | 0.795 | 0.512 | 0.481 | n/a | 0.000 | 0.400 | 0.798526 | 0.774106 |
| Text-RAG Generation | 1.000 | 1.000 | 0.318 | 0.779 | 0.448 | 0.782 | 0.928 | 0.000 | 0.400 | 0.846074 | 0.818472 |
| Ontology-Derived Structured Prompting RAG | 1.000 | 1.000 | 0.508 | 0.596 | 0.545 | 1.000 | 0.996 | 0.000 | 0.900 | 0.908950 | 0.886187 |
| Ontology-to-Text Vector RAG | 1.000 | 1.000 | 0.270 | 0.809 | 0.399 | 1.000 | 0.968 | 0.003 | 0.865 | 0.879257 | 0.849488 |

## Model stability

| Model | Condition | OCI_eq | Eq. rank | OCI_legacy | Legacy rank | Reversal |
|---|---|---:|---:|---:|---:|:---:|
| mistral_7b | Prompt-Only Generation | 0.775450 | 4 | 0.747160 | 4 | no |
| mistral_7b | Text-RAG Generation | 0.844625 | 3 | 0.816406 | 3 | no |
| mistral_7b | Ontology-Derived Structured Prompting RAG | 0.901919 | 1 | 0.877399 | 1 | no |
| mistral_7b | Ontology-to-Text Vector RAG | 0.878776 | 2 | 0.848470 | 2 | no |
| qwen2_5_7b | Prompt-Only Generation | 0.810020 | 4 | 0.787525 | 4 | no |
| qwen2_5_7b | Text-RAG Generation | 0.850192 | 3 | 0.823365 | 3 | no |
| qwen2_5_7b | Ontology-Derived Structured Prompting RAG | 0.903518 | 1 | 0.879398 | 1 | no |
| qwen2_5_7b | Ontology-to-Text Vector RAG | 0.878225 | 2 | 0.847781 | 2 | no |
| qwen3_8b | Prompt-Only Generation | 0.810107 | 4 | 0.787633 | 4 | no |
| qwen3_8b | Text-RAG Generation | 0.843406 | 3 | 0.815646 | 3 | no |
| qwen3_8b | Ontology-Derived Structured Prompting RAG | 0.921412 | 1 | 0.901765 | 1 | no |
| qwen3_8b | Ontology-to-Text Vector RAG | 0.880769 | 2 | 0.852211 | 2 | no |

## Weight sensitivity

10,000 nonnegative weight vectors summing to one were sampled with seed 20260723 from Dirichlet(1,1,1,1,1) via normalized exponential draws.

| Condition | First-place proportion |
|---|---:|
| Prompt-Only Generation | 0.000000 |
| Text-RAG Generation | 0.000000 |
| Ontology-Derived Structured Prompting RAG | 1.000000 |
| Ontology-to-Text Vector RAG | 0.000000 |

Pairwise order stability relative to the equal-weight order:

- `prompt_only_vs_prompt_rag` (equal-weight order `prompt_rag>prompt_only`): 0.827700
- `prompt_only_vs_ontology_prompt_rag` (equal-weight order `ontology_prompt_rag>prompt_only`): 1.000000
- `prompt_only_vs_ontology_text_rag` (equal-weight order `ontology_text_rag>prompt_only`): 0.819300
- `prompt_rag_vs_ontology_prompt_rag` (equal-weight order `ontology_prompt_rag>prompt_rag`): 1.000000
- `prompt_rag_vs_ontology_text_rag` (equal-weight order `ontology_text_rag>prompt_rag`): 0.807400
- `ontology_prompt_rag_vs_ontology_text_rag` (equal-weight order `ontology_prompt_rag>ontology_text_rag`): 1.000000

## Traceability findings

- Applicable outputs: 946/1440.
- Outputs with unresolved ordered/context targets: 164.
- Outputs with any trace diagnostic: 344.
- Missing canonical links: 0.
- Wrong/mismatched ordered-context links: 447.
- Duplicate/conflicting declarations: 521.
- T is conditional resolution; G remains the separate completeness diagnostic.
- Claim-source support remains not evaluated.

## Technical decisions and generation integrity

- ACCEPTED: 1439
- REJECT_REGENERATE: 1
- Stored live-call records: 1440
- Stored fallback records: 0
- Live calls finalized with deterministic schema-safe repair: 318
- Live model content retained in finalized scenario: 1122

The zero fallback count is not equivalent to unmodified live-model content. Schema-safe repairs are therefore reported separately.

## Five matched cases

- PSQ-SCO-120-053 / mistral_7b: representative_median_performing — Pair mean OCI_eq is nearest the median across complete case-model pairs (global median=0.858676).
- PSQ-SCO-120-023 / qwen3_8b: ontology_to_text_contradiction — The frozen ontology-to-text output triggered the deterministic contradiction rule.
- PSQ-SCO-120-002 / mistral_7b: external_rag_returned_no_text — The Text-RAG condition stored no retrieved external context for this matched pair.
- PSQ-SCO-120-070 / qwen2_5_7b: legitimate_communication — A real/legitimate case nearest the median of eligible legitimate pairs.
- PSQ-SCO-120-064 / qwen3_8b: clearest_precision_recall_tradeoff — Contains the largest remaining absolute method-conditioned precision/recall gap (0.828571, method=ontology_text_rag).

## Interpretation boundary

The component metrics are the primary scientific results. OCI_eq only summarizes the five legacy components under equal nominal weights because no empirically validated differential weighting model is available. Neither the component diagnostics nor OCI_eq establish learner gains, expert-rated realism, or universal scenario quality.
