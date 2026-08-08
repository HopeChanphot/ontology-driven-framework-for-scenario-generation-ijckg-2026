#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR"

ENVIRONMENT_NAME="chanphot-psq-sco"
MODEL_NAME="psq-small:q4_0"
OLLAMA_URL="http://127.0.0.1:11435"
LOCAL_RUNTIME="$ROOT_DIR/.portable_runtime"
OLLAMA_APP="$LOCAL_RUNTIME/Ollama.app"
OLLAMA_BIN="$OLLAMA_APP/Contents/Resources/ollama"
OLLAMA_ZIP="$ROOT_DIR/runtime/Ollama-darwin-v0.30.8.zip"
MODEL_FILE="$ROOT_DIR/models/qwen2.5-0.5b-instruct-q4_0.gguf"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: This launcher is for macOS."
  exit 1
fi

case "$(uname -m)" in
  arm64)
    WHEELHOUSE="$ROOT_DIR/wheelhouse/macos-arm64"
    ;;
  x86_64)
    WHEELHOUSE="$ROOT_DIR/wheelhouse/macos-x86_64"
    ;;
  *)
    echo "ERROR: Unsupported Mac architecture: $(uname -m)"
    exit 1
    ;;
esac

find_python() {
  local candidate
  for candidate in \
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" \
    "python3.12" \
    "python3"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then
        command -v "$candidate"
        return 0
      fi
    elif [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! BOOTSTRAP_PYTHON="$(find_python)"; then
  echo "Python 3.12 is required by the included offline wheelhouse."
  echo "Open and install:"
  echo "  $ROOT_DIR/runtime/python-3.12.10-macos11.pkg"
  echo "Then run this file again."
  open "$ROOT_DIR/runtime/python-3.12.10-macos11.pkg"
  exit 2
fi

if [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
  echo "Creating Python environment: $ENVIRONMENT_NAME"
  "$BOOTSTRAP_PYTHON" -m venv --prompt "$ENVIRONMENT_NAME" "$ROOT_DIR/.venv"
fi

PYTHON="$ROOT_DIR/.venv/bin/python"
echo "Installing Python dependencies from the included offline wheelhouse..."
"$PYTHON" -m pip install \
  --no-index \
  --find-links "$WHEELHOUSE" \
  -r "$ROOT_DIR/requirements-macos.txt"

if [[ ! -f "$OLLAMA_ZIP" ]]; then
  echo "ERROR: Missing bundled Ollama archive: $OLLAMA_ZIP"
  exit 1
fi
if [[ ! -f "$MODEL_FILE" ]]; then
  echo "ERROR: Missing bundled small model: $MODEL_FILE"
  exit 1
fi

if [[ ! -x "$OLLAMA_BIN" ]]; then
  echo "Extracting the included Ollama macOS runtime..."
  mkdir -p "$LOCAL_RUNTIME"
  unzip -q "$OLLAMA_ZIP" -d "$LOCAL_RUNTIME"
fi
chmod +x "$OLLAMA_BIN"

export OLLAMA_HOST="127.0.0.1:11435"
export OLLAMA_BASE_URL="$OLLAMA_URL"
export OLLAMA_MODELS="$LOCAL_RUNTIME/ollama-model-store"
mkdir -p "$OLLAMA_MODELS" "$LOCAL_RUNTIME/logs"

echo "Starting the private local Ollama service on port 11435..."
"$OLLAMA_BIN" serve >"$LOCAL_RUNTIME/logs/ollama-server.log" 2>&1 &
OLLAMA_PID=$!
cleanup() {
  kill "$OLLAMA_PID" >/dev/null 2>&1 || true
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
  echo "ERROR: The included Ollama service did not start."
  echo "Read: $LOCAL_RUNTIME/logs/ollama-server.log"
  exit 1
fi

if ! "$OLLAMA_BIN" list | awk 'NR > 1 {print $1}' | grep -qx "$MODEL_NAME"; then
  echo "Registering the included Qwen2.5 0.5B model..."
  "$OLLAMA_BIN" create "$MODEL_NAME" -f "$ROOT_DIR/models/Modelfile.psq-small"
fi

echo "Testing the bundled model through the PSQ-SCO LLM client..."
"$PYTHON" "$ROOT_DIR/tools/test_bundled_small_llm.py" \
  --base-url "$OLLAMA_URL" \
  --model "$MODEL_NAME"

echo "Running ontology, four-mode, evaluation, and unit-test workflow..."
"$PYTHON" "$ROOT_DIR/tools/setup_and_test_macos.py" --skip-install

echo
echo "ALL PORTABLE PSQ-SCO TESTS PASSED."
echo "Environment: $ENVIRONMENT_NAME"
echo "Activate later with: source \"$ROOT_DIR/.venv/bin/activate\""
echo "Results: $ROOT_DIR/.macos_test_output"
