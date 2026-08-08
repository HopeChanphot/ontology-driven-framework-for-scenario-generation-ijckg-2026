# Targeted PSQ-SCO Evaluation Repair

This directory is an isolated, non-overwriting repair package for the frozen
PSQ-SCO paper experiment.

It evaluates the existing 1,440 live records, adds canonical local provenance
traceability (`T`), computes an equal-weight secondary operational index
(`OCI_eq`), runs deterministic 10,000-vector weight sensitivity, and exports five
matched diagnostic cases. It does not call Ollama or any other generation model.

The manuscript's frozen experiment uses
`output/paper120_live_recovered_final/20260714_031104/generated_scenarios`.
The later Graph-Walk v1 output is a separate ablation and is not silently mixed
into this paper-aligned rerun.

Run from `D:\PersonaShieldQuest-GenAI-Engine`:

```powershell
$PY = "C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

& $PY .\output\targeted_psq_sco_evaluation_repair\20260723_200851\src\targeted_evaluation.py `
  --input-root .\output\paper120_live_recovered_final\20260714_031104\generated_scenarios `
  --ontology C:\Users\user\PersonaShieldQuest-Ontology\ontology\personashield-psq-sco-v9.1.owl `
  --dataset-catalog C:\Users\user\PersonaShieldQuest-Ontology\data\ontology_bindings\dataset-catalog.json `
  --corpus-root .\output `
  --out-dir .\output\targeted_psq_sco_evaluation_repair\20260723_200851\evaluation_rerun
```

Run focused tests:

```powershell
& $PY -m unittest discover `
  -s .\output\targeted_psq_sco_evaluation_repair\20260723_200851\tests `
  -p "test_*.py" -v
```
