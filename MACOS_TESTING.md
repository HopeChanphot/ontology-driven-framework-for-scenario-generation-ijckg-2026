# Test PSQ-SCO on macOS

This workflow creates a project-local Python virtual environment whose shell
prompt name is `chanphot-psq-sco`. It runs without API keys, paid services,
Chroma, Ollama, or model downloads.

## Requirements

- macOS on Apple Silicon or Intel
- Python 3.12 (the tested and supported macOS environment)
- Git
- Internet access for the first dependency installation

Check Python:

```bash
python3 --version
```

If needed and Homebrew is installed:

```bash
brew install python@3.12
```

## Clone the current pull-request branch

Until the pull request is merged:

```bash
git clone \
  --branch psq-sco-internship-handover \
  https://github.com/HopeChanphot/ontology-driven-framework-for-scenario-generation-ijckg-2026.git

cd ontology-driven-framework-for-scenario-generation-ijckg-2026
```

After the pull request is merged, clone the upstream `main` branch instead:

```bash
git clone \
  https://github.com/realearn-people/ontology-driven-framework-for-scenario-generation-ijckg-2026.git

cd ontology-driven-framework-for-scenario-generation-ijckg-2026
```

## Create Chanphot's environment and test everything

```bash
chmod +x ./RUN_AND_TEST_MACOS.sh
./RUN_AND_TEST_MACOS.sh
```

If Homebrew installed Python as `python3.12`, use:

```bash
PYTHON_CMD=python3.12 ./RUN_AND_TEST_MACOS.sh
```

The source-repository script:

1. creates `.venv` with the prompt name `chanphot-psq-sco`;
2. installs `requirements-macos.txt`;
3. verifies every packaged checksum;
4. runs the ontology competency questions and validation cases;
5. generates a matched scenario in all four research modes;
6. checks that RAG used the included synthetic fixture;
7. runs the three-layer evaluation engine; and
8. runs the 65 primary and 13 targeted evaluation tests.

Generated smoke-test results are written to `.macos_test_output/`, which is not
committed to Git.

## Activate the environment later

```bash
source .venv/bin/activate
```

The command prompt should begin with:

```text
(chanphot-psq-sco)
```

Deactivate it with:

```bash
deactivate
```

## Fast repeat run

After the first successful installation:

```bash
./RUN_AND_TEST_MACOS.sh --skip-install
```

To run generation and evaluation while temporarily skipping unit tests:

```bash
./RUN_AND_TEST_MACOS.sh --skip-install --skip-tests
```

## Important output files

- `.macos_test_output/ontology/sparql-cq-full-run-report.json`
- `.macos_test_output/ontology/sparql-cq-validation-report.json`
- `.macos_test_output/generation/<timestamp>/scenarios.jsonl`
- `.macos_test_output/evaluation/<timestamp>/evaluation_report.md`
- `.macos_test_output/evaluation/<timestamp>/method_summary.csv`
- `.macos_test_output/evaluation/<timestamp>/ontology_validation.json`

This is an offline code-path and reproducibility smoke test. It does not replace
the frozen paper experiment or a live local-model evaluation.

## Optional complete portable bundle

The GitHub repository intentionally omits the large GGUF, Ollama archive,
Python installer, and offline wheelhouse. The complete internship handover
bundle includes those assets for a copy-and-run test without downloading a
model.

After copying that complete bundle to the Mac:

```bash
chmod +x START_AND_TEST_MACOS.command RUN_ONE_LIVE_SCENARIO_MACOS.command
./START_AND_TEST_MACOS.command
./RUN_ONE_LIVE_SCENARIO_MACOS.command
```

The first command tests the private bundled Ollama service, ontology, all four
modes, evaluation, and unit tests. The second creates one genuinely live
small-model scenario. See `RUN_ONE_LIVE_SCENARIO.md` and
`OFFLINE_ASSET_SHA256.txt`.
