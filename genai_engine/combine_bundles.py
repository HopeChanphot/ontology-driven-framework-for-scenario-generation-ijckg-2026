#!/usr/bin/env python3
"""
combine_bundles.py
------------------
Combines all per-bundle JSON files in content_bundles/ into one
scenario_pool.json that ScenarioLoader.gd can consume.

v4.1 layout keeps backward-friendly keys:
  {
    "_meta": {...},
    "_game_system": {...},
    "<persona_path_id>": {
      "_profile": {...},
      "_learning": {...},
      "_rules": {...},
      "_gsdl": {...},
      "_bundle_meta": {...},
      "sms": {"fake": {"gpt_nano": {...}}, "real": {...}},
      "email": {...},
      "voice": {...}
    }
  }
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_INPUT = Path(__file__).resolve().parent / "content_bundles"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "scenario_pool" / "scenario_pool.json"
ALLOWED_LLMS = {"gpt_nano", "qwen3_8b", "mistral_7b"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine content bundles into one scenario_pool.json")
    parser.add_argument("--input", "-i", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--no-pretty", action="store_true")
    parser.add_argument("--overwrite-duplicates", action="store_true")
    return parser.parse_args()


def load_bundle(path: Path) -> Tuple[Optional[dict], Optional[str]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return None, f"failed to read {path.name}: {exc}"

    required = {
        "persona_path_id",
        "llm_key",
        "scenario_pool",
        "persona_profile",
        "learning_criteria",
        "gameplay_rules",
    }
    missing = required - set(data.keys())
    if missing:
        return None, f"missing keys: {sorted(missing)}"
    if not isinstance(data["scenario_pool"], list):
        return None, "scenario_pool must be a list"
    return data, None


def ensure_slot(pool: Dict, pid: str, channel: str, variant: str) -> None:
    pool.setdefault(pid, {})
    pool[pid].setdefault(channel, {})
    pool[pid][channel].setdefault(variant, {})


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        print(f"Input folder does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    final_pool: Dict[str, dict] = {}
    game_system_snapshot = None
    files = sorted(input_dir.glob("*.json"))
    total_scenarios = 0
    loaded_bundles = 0
    skipped_files = []

    for path in files:
        bundle, error = load_bundle(path)
        if error:
            skipped_files.append({"file": path.name, "error": error})
            continue

        llm_key = bundle["llm_key"]
        if llm_key not in ALLOWED_LLMS:
            skipped_files.append({"file": path.name, "error": f"unsupported llm_key {llm_key}"})
            continue

        pid = bundle["persona_path_id"]
        entry = final_pool.setdefault(
            pid,
            {
                "_profile": bundle["persona_profile"],
                "_learning": bundle["learning_criteria"],
                "_rules": bundle["gameplay_rules"],
                "_gsdl": bundle.get("gsdl_descriptor", {}),
                "_bundle_meta": {
                    "engine_version": bundle.get("engine_version", "v4.1"),
                    "persona_id": bundle.get("persona_id"),
                    "created_at": bundle.get("created_at"),
                    "generation_notes": bundle.get("generation_notes", {}),
                },
            },
        )

        if game_system_snapshot is None and bundle.get("game_system"):
            game_system_snapshot = bundle["game_system"]

        for scenario in bundle["scenario_pool"]:
            channel = scenario["channel"]
            variant = scenario["variant"]
            ensure_slot(final_pool, pid, channel, variant)
            existing = entry[channel][variant].get(llm_key)
            if existing and not args.overwrite_duplicates:
                continue
            entry[channel][variant][llm_key] = scenario
            total_scenarios += 1

        loaded_bundles += 1

    payload = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": "v4.1",
            "total_bundle_files_seen": len(files),
            "total_bundles_loaded": loaded_bundles,
            "total_persona_paths": len(final_pool),
            "total_scenarios_written": total_scenarios,
            "skipped_files": skipped_files,
        },
        "_game_system": game_system_snapshot or {},
        **final_pool,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=None if args.no_pretty else 2)

    print(f"Wrote scenario pool to: {output_path}")
    print(f"Persona paths: {len(final_pool)} | Bundles loaded: {loaded_bundles} | Scenarios: {total_scenarios}")
    if skipped_files:
        print(f"Skipped files: {len(skipped_files)}")


if __name__ == "__main__":
    main()
