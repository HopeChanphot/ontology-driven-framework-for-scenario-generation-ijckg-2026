# Run one live scenario with the bundled small model

This optional test generates exactly one real scenario through the project
engine using:

- model: `psq-small:q4_0` (Qwen2.5 0.5B Instruct Q4_0);
- research mode: `ontology_text_rag`;
- channel: email;
- variant: fake;
- role: HR;
- stage: `BEGINNER_INTRODUCTORY`; and
- the included synthetic RAG fixture and PSQ-SCO ontology text.

The launcher needs the complete portable handover assets. The GitHub source
repository intentionally excludes the large GGUF, Ollama runtime, Python
installer, and offline wheelhouse. Put those assets in the paths listed in
`OFFLINE_ASSET_SHA256.txt`, or use the complete portable handover folder.

First initialize the portable environment:

```bash
cd /path/to/interjp
chmod +x START_AND_TEST_MACOS.command RUN_ONE_LIVE_SCENARIO_MACOS.command
./START_AND_TEST_MACOS.command
```

After the complete portable test succeeds, run:

```bash
./RUN_ONE_LIVE_SCENARIO_MACOS.command
```

The live run can take several minutes on CPU. It must end with:

```text
ONE LIVE SMALL-MODEL SCENARIO PASSED.
```

The readable result is:

```text
live_scenario_output/LATEST_LIVE_SCENARIO.json
```

Timestamped raw files, prompt metadata, ontology traces, RAG examples, and the
run summary remain in the timestamped subfolder under `live_scenario_output/`.

Because a 0.5B model can return valid JSON that is still too weak for the
research validator, the engine applies a validator-safe field projection when
needed. The raw live draft, accepted fields, rejected fields, and original
validation issues are preserved under:

```text
scenario.generation_meta.small_model_guardrail
```

The published scenario remains a live-model run (`used_live_llm: true`,
`used_fallback: false`) while deterministic safety scaffolding prevents a
low-resource draft from violating the scenario contract.

This is a functional low-resource demonstration. Qwen2.5 0.5B is not a
paper-grade replacement for the larger frozen experiment models.
