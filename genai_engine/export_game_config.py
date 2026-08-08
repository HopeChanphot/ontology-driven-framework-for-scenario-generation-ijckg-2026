
#!/usr/bin/env python3
"""
export_game_config.py
---------------------
Writes the formal game-system configuration to JSON for Godot or other runtime use.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from game_system import build_game_system_config


def parse_args():
    parser = argparse.ArgumentParser(description="Export PersonaShield Quest v4.1 game system config to JSON")
    parser.add_argument(
        "--output",
        "-o",
        default=str(Path(__file__).resolve().parent / "scenario_pool" / "game_system_config.json"),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_game_system_config().model_dump()
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote game system config to: {output_path}")


if __name__ == "__main__":
    main()
