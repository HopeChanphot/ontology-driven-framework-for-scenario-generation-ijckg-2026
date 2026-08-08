# PSQ-SCO 120-Case Scenario Generation Plan for Paper Evaluation

## Purpose

This document defines the frozen 120-case scenario-generation set used to compare the separate PSQ-SCO ontology-guided generation engine against the baseline prompt+RAG engine. The same 120 case definitions are used in both modes so that the ontology is the main experimental difference.

## How Many Scenarios Can the Engine Generate?

The complete PersonaShield Quest scenario slot space is:

```text
5 roles x 9 stages x 5 age groups x 3 channels x 2 variants = 1,350 scenario slots
```

This count is per retrieval mode, per model, and per generation mode. Therefore:

| Configuration | Generated outputs |
|---|---:|
| 1 model, 1 retrieval mode, 1 generation mode | 1,350 |
| 1 model, 1 retrieval mode, both modes | 2,700 |
| 1 model, 2 production retrieval modes, both modes | 5,400 |
| 3 primary local models, 1 retrieval mode, both modes | 8,100 |

A complete game scenario content item is one channel/variant scenario slot. It includes the player-facing message or dialogue, attack/legitimate classification, role and stage metadata, choices, feedback, hint text, scoring metadata, quality metadata, and generation trace. A full six-slot persona bundle would contain sms/email/voice x fake/real for one persona path.

## Why 120 Cases?

The 120-case set is a controlled evaluation subset. It is small enough for local lightweight LLM generation and human inspection, but broad enough to test the ontology across the key scenario-control dimensions.

```text
30 base groups = 3 channels x 2 variants x 5 roles
Test each group at 3 difficulty levels = 90 cases
Add 1 balanced repetition per group = 30 cases
Total = 120 cases
```

The three difficulty anchors are:

| Difficulty condition | Stage | Reason |
|---|---|---|
| low_foundational | BEGINNER_INTRODUCTORY | Tests explicit cues, basic recognition, and high scaffolding. |
| medium_applied | INTERMEDIATE_DEVELOPING | Tests applied comparison, multiple cues, and moderate ambiguity. |
| high_expert | EXPERT_ADVANCED | Tests subtle cues, low scaffolding, and strategic reasoning. |

The balanced repetition is one extra case per base group. It is not a random duplicate. It rotates through the six non-anchor stages and all five age groups. This gives the paper sample extra stability evidence and shows whether the ontology still behaves well outside the three anchor stages.

## Matching Across Both Modes

Every case has a fixed `case_id`, role, channel, variant, stage, age group, retrieval mode, and language. The engine then runs that same case in:

- Mode 1: `prompt_rag`
- Mode 2: `ontology_prompt_rag`

With `--mode both`, 120 case definitions produce 240 generated outputs. This paired design supports direct comparison because each Mode 1 output has a matching Mode 2 output with the same case definition.

## Balance Summary

### counts_by_role

| Value | Count |
|---|---:|
| `FINANCE` | 24 |
| `HR` | 24 |
| `IT` | 24 |
| `MANAGEMENT` | 24 |
| `OTHER` | 24 |

### counts_by_channel

| Value | Count |
|---|---:|
| `email` | 40 |
| `sms` | 40 |
| `voice` | 40 |

### counts_by_variant

| Value | Count |
|---|---:|
| `fake` | 60 |
| `real` | 60 |

### counts_by_age_group

| Value | Count |
|---|---:|
| `15_21` | 24 |
| `22_35` | 24 |
| `36_45` | 24 |
| `46_59` | 24 |
| `60_90` | 24 |

### counts_by_difficulty_condition

| Value | Count |
|---|---:|
| `balanced_repetition` | 30 |
| `high_expert` | 30 |
| `low_foundational` | 30 |
| `medium_applied` | 30 |

### counts_by_stage

| Value | Count |
|---|---:|
| `BEGINNER_ADVANCED` | 5 |
| `BEGINNER_DEVELOPING` | 5 |
| `BEGINNER_INTRODUCTORY` | 30 |
| `EXPERT_ADVANCED` | 30 |
| `EXPERT_DEVELOPING` | 5 |
| `EXPERT_INTRODUCTORY` | 5 |
| `INTERMEDIATE_ADVANCED` | 5 |
| `INTERMEDIATE_DEVELOPING` | 30 |
| `INTERMEDIATE_INTRODUCTORY` | 5 |

