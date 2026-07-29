# Dual-Profile Evaluation Metric Framework

## Purpose

This document restores the earlier PersonaShield Quest weighted conformance metric while improving its methodological presentation with standard-form companion metrics. It applies to the completed `120 cases x 4 methods x 3 local LLMs = 1,440` live-output experiment.

The framework deliberately separates two questions:

1. **Did the finalized scenario satisfy comparable technical and case requirements?** Use the standard-form metric profile.
2. **How completely did the whole PSQ generation mechanism expose case, concept, grounding, and contradiction controls?** Use the restored PSQ mechanism-aware conformance index as a secondary summary.

The weighted score is therefore restored, but it is not presented as a universal standard, a percentage of educational quality, or a replacement for the component metrics.

## Profile A: Standard-Form Comparable Metrics

| Metric | Formula or rule | Construct | Why it is used | Interpretation | Status |
|---|---|---|---|---|---|
| JSON parse pass | `mean(I[parseable scenario object])` | Technical executability | A game cannot inspect a record that cannot be parsed. | `1.00` means all finalized records parsed; it does not mean all content is good. | Standard binary pass-rate form |
| Exact eight-control pass | `mean(I[all 8 controls match])` | Experimental adherence | The same role, age, macro/micro stage, channel, variant, difficulty, attack type, and safe response must be preserved across methods. | One mismatched control makes that row fail. | Standard exact-match form applied to a PSQ contract |
| Common precision | `TP/(TP+FP)` | Purity of detected case labels | Shows whether detected closed-vocabulary labels belong to the case-derived oracle. | Higher means fewer extra labels under the disclosed extractor. | Standard formula; project-specific oracle |
| Common recall | `TP/(TP+FN)` | Coverage of required case labels | Shows whether required closed-vocabulary labels were recovered. | Higher means fewer required labels were missed. | Standard formula; project-specific oracle |
| Common F1 | `2PR/(P+R)` | Balance of precision and recall | Prevents interpretation from relying on precision or recall alone. | High F1 means strong closed-label adherence, not human-rated prose quality. | Standard formula; project-specific oracle |
| Contradiction-free pass | `mean(I[no disclosed rule fires])` | Bounded structural and defensive safety | Prevents aggregate results from hiding wrong attack/channel combinations, fake/real inconsistency, or unsafe actions. | `1.00` means no implemented rule fired; unknown harms can remain. | Standard binary pass-rate form; PSQ rule set |
| LaBSE embedding diversity | `1 - mean cosine(E_i,E_j)` for unordered pairs | Relative semantic dispersion | Meaning-level similarity can remain high even when wording changes. | Higher means more semantic dispersion within the compared set. No universal cutoff is used. | Literature-grounded diagnostic |
| Self-BLEU | Mean BLEU of each output against the remaining outputs | Relative lexical redundancy | Detects repeated wording and template-like collapse across 120 outputs. | Lower means less lexical repetition. It is not a quality score. | Established text-generation diversity metric |

Precision, recall, and F1 follow standard definitions, but their scientific meaning depends on the reference set. Here the reference is one method-invariant, automatically constructed case oracle. Prompt-only is not the reference answer and is not expected to equal `1.0` automatically. Sokolova and Lapalme explain why metric selection and interpretation depend on task structure and class behavior.

Self-BLEU comes from text-generation benchmarking practice, including Texygen. Tevet and Berant show that automatic diversity metrics have important limitations and should be interpreted relatively and supported by human judgment. LaBSE supplies the frozen sentence representation used for the embedding-dispersion calculation.

## Profile B: Restored PSQ Mechanism-Aware Conformance Index

The previous score is restored unchanged:

```text
C_PSQ = 0.20 J + 0.25 A + 0.25 F_legacy + 0.20 G + 0.10 (1 - E)
```

where all components are normalized to `[0,1]`:

| Component | Weight | Meaning | Original design reason | Methodological caution |
|---|---:|---|---|---|
| `J`: JSON validity | 0.20 | Final record parses and contains an inspectable scenario object. | Executability is necessary for deployment and automated evaluation. | Parsing does not establish content quality. |
| `A`: control adherence | 0.25 | Fraction of frozen case controls preserved. | Case fidelity is central to a matched scenario-generation experiment. | Fractional adherence can hide which control failed; exact-eight pass is reported beside it. |
| `F_legacy`: required-concept F1 | 0.25 | Original required-concept balance. | Concept coverage was treated as equally central to case adherence. | The legacy reference can include ontology packet/provenance terms unavailable to other methods, so it is not a neutral cross-method standard. |
| `G`: grounding completeness | 0.20 | Fraction of expected evidence and provenance fields present. | Traceability is central to the ontology/RAG engineering contribution. | Prompt-only lacks traces by design; trace presence does not prove source entailment. |
| `1-E`: non-contradiction | 0.10 | Complement of the bounded contradiction rate. | Safety consistency must remain visible in the compact summary. | The small weight does not make safety unimportant; contradiction counts are reported separately and should route to review. |

### What justifies the coefficients?

The exact numbers are **not coefficients imported from another phishing study and are not learned from the current 120 cases**. They encode the ordering used by the earlier PSQ evaluator: case adherence and concept coverage receive the largest shares; technical executability and trace completeness receive the next shares; contradiction status remains a separately reported bounded check.

Restoring the formula preserves comparability with earlier PSQ reports. It does not convert those design choices into empirical constants. The OECD/JRC handbook on composite indicators supports defining a theoretical framework, normalizing components, disclosing weights and aggregation, returning to component data, and conducting uncertainty/sensitivity analysis. It does not validate the PSQ values `0.20`, `0.25`, and `0.10`.

Accordingly:

