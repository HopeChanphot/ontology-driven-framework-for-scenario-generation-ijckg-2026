# Weighting, Qualifier, and Decision Framework for PersonaShield Quest Scenario Evaluation

## Purpose Of Weighting

The PCUE weighting framework combines four top-level scenario-quality criteria into a final weighted score for game-scenario validation: Pedagogical Quality, Cybersecurity Realism, Usability / Game Clarity, and Ethical Safety.

## Why Fixed Weights Are Only A Phase 1 Baseline

The initial PCUE weights are used as an expert-informed baseline because the first version of the evaluation engine does not yet have sufficient play-testing data to estimate empirical weights. Pedagogical Quality and Cybersecurity Realism are prioritized because they correspond directly to the game's primary learning goals: improving cybersecurity awareness and supporting realistic social-engineering threat recognition. Usability receives a smaller but still important weight because the scenario must be playable and understandable. Ethical Safety is treated both as a weighted criterion and as a veto criterion because a scenario with harmful or discriminatory content cannot be accepted even if other dimensions score highly.

## Baseline PCUE Weights

```text
Pedagogical Quality      = 0.40
Cybersecurity Realism    = 0.35
Usability / Game Clarity = 0.15
Ethical Safety           = 0.10
```

The final weighted score is:

```text
FWS = w_P x P + w_C x C + w_U x U + w_E x E
```

## Rationale For Each Weight

Pedagogical Quality receives the largest weight because the scenario is intended to teach. Cybersecurity Realism is nearly as important because unrealistic phishing, smishing, or vishing scenarios can teach the wrong threat model. Usability / Game Clarity receives a smaller but meaningful weight because a scenario must be playable. Ethical Safety receives both a weight and a veto because unsafe content cannot be accepted.

## Why Adaptive Weights Are More Principled

Fixed weights are transparent but arbitrary unless empirically justified. Adaptive weights become more principled once play-testing data can show which scenario qualities predict normalized learning gain.

## Phase 2 Regression-Derived Weights

Once at least 30 complete play-testing records are available, the system can estimate empirical weights using normalized learning gain as the outcome variable. In the long term, a Personalized Calibration Network can be used to learn player- or judge-specific calibration weights, following the logic of multidimensional calibrated rubric evaluation.

Required play-testing fields include scenario ID, participant ID, pre-test score, post-test score, PCUE scores, macro-stage, micro-stage, role, age group, channel, and variant.

## Phase 3 Personalized Calibration Network Future Extension

Phase 3 is represented in code by `PersonalizedCalibrationNetworkWeights`. It is intentionally a placeholder until expert ratings, learner outcomes, and judge-score distributions are available. The planned inputs are criterion-level judge distributions, human expert ratings, normalized learning gain, player proficiency level, macro-stage, micro-stage, role, and age group.

The initial PCUE weights are used as an expert-informed Phase 1 baseline because the current evaluation engine does not yet have sufficient play-testing data to estimate empirical weights. Pedagogical Quality and Cybersecurity Realism are prioritized because they correspond directly to the game's primary learning goals: cybersecurity awareness and realistic social-engineering threat recognition. After at least 30 complete play-testing records are available, Phase 2 regression-derived weights can be estimated using normalized learning gain as the outcome variable. In the long term, Phase 3 will support a Personalized Calibration Network inspired by multidimensional calibrated rubric evaluation.

## Qualifier Interval System

The revised evaluation engine uses qualifier intervals to make scenario scores interpretable and actionable. Instead of binary 0/1 judgments, each criterion is mapped to a five-level scale: Excellent, Good, Adequate, Poor, and Fail. This allows the engine to explain how a scenario should be improved. For example, a Pedagogical Quality score of 0.4733 is classified as Poor and triggers specific revision guidance related to learning-objective scaffolding, Bloom-level application, consequence feedback, and wrong-choice explanations.

```text
0.85-1.00 = Excellent
0.70-0.84 = Good
0.50-0.69 = Adequate
0.25-0.49 = Poor
0.00-0.24 = Fail
```

## Accept / Minor Revision / Major Revision / Reject Decision Framework

The revised validation pipeline also introduces a complete decision state machine: Accepted, Minor Revision, Major Revision, and Reject/Regenerate. A scenario is accepted only when its final weighted score reaches the acceptance threshold and no criterion-level veto applies. This prevents infinite revision loops and ensures that high overall scores cannot hide critical failures in ethical safety, cybersecurity realism, pedagogy, or usability.

```text
FWS >= 0.75          -> ACCEPTED
0.60 <= FWS < 0.75  -> MINOR_REVISION
0.40 <= FWS < 0.60  -> MAJOR_REVISION
FWS < 0.40          -> REJECT_REGENERATE
```

## Criterion-Level Veto Rule

Even when FWS is high, a scenario cannot be accepted if a critical top-level criterion is dangerously low. Ethical Safety <= 0.25 immediately rejects the scenario. Pedagogical Quality or Cybersecurity Realism <= 0.25 downgrades at least to Major Revision. Usability / Game Clarity <= 0.25 downgrades at least to Minor or Major Revision depending on FWS.

## Low Pedagogical Quality

A low Pedagogical Quality score means the scenario may be safe and realistic but not instructionally effective. For example:

```text
Pedagogical Quality = 0.4733
Qualifier = Poor
Action = Significant rewrite
Revision guidance:
- Add explicit learning objective.
- Add Bloom Level 3+ application/analysis action.
- Add consequence feedback.
- Add LO-linked hint.
- Improve wrong-choice explanations.
```

## High Ethical Safety

A high Ethical Safety score should be reported clearly:

```text
Ethical Safety = 0.92
Qualifier = Excellent
Interpretation = The scenario avoids discriminatory wording, harmful operational detail, and unsafe instruction.
Action = No ethical revision needed.
```

Ethical Safety can be strong while Pedagogical Quality is weak. This means the scenario is safe but not yet instructionally effective.

## Example Interpretation

```text
Final weighted score:
FWS = w_P x P + w_C x C + w_U x U + w_E x E

Decision:
- ACCEPTED only if FWS >= 0.75 and no criterion-level veto applies.
- MINOR_REVISION if 0.60 <= FWS < 0.75 or if a minor veto applies.
- MAJOR_REVISION if 0.40 <= FWS < 0.60 or if a major criterion fails.
- REJECT_REGENERATE if FWS < 0.40 or Ethical Safety <= 0.25.
```

## References To Verify Before Publication

- Hashemi et al. (2024). LLM-Rubric: A Multidimensional, Calibrated Approach to Automated Evaluation of Natural Language Texts. ACL 2024.
- Adaptive feedback and serious-game validation literature on learner interaction trajectories.
- ML-based adaptive feedback literature using pre-test, post-test, and normalized learning gain.
- LLM-as-judge bias literature on multi-judge evaluation, self-judge avoidance, and agreement statistics.
