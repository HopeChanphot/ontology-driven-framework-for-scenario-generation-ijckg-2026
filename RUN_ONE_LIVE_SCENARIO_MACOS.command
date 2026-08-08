#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR"

PYTHON="$ROOT_DIR/.venv/bin/python"
OLLAMA_BIN="$ROOT_DIR/.portable_runtime/Ollama.app/Contents/Resources/ollama"
MODEL_NAME="psq-small:q4_0"
OLLAMA_URL="http://127.0.0.1:11435"
OUTPUT_ROOT="$ROOT_DIR/live_scenario_output"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: This launcher is for macOS."
  exit 1
fi

if [[ ! -x "$PYTHON" || ! -x "$OLLAMA_BIN" ]]; then
  echo "The portable environment has not been initialized."
  echo "Run this first:"
  echo "  ./START_AND_TEST_MACOS.command"
  exit 2
fi

export OLLAMA_HOST="127.0.0.1:11435"
export OLLAMA_BASE_URL="$OLLAMA_URL"
export OLLAMA_MODELS="$ROOT_DIR/.portable_runtime/ollama-model-store"
export PSQ_KB_DIR="$ROOT_DIR/genai_engine/minimal_kb"
export PSQ_FORCE_LEXICAL_RAG="1"

STARTED_OLLAMA=0
OLLAMA_PID=""
if ! curl --silent --fail "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  mkdir -p "$ROOT_DIR/.portable_runtime/logs" "$OLLAMA_MODELS"
  echo "Starting the private local Ollama service on port 11435..."
  "$OLLAMA_BIN" serve \
    >"$ROOT_DIR/.portable_runtime/logs/ollama-live-scenario.log" 2>&1 &
  OLLAMA_PID=$!
  STARTED_OLLAMA=1
fi

cleanup() {
  if [[ "$STARTED_OLLAMA" -eq 1 && -n "$OLLAMA_PID" ]]; then
    kill "$OLLAMA_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

ready=0
for _ in $(seq 1 90); do
  if curl --silent --fail "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: The private Ollama service did not start."
  echo "Read: $ROOT_DIR/.portable_runtime/logs/ollama-live-scenario.log"
  exit 1
fi

if ! "$OLLAMA_BIN" list | awk 'NR > 1 {print $1}' | grep -qx "$MODEL_NAME"; then
  echo "Registering the bundled Qwen2.5 0.5B model..."
  "$OLLAMA_BIN" create "$MODEL_NAME" -f "$ROOT_DIR/models/Modelfile.psq-small"
fi

mkdir -p "$OUTPUT_ROOT"

echo "Generating exactly one live ontology-text-RAG scenario..."
cd "$ROOT_DIR/genai_engine"
"$PYTHON" generate_scenarios_sco.py \
  --ontology-path "$ROOT_DIR/ontology/ontology/personashield-psq-sco-v9.1.owl" \
  --mode ontology_text_rag \
  --role HR \
  --stage BEGINNER_INTRODUCTORY \
  --age-group 22_35 \
  --channel email \
  --variant fake \
  --retrieval-mode ENGLISH_GLOBAL \
  --language-mode en \
  --llm qwen2_5_0_5b \
  --case-set single \
  --limit 1 \
  --n-rag-examples 1 \
  --ontology-text-doc-limit 3 \
  --llm-timeout 600 \
  --llm-max-tokens 900 \
  --llm-num-ctx 4096 \
  --llm-temperature 0.2 \
  --llm-parse-retries 2 \
  --compact-generation-prompt \
  --require-live-llm \
  --out-dir "$OUTPUT_ROOT"

cd "$ROOT_DIR"
"$PYTHON" "$ROOT_DIR/tools/verify_one_live_scenario.py" \
  --output-root "$OUTPUT_ROOT"

echo
echo "ONE LIVE SMALL-MODEL SCENARIO PASSED."
echo "Result: $OUTPUT_ROOT/LATEST_LIVE_SCENARIO.json"
