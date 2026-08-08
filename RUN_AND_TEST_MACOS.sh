#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_CMD="${PYTHON_CMD:-python3}"

exec "$PYTHON_CMD" "$ROOT_DIR/tools/setup_and_test_macos.py" "$@"
