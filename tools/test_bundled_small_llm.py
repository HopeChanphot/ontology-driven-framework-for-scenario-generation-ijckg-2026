from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1] / "genai_engine"
sys.path.insert(0, str(ENGINE_ROOT))

from llm_client import LLMClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the bundled small model through the PSQ-SCO LLM client."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:11435",
        help="Local Ollama-compatible server URL.",
    )
    parser.add_argument("--model", default="psq-small:q4_0")
    args = parser.parse_args()

    client = LLMClient()
    client.ollama_base_url = args.base_url.rstrip("/")
    result = client.generate(
        "ollama",
        args.model,
        (
            "Return exactly one small JSON object. Do not use markdown or add "
            "text outside the JSON object."
        ),
        (
            'Return {"status":"ok","component":"PSQ-SCO",'
            '"test":"bundled-small-llm"}'
        ),
        temperature=0.0,
        max_tokens=128,
        timeout=180,
        num_ctx=2048,
    )
    if not isinstance(result, dict):
        details = json.dumps(client.last_call_info, ensure_ascii=False, indent=2)
        raise SystemExit(
            "The bundled model did not return parseable JSON through the "
            f"PSQ-SCO LLM client.\n{details}"
        )

    print("Bundled small-LLM integration passed.")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
