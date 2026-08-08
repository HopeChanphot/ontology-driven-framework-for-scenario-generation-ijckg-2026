# Data Availability and Reproduction

This public repository includes the data that can be redistributed safely with the internship handover. It does **not** publish third-party corpora whose redistribution rights or privacy status have not been verified.

## Included data

- `genai_engine/minimal_kb/` contains one synthetic defensive phishing example created for this project. It exercises the JSONL lexical-RAG path without redistributing third-party text.
- `genai_engine/output/minimal_four_modes/20260726_235309/` contains the retained four-mode portability smoke output.
- `genai_engine/output/minimal_four_modes_evaluation/20260727_001450/` contains the matching compact evaluation output.
- `genai_engine/evidence/` and `genai_engine/targeted_evaluation_repair/evaluation_rerun/` contain compact manifests, aggregate tables, audit records, and paper-aligned evidence.
- `genai_engine/example_scenario_pool.json` contains the small example scenario-pool fixture retained for code and format inspection.
- `ontology/data/`, `ontology/knowledge_graph/`, and `ontology/outputs/` contain the redistributable ontology-side inputs, exports, bindings, and validation evidence retained for PSQ-SCO v9.1.

The included synthetic record is a code-path fixture, not the research corpus and not evidence of model quality.

## Original RAG holdings not published

The private research workspace contained 37 RAG files totaling 472,949,191 bytes:

- 23 raw source files totaling 461,724,951 bytes.
- 14 processed channel JSONL files totaling 11,224,240 bytes.

The raw filenames indicated material derived from or associated with CEAS 2008, Enron, Ling Spam, Nazario, Nigerian-fraud collections, SpamAssassin, TREC 2005–2007, SMS Spam Collection, Thai fraud/ham samples, financial-fraud documents, an IRS call transcript, and a TB-CERT presentation. No license, copying, notice, terms, citation, or source file was stored beside those local copies.

These files are excluded because:

1. Public redistribution permission was not established.
2. Email and message corpora can contain personal, copyrighted, or sensitive text.
3. Processed JSONL derived from a third-party corpus does not automatically become redistributable.
4. `TREC_05.csv` and `TREC_07.csv` individually exceeded GitHub's normal 100 MB file limit.

Do not commit those local raw or processed files until an institutional data review confirms the permitted source, license, privacy treatment, and redistribution terms for every dataset.

## Rebuild an authorized RAG corpus

1. Reacquire each dataset from its official or otherwise authorized source.
2. Record the dataset name, version, source URL, retrieval date, license, file checksum, language, channel, and labeling policy.
3. Place the authorized files under `genai_engine/knowledge_base/raw_data/`.
4. Install the full data-preparation dependencies:

```powershell
python -m venv .venv
$py = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $py -m pip install -r .\genai_engine\requirements.txt
```

5. Normalize the source files:

```powershell
Push-Location .\genai_engine
& $py .\prepare_rag_data.py `
  --input-dir .\knowledge_base\raw_data `
  --output-dir .\knowledge_base\prepared
$env:PSQ_KB_DIR = (Resolve-Path .\knowledge_base\prepared).Path
Pop-Location
```

6. Inspect `_manifest/rag_prepare_manifest_v5_1.json`, sample the normalized records, and freeze checksums before generation.
7. Record whether retrieval used the JSONL lexical fallback or a Chroma vector index. These are different retrieval conditions.

## Full paper experiment

The compact repository does not contain the frozen 1,440 raw scenario JSONL records or the separate 360-record Graph-Walk v1 ablation. Exact frozen-table reproduction requires restoration of those precise inputs and their manifests. Regenerating 120 matched cases across four modes and three models creates a new replication dataset and must receive a new run identifier.

See `EXCLUSIONS_AND_REBUILD.md` and `HOW_TO_USE_RUN_AND_REPRODUCE_PSQ_SCO.docx` for the complete workflow.