## Exported Case Manifest Files

The full machine-readable case set is exported here:

- `configs/psq_sco_paper_120_cases.json`
- `configs/psq_sco_paper_120_cases.csv`

The CLI also exports a per-run copy as `case_manifest.json` and `case_manifest.csv` inside each output run directory.

## Commands

Export the 120-case plan only:

```bash
python generate_scenarios_sco.py --case-set paper_120 --export-case-plan-only --limit 0 --out-dir output/psq_sco_case_plan
```

Generate all 120 cases in both modes. This produces 240 output rows:

```bash
python generate_scenarios_sco.py --case-set paper_120 --mode both --limit 0 --llm qwen2_5_7b --out-dir output/psq_sco_paper_120
```

Dry-run the same case set without calling Ollama:

```bash
python generate_scenarios_sco.py --case-set paper_120 --mode both --limit 0 --dry-run --skip-rag --out-dir output/psq_sco_paper_120_dryrun
```

## All 120 Case Definitions

| # | Case ID | Group | Role | Channel | Variant | Condition | Stage | Age | Retrieval | Language |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | `PSQ-SCO-120-001` | `G01_IT_sms_fake` | IT | sms | fake | low_foundational | BEGINNER_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 2 | `PSQ-SCO-120-002` | `G01_IT_sms_fake` | IT | sms | fake | medium_applied | INTERMEDIATE_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 3 | `PSQ-SCO-120-003` | `G01_IT_sms_fake` | IT | sms | fake | high_expert | EXPERT_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 4 | `PSQ-SCO-120-004` | `G01_IT_sms_fake` | IT | sms | fake | balanced_repetition | BEGINNER_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 5 | `PSQ-SCO-120-005` | `G02_FINANCE_sms_fake` | FINANCE | sms | fake | low_foundational | BEGINNER_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 6 | `PSQ-SCO-120-006` | `G02_FINANCE_sms_fake` | FINANCE | sms | fake | medium_applied | INTERMEDIATE_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
| 7 | `PSQ-SCO-120-007` | `G02_FINANCE_sms_fake` | FINANCE | sms | fake | high_expert | EXPERT_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 8 | `PSQ-SCO-120-008` | `G02_FINANCE_sms_fake` | FINANCE | sms | fake | balanced_repetition | BEGINNER_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 9 | `PSQ-SCO-120-009` | `G03_HR_sms_fake` | HR | sms | fake | low_foundational | BEGINNER_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 10 | `PSQ-SCO-120-010` | `G03_HR_sms_fake` | HR | sms | fake | medium_applied | INTERMEDIATE_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 11 | `PSQ-SCO-120-011` | `G03_HR_sms_fake` | HR | sms | fake | high_expert | EXPERT_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 12 | `PSQ-SCO-120-012` | `G03_HR_sms_fake` | HR | sms | fake | balanced_repetition | INTERMEDIATE_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 13 | `PSQ-SCO-120-013` | `G04_MANAGEMENT_sms_fake` | MANAGEMENT | sms | fake | low_foundational | BEGINNER_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 14 | `PSQ-SCO-120-014` | `G04_MANAGEMENT_sms_fake` | MANAGEMENT | sms | fake | medium_applied | INTERMEDIATE_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 15 | `PSQ-SCO-120-015` | `G04_MANAGEMENT_sms_fake` | MANAGEMENT | sms | fake | high_expert | EXPERT_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 16 | `PSQ-SCO-120-016` | `G04_MANAGEMENT_sms_fake` | MANAGEMENT | sms | fake | balanced_repetition | INTERMEDIATE_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 17 | `PSQ-SCO-120-017` | `G05_OTHER_sms_fake` | OTHER | sms | fake | low_foundational | BEGINNER_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 18 | `PSQ-SCO-120-018` | `G05_OTHER_sms_fake` | OTHER | sms | fake | medium_applied | INTERMEDIATE_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 19 | `PSQ-SCO-120-019` | `G05_OTHER_sms_fake` | OTHER | sms | fake | high_expert | EXPERT_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 20 | `PSQ-SCO-120-020` | `G05_OTHER_sms_fake` | OTHER | sms | fake | balanced_repetition | EXPERT_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 21 | `PSQ-SCO-120-021` | `G06_IT_sms_real` | IT | sms | real | low_foundational | BEGINNER_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 22 | `PSQ-SCO-120-022` | `G06_IT_sms_real` | IT | sms | real | medium_applied | INTERMEDIATE_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 23 | `PSQ-SCO-120-023` | `G06_IT_sms_real` | IT | sms | real | high_expert | EXPERT_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 24 | `PSQ-SCO-120-024` | `G06_IT_sms_real` | IT | sms | real | balanced_repetition | EXPERT_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 25 | `PSQ-SCO-120-025` | `G07_FINANCE_sms_real` | FINANCE | sms | real | low_foundational | BEGINNER_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 26 | `PSQ-SCO-120-026` | `G07_FINANCE_sms_real` | FINANCE | sms | real | medium_applied | INTERMEDIATE_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
| 27 | `PSQ-SCO-120-027` | `G07_FINANCE_sms_real` | FINANCE | sms | real | high_expert | EXPERT_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 28 | `PSQ-SCO-120-028` | `G07_FINANCE_sms_real` | FINANCE | sms | real | balanced_repetition | BEGINNER_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 29 | `PSQ-SCO-120-029` | `G08_HR_sms_real` | HR | sms | real | low_foundational | BEGINNER_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 30 | `PSQ-SCO-120-030` | `G08_HR_sms_real` | HR | sms | real | medium_applied | INTERMEDIATE_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 31 | `PSQ-SCO-120-031` | `G08_HR_sms_real` | HR | sms | real | high_expert | EXPERT_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 32 | `PSQ-SCO-120-032` | `G08_HR_sms_real` | HR | sms | real | balanced_repetition | BEGINNER_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 33 | `PSQ-SCO-120-033` | `G09_MANAGEMENT_sms_real` | MANAGEMENT | sms | real | low_foundational | BEGINNER_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 34 | `PSQ-SCO-120-034` | `G09_MANAGEMENT_sms_real` | MANAGEMENT | sms | real | medium_applied | INTERMEDIATE_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 35 | `PSQ-SCO-120-035` | `G09_MANAGEMENT_sms_real` | MANAGEMENT | sms | real | high_expert | EXPERT_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 36 | `PSQ-SCO-120-036` | `G09_MANAGEMENT_sms_real` | MANAGEMENT | sms | real | balanced_repetition | INTERMEDIATE_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 37 | `PSQ-SCO-120-037` | `G10_OTHER_sms_real` | OTHER | sms | real | low_foundational | BEGINNER_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 38 | `PSQ-SCO-120-038` | `G10_OTHER_sms_real` | OTHER | sms | real | medium_applied | INTERMEDIATE_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 39 | `PSQ-SCO-120-039` | `G10_OTHER_sms_real` | OTHER | sms | real | high_expert | EXPERT_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 40 | `PSQ-SCO-120-040` | `G10_OTHER_sms_real` | OTHER | sms | real | balanced_repetition | INTERMEDIATE_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 41 | `PSQ-SCO-120-041` | `G11_IT_email_fake` | IT | email | fake | low_foundational | BEGINNER_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 42 | `PSQ-SCO-120-042` | `G11_IT_email_fake` | IT | email | fake | medium_applied | INTERMEDIATE_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 43 | `PSQ-SCO-120-043` | `G11_IT_email_fake` | IT | email | fake | high_expert | EXPERT_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 44 | `PSQ-SCO-120-044` | `G11_IT_email_fake` | IT | email | fake | balanced_repetition | EXPERT_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 45 | `PSQ-SCO-120-045` | `G12_FINANCE_email_fake` | FINANCE | email | fake | low_foundational | BEGINNER_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 46 | `PSQ-SCO-120-046` | `G12_FINANCE_email_fake` | FINANCE | email | fake | medium_applied | INTERMEDIATE_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
| 47 | `PSQ-SCO-120-047` | `G12_FINANCE_email_fake` | FINANCE | email | fake | high_expert | EXPERT_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 48 | `PSQ-SCO-120-048` | `G12_FINANCE_email_fake` | FINANCE | email | fake | balanced_repetition | EXPERT_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 49 | `PSQ-SCO-120-049` | `G13_HR_email_fake` | HR | email | fake | low_foundational | BEGINNER_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 50 | `PSQ-SCO-120-050` | `G13_HR_email_fake` | HR | email | fake | medium_applied | INTERMEDIATE_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 51 | `PSQ-SCO-120-051` | `G13_HR_email_fake` | HR | email | fake | high_expert | EXPERT_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 52 | `PSQ-SCO-120-052` | `G13_HR_email_fake` | HR | email | fake | balanced_repetition | BEGINNER_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 53 | `PSQ-SCO-120-053` | `G14_MANAGEMENT_email_fake` | MANAGEMENT | email | fake | low_foundational | BEGINNER_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 54 | `PSQ-SCO-120-054` | `G14_MANAGEMENT_email_fake` | MANAGEMENT | email | fake | medium_applied | INTERMEDIATE_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 55 | `PSQ-SCO-120-055` | `G14_MANAGEMENT_email_fake` | MANAGEMENT | email | fake | high_expert | EXPERT_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 56 | `PSQ-SCO-120-056` | `G14_MANAGEMENT_email_fake` | MANAGEMENT | email | fake | balanced_repetition | BEGINNER_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 57 | `PSQ-SCO-120-057` | `G15_OTHER_email_fake` | OTHER | email | fake | low_foundational | BEGINNER_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 58 | `PSQ-SCO-120-058` | `G15_OTHER_email_fake` | OTHER | email | fake | medium_applied | INTERMEDIATE_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 59 | `PSQ-SCO-120-059` | `G15_OTHER_email_fake` | OTHER | email | fake | high_expert | EXPERT_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 60 | `PSQ-SCO-120-060` | `G15_OTHER_email_fake` | OTHER | email | fake | balanced_repetition | INTERMEDIATE_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 61 | `PSQ-SCO-120-061` | `G16_IT_email_real` | IT | email | real | low_foundational | BEGINNER_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 62 | `PSQ-SCO-120-062` | `G16_IT_email_real` | IT | email | real | medium_applied | INTERMEDIATE_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 63 | `PSQ-SCO-120-063` | `G16_IT_email_real` | IT | email | real | high_expert | EXPERT_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 64 | `PSQ-SCO-120-064` | `G16_IT_email_real` | IT | email | real | balanced_repetition | INTERMEDIATE_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 65 | `PSQ-SCO-120-065` | `G17_FINANCE_email_real` | FINANCE | email | real | low_foundational | BEGINNER_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 66 | `PSQ-SCO-120-066` | `G17_FINANCE_email_real` | FINANCE | email | real | medium_applied | INTERMEDIATE_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
| 67 | `PSQ-SCO-120-067` | `G17_FINANCE_email_real` | FINANCE | email | real | high_expert | EXPERT_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 68 | `PSQ-SCO-120-068` | `G17_FINANCE_email_real` | FINANCE | email | real | balanced_repetition | EXPERT_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 69 | `PSQ-SCO-120-069` | `G18_HR_email_real` | HR | email | real | low_foundational | BEGINNER_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 70 | `PSQ-SCO-120-070` | `G18_HR_email_real` | HR | email | real | medium_applied | INTERMEDIATE_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 71 | `PSQ-SCO-120-071` | `G18_HR_email_real` | HR | email | real | high_expert | EXPERT_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 72 | `PSQ-SCO-120-072` | `G18_HR_email_real` | HR | email | real | balanced_repetition | EXPERT_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 73 | `PSQ-SCO-120-073` | `G19_MANAGEMENT_email_real` | MANAGEMENT | email | real | low_foundational | BEGINNER_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 74 | `PSQ-SCO-120-074` | `G19_MANAGEMENT_email_real` | MANAGEMENT | email | real | medium_applied | INTERMEDIATE_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 75 | `PSQ-SCO-120-075` | `G19_MANAGEMENT_email_real` | MANAGEMENT | email | real | high_expert | EXPERT_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 76 | `PSQ-SCO-120-076` | `G19_MANAGEMENT_email_real` | MANAGEMENT | email | real | balanced_repetition | BEGINNER_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 77 | `PSQ-SCO-120-077` | `G20_OTHER_email_real` | OTHER | email | real | low_foundational | BEGINNER_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 78 | `PSQ-SCO-120-078` | `G20_OTHER_email_real` | OTHER | email | real | medium_applied | INTERMEDIATE_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 79 | `PSQ-SCO-120-079` | `G20_OTHER_email_real` | OTHER | email | real | high_expert | EXPERT_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 80 | `PSQ-SCO-120-080` | `G20_OTHER_email_real` | OTHER | email | real | balanced_repetition | BEGINNER_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 81 | `PSQ-SCO-120-081` | `G21_IT_voice_fake` | IT | voice | fake | low_foundational | BEGINNER_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 82 | `PSQ-SCO-120-082` | `G21_IT_voice_fake` | IT | voice | fake | medium_applied | INTERMEDIATE_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 83 | `PSQ-SCO-120-083` | `G21_IT_voice_fake` | IT | voice | fake | high_expert | EXPERT_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 84 | `PSQ-SCO-120-084` | `G21_IT_voice_fake` | IT | voice | fake | balanced_repetition | INTERMEDIATE_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 85 | `PSQ-SCO-120-085` | `G22_FINANCE_voice_fake` | FINANCE | voice | fake | low_foundational | BEGINNER_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 86 | `PSQ-SCO-120-086` | `G22_FINANCE_voice_fake` | FINANCE | voice | fake | medium_applied | INTERMEDIATE_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
| 87 | `PSQ-SCO-120-087` | `G22_FINANCE_voice_fake` | FINANCE | voice | fake | high_expert | EXPERT_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 88 | `PSQ-SCO-120-088` | `G22_FINANCE_voice_fake` | FINANCE | voice | fake | balanced_repetition | INTERMEDIATE_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 89 | `PSQ-SCO-120-089` | `G23_HR_voice_fake` | HR | voice | fake | low_foundational | BEGINNER_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 90 | `PSQ-SCO-120-090` | `G23_HR_voice_fake` | HR | voice | fake | medium_applied | INTERMEDIATE_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 91 | `PSQ-SCO-120-091` | `G23_HR_voice_fake` | HR | voice | fake | high_expert | EXPERT_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 92 | `PSQ-SCO-120-092` | `G23_HR_voice_fake` | HR | voice | fake | balanced_repetition | EXPERT_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 93 | `PSQ-SCO-120-093` | `G24_MANAGEMENT_voice_fake` | MANAGEMENT | voice | fake | low_foundational | BEGINNER_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 94 | `PSQ-SCO-120-094` | `G24_MANAGEMENT_voice_fake` | MANAGEMENT | voice | fake | medium_applied | INTERMEDIATE_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 95 | `PSQ-SCO-120-095` | `G24_MANAGEMENT_voice_fake` | MANAGEMENT | voice | fake | high_expert | EXPERT_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 96 | `PSQ-SCO-120-096` | `G24_MANAGEMENT_voice_fake` | MANAGEMENT | voice | fake | balanced_repetition | EXPERT_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 97 | `PSQ-SCO-120-097` | `G25_OTHER_voice_fake` | OTHER | voice | fake | low_foundational | BEGINNER_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 98 | `PSQ-SCO-120-098` | `G25_OTHER_voice_fake` | OTHER | voice | fake | medium_applied | INTERMEDIATE_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 99 | `PSQ-SCO-120-099` | `G25_OTHER_voice_fake` | OTHER | voice | fake | high_expert | EXPERT_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 100 | `PSQ-SCO-120-100` | `G25_OTHER_voice_fake` | OTHER | voice | fake | balanced_repetition | BEGINNER_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
| 101 | `PSQ-SCO-120-101` | `G26_IT_voice_real` | IT | voice | real | low_foundational | BEGINNER_INTRODUCTORY | 15_21 | ENGLISH_GLOBAL | en |
| 102 | `PSQ-SCO-120-102` | `G26_IT_voice_real` | IT | voice | real | medium_applied | INTERMEDIATE_DEVELOPING | 22_35 | ENGLISH_GLOBAL | en |
| 103 | `PSQ-SCO-120-103` | `G26_IT_voice_real` | IT | voice | real | high_expert | EXPERT_ADVANCED | 36_45 | ENGLISH_GLOBAL | en |
| 104 | `PSQ-SCO-120-104` | `G26_IT_voice_real` | IT | voice | real | balanced_repetition | BEGINNER_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 105 | `PSQ-SCO-120-105` | `G27_FINANCE_voice_real` | FINANCE | voice | real | low_foundational | BEGINNER_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 106 | `PSQ-SCO-120-106` | `G27_FINANCE_voice_real` | FINANCE | voice | real | medium_applied | INTERMEDIATE_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
| 107 | `PSQ-SCO-120-107` | `G27_FINANCE_voice_real` | FINANCE | voice | real | high_expert | EXPERT_ADVANCED | 46_59 | ENGLISH_GLOBAL | en |
| 108 | `PSQ-SCO-120-108` | `G27_FINANCE_voice_real` | FINANCE | voice | real | balanced_repetition | INTERMEDIATE_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 109 | `PSQ-SCO-120-109` | `G28_HR_voice_real` | HR | voice | real | low_foundational | BEGINNER_INTRODUCTORY | 36_45 | ENGLISH_GLOBAL | en |
| 110 | `PSQ-SCO-120-110` | `G28_HR_voice_real` | HR | voice | real | medium_applied | INTERMEDIATE_DEVELOPING | 46_59 | ENGLISH_GLOBAL | en |
| 111 | `PSQ-SCO-120-111` | `G28_HR_voice_real` | HR | voice | real | high_expert | EXPERT_ADVANCED | 60_90 | ENGLISH_GLOBAL | en |
| 112 | `PSQ-SCO-120-112` | `G28_HR_voice_real` | HR | voice | real | balanced_repetition | INTERMEDIATE_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 113 | `PSQ-SCO-120-113` | `G29_MANAGEMENT_voice_real` | MANAGEMENT | voice | real | low_foundational | BEGINNER_INTRODUCTORY | 46_59 | ENGLISH_GLOBAL | en |
| 114 | `PSQ-SCO-120-114` | `G29_MANAGEMENT_voice_real` | MANAGEMENT | voice | real | medium_applied | INTERMEDIATE_DEVELOPING | 60_90 | ENGLISH_GLOBAL | en |
| 115 | `PSQ-SCO-120-115` | `G29_MANAGEMENT_voice_real` | MANAGEMENT | voice | real | high_expert | EXPERT_ADVANCED | 15_21 | ENGLISH_GLOBAL | en |
| 116 | `PSQ-SCO-120-116` | `G29_MANAGEMENT_voice_real` | MANAGEMENT | voice | real | balanced_repetition | EXPERT_INTRODUCTORY | 22_35 | ENGLISH_GLOBAL | en |
| 117 | `PSQ-SCO-120-117` | `G30_OTHER_voice_real` | OTHER | voice | real | low_foundational | BEGINNER_INTRODUCTORY | 60_90 | ENGLISH_GLOBAL | en |
| 118 | `PSQ-SCO-120-118` | `G30_OTHER_voice_real` | OTHER | voice | real | medium_applied | INTERMEDIATE_DEVELOPING | 15_21 | ENGLISH_GLOBAL | en |
| 119 | `PSQ-SCO-120-119` | `G30_OTHER_voice_real` | OTHER | voice | real | high_expert | EXPERT_ADVANCED | 22_35 | ENGLISH_GLOBAL | en |
| 120 | `PSQ-SCO-120-120` | `G30_OTHER_voice_real` | OTHER | voice | real | balanced_repetition | EXPERT_DEVELOPING | 36_45 | ENGLISH_GLOBAL | en |
