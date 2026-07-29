# PersonaShield Quest v4.1 Engine

This package generates the new stage-aware scenario library for PersonaShield Quest.

## What v4.1 now defines

- 5 occupation role types: `IT`, `FINANCE`, `HR`, `MANAGEMENT`, `OTHER`
- 9 learner stages:
  - `BEGINNER_INTRODUCTORY`
  - `BEGINNER_DEVELOPING`
  - `BEGINNER_ADVANCED`
  - `INTERMEDIATE_INTRODUCTORY`
  - `INTERMEDIATE_DEVELOPING`
  - `INTERMEDIATE_ADVANCED`
  - `EXPERT_INTRODUCTORY`
  - `EXPERT_DEVELOPING`
  - `EXPERT_ADVANCED`
- 5 age groups
- 3 channels: `sms`, `email`, `voice`
- 2 content variants: `fake`, `real`
- 2 production retrieval modes:
  - `THAI_LOCAL`
  - `ENGLISH_GLOBAL`
- Formal placement-test scoring bands
- Formal training-loop and mastery-loop metadata
- Regression policy metadata for later DDA/game-core integration

## Content count

Per retrieval mode, per LLM:

`5 roles × 9 stages × 5 age groups × 3 channels × 2 variants = 1,350 scenarios`

If you generate both `THAI_LOCAL` and `ENGLISH_GLOBAL`, that doubles the total.

## Main files

- `config.py` — stage ladder, role blueprints, counts, placement config, loop config
- `schemas.py` — bundle/data models
- `game_system.py` — placement scoring and stage-transition helpers
- `export_game_config.py` — writes JSON config for Godot/runtime use
- `generate_scenarios.py` — main generator
- `combine_bundles.py` — merges bundle JSONs into one scenario pool
- `prompt_engine.py` — persona/scenario prompts
- `rag_engine.py` — metadata-aware retrieval
- `validator.py` — schema/content checks

## Dry run

```bash
python generate_scenarios.py --dry-run --skip-rag --role HR --stage BEGINNER_INTRODUCTORY --age-group 22_35 --retrieval-mode THAI_LOCAL --llm gpt_nano
```

## Full generation for one retrieval mode

```bash
python generate_scenarios.py --retrieval-mode THAI_LOCAL
```

## Full generation for both retrieval modes

```bash
python generate_scenarios.py
```

## Export game-system JSON

```bash
python export_game_config.py
```

## Combine bundles

```bash
python combine_bundles.py
```

## Evaluate scenario pool

Research-quality open-weight profile:

```bash
python evaluate_scenarios.py --scenario-pool scenario_pool/scenario_pool.json --judge-profile open_weight_research --disable-paid-judges --out-dir evaluation_output/open_weight_layer2_eval
```

Low-spec local preliminary profile:

```bash
python evaluate_scenarios.py --scenario-pool scenario_pool/scenario_pool.json --judge-profile local_low_spec --disable-paid-judges --out-dir evaluation_output/local_low_spec_eval
```

Dry-run judge selection without evaluating scenarios:

```bash
python evaluate_scenarios.py --scenario-pool scenario_pool/scenario_pool.json --judge-profile open_weight_research --disable-paid-judges --dry-run-judges
```

By default, the evaluator remains cost-free and uses deterministic judge-shaped proxy scoring. To call configured local/open-access endpoints, add `--run-live-judges`; failed live judge calls fall back to the deterministic proxy and record the error in judge metadata.

The evaluator preserves the older Layer 1/Layer 2 CSV outputs and adds reviewer-responsive fields such as `final_weighted_score`, `final_decision`, `criterion_qualifiers`, `revision_guidance`, `judge_metadata`, `needs_human_review`, and reproducibility metadata.

Additional documentation:

- `docs/SCENARIO_EVALUATION_ENGINE_ACADEMIC_RESPONSE.md`
- `docs/OPEN_WEIGHT_LLM_JUDGES.md`
- `docs/WEIGHTING_AND_DECISION_FRAMEWORK.md`
- `docs/COEFFICIENT_JUSTIFICATION_VALIDATION_AND_REVISION_WORKFLOW.md`
