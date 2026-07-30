from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and display the newest one-scenario live-model run."
    )
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    run_directories = sorted(
        (
            path
            for path in args.output_root.iterdir()
            if path.is_dir() and (path / "scenarios.jsonl").is_file()
        ),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not run_directories:
        raise SystemExit(f"No live scenario run was found under: {args.output_root}")

    run_directory = run_directories[0]
    rows = [
        json.loads(line)
        for line in (run_directory / "scenarios.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if len(rows) != 1:
        raise SystemExit(f"Expected exactly one scenario row; found {len(rows)}.")

    row = rows[0]
    if not row.get("used_live_llm") or row.get("used_fallback"):
        raise SystemExit("The scenario was not produced by a live LLM response.")
    if not isinstance(row.get("scenario"), dict):
        raise SystemExit("The live run did not contain a scenario JSON object.")

    latest_path = args.output_root / "LATEST_LIVE_SCENARIO.json"
    latest_path.write_text(
        json.dumps(row, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if not row.get("validation_passed"):
        issues = json.dumps(row.get("validation_issues", []), ensure_ascii=False)
        raise SystemExit(
            "The live scenario was saved but failed engine validation.\n"
            f"Saved result: {latest_path}\n"
            f"Validation issues: {issues}"
        )

    print("Live scenario validation passed.")
    print(f"Run directory: {run_directory}")
    print(f"Readable result: {latest_path}")
    print(json.dumps(row["scenario"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