- call `C_PSQ` a **project-defined mechanism-aware conformance index**;
- never call it a standardized quality percentage;
- always display its five components;
- always display the method-invariant standard profile beside it;
- do not use it alone to claim the best pedagogy, realism, usability, or learner outcome;
- calibrate future weights using independent expert ratings or learner outcomes, with held-out testing.

## Current All-Live Results Under Both Profiles

| Method | Restored PSQ index | JSON pass | Exact 8 controls | Common P | Common R | Common F1 | Contradiction-free | LaBSE diversity | Self-BLEU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Prompt only | 0.7741 | 100.00% | 100.00% | 0.9375 | 1.0000 | 0.9667 | 100.00% | 0.1865 | 0.8846 |
| Prompt + external RAG | 0.8181 | 100.00% | 98.89% | 0.9389 | 0.9984 | 0.9666 | 100.00% | 0.2289 | 0.8106 |
| Ontology packet + prompt + RAG | 0.8860 | 100.00% | 99.44% | 0.9382 | 0.9985 | 0.9662 | 100.00% | 0.2339 | 0.7906 |
| Ontology text + prompt + RAG | 0.8491 | 100.00% | 98.61% | 0.9392 | 0.9976 | 0.9663 | 99.72% | 0.2307 | 0.8059 |

The restored index ranks ontology packet highest because the index explicitly rewards ontology/provenance mechanism coverage and uses method-conditioned legacy concept terms. The method-invariant common F1 does not show a significant method difference: the case-level Friedman test gives `p=0.1272`, and no Holm-adjusted pairwise contrast is significant. Both statements are true because the profiles measure different constructs.

## Statistical Interpretation

The frozen case is the inferential unit (`n=120`). Each method's value is averaged across the three LLMs within each case before the primary repeated-measures test.

- Friedman tests the four matched method conditions without assuming normality.
- Wilcoxon signed-rank tests examine paired post-hoc contrasts.
- Holm correction controls family-wise error across six comparisons.
- A 5,000-resample case bootstrap reports confidence intervals.
- Non-zero difference counts and ties must accompany rank-biserial effects because 110-116 cases are tied in several contrasts.

These tests apply to the method-invariant common F1, not to a claim that the weighted PSQ index is a validated latent quality construct.

## Ground Truth and Validation Boundary

| Construct | Available reference | Valid claim | Not established |
|---|---|---|---|
| Ontology consistency | HermiT report | Formal consistency for PSQ-SCO v9.1 under the reported reasoner | Completeness of all cybersecurity knowledge |
| Competency questions | Expected ASK booleans | Eight executable CQ validation checks pass | Exhaustive ontology validation |
| Case controls | Frozen 120-case specification | Structured task adherence | Human quality or realism |
| Common concept labels | Automatic closed-label oracle | Comparable technical label adherence | Human-authored semantic ground truth |
| Provenance trace | Stored trace fields | Presence of declared audit metadata | Source entailment or truth |
| Diversity | LaBSE and Self-BLEU | Relative within-study dispersion/redundancy | Universal diversity sufficiency |
| Pedagogy, realism, usability, ethics | No completed human ratings | No conclusion yet | Human acceptability or learner benefit |

The exported 24-row manual-inspection sheet remains unfilled. Human-rated claims require blinded experts, a predefined rubric, inter-rater reliability, adjudication, and a separate learner study.

## Recommended Reporting Language

> The evaluation reports a dual metric profile. Standard-form measures provide the primary comparable evidence: binary JSON and contradiction pass rates, exact eight-control adherence, method-invariant precision/recall/F1, and established relative diversity diagnostics. The earlier PSQ weighted conformance index is retained as a secondary mechanism-aware summary for continuity. Its coefficients encode the original design priorities and are not empirically calibrated constants. Consequently, the weighted index is interpreted only with its component scores and does not replace human evaluation or learner-outcome validation.

## References

1. Sokolova, M., and Lapalme, G. (2009). A systematic analysis of performance measures for classification tasks. *Information Processing & Management*, 45(4), 427-437. https://doi.org/10.1016/j.ipm.2009.03.002
2. Zhu, Y., et al. (2018). Texygen: A Benchmarking Platform for Text Generation Models. *SIGIR 2018*. https://discovery.ucl.ac.uk/10066104/
3. Tevet, G., and Berant, J. (2021). Evaluating the Evaluation of Diversity in Natural Language Generation. *EACL 2021*, 326-346. https://doi.org/10.18653/v1/2021.eacl-main.25
4. Feng, F., et al. (2022). Language-agnostic BERT Sentence Embedding. *ACL 2022*, 878-891. https://doi.org/10.18653/v1/2022.acl-long.62
5. Friedman, M. (1937). The Use of Ranks to Avoid the Assumption of Normality Implicit in the Analysis of Variance. *JASA*, 32(200), 675-701. https://doi.org/10.1080/01621459.1937.10503522
6. Wilcoxon, F. (1945). Individual Comparisons by Ranking Methods. *Biometrics Bulletin*, 1(6), 80-83. https://doi.org/10.2307/3001968
7. Holm, S. (1979). A Simple Sequentially Rejective Multiple Test Procedure. *Scandinavian Journal of Statistics*, 6(2), 65-70. https://www.jstor.org/stable/4615733
8. Efron, B. (1979). Bootstrap Methods: Another Look at the Jackknife. *The Annals of Statistics*, 7(1), 1-26. https://doi.org/10.1214/aos/1176344552
9. OECD/European Union/EC-JRC. (2008). *Handbook on Constructing Composite Indicators: Methodology and User Guide*. OECD Publishing. https://doi.org/10.1787/9789264043466-en

Conference proceedings do not have journal quartiles. Journal quartiles vary by database, subject category, and year and must be verified in the exact indexing edition used for publication.
