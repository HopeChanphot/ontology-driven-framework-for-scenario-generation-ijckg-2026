from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import venv
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "genai_engine"
ONTOLOGY_ROOT = ROOT / "ontology"
ONTOLOGY_PATH = ONTOLOGY_ROOT / "ontology" / "personashield-psq-sco-v9.1.owl"
QUERIES_DIR = ONTOLOGY_ROOT / "queries" / "v9_1"
HERMIT_REPORT = ONTOLOGY_ROOT / "outputs" / "v9_1" / "hermit-reasoner-report.json"
VENV_DIR = ROOT / ".venv"
OUTPUT_ROOT = ROOT / ".macos_test_output"
ONTOLOGY_TEST_ROOT = OUTPUT_ROOT / "ontology"
GENERATION_ROOT = OUTPUT_ROOT / "generation"
EVALUATION_ROOT = OUTPUT_ROOT / "evaluation"
EXPECTED_MODES = {
    "prompt_only",
    "prompt_rag",
    "ontology_prompt_rag",
    "ontology_text_rag",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the named Chanphot macOS environment and run the portable "
            "PSQ-SCO ontology, four-mode generation, evaluation, and test workflow."
        )
    )
    parser.add_argument(
        "--environment-name",
        default="chanphot-psq-sco",
        help="Virtual-environment prompt name. Default: chanphot-psq-sco.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Matched cases to generate in each of the four modes. Default: 1.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Reuse an existing .venv without installing or updating packages.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Run setup, ontology checks, generation, and evaluation but skip unit tests.",
    )
    parser.add_argument(
        "--use-current-python",
        action="store_true",
        help="Maintainer/CI option: use the current interpreter instead of creating .venv.",
    )
    parser.add_argument(
        "--allow-non-macos",
        action="store_true",
        help="Maintainer/CI option: allow the portable workflow to run outside macOS.",
    )
    return parser.parse_args()


def run(
    label: str,
    command: Iterable[object],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    rendered = [str(part) for part in command]
    print(f"\n==> {label}", flush=True)
    print(" ".join(shlex.quote(part) for part in rendered), flush=True)
    subprocess.run(rendered, cwd=cwd, env=env, check=True)


def require_python_312() -> None:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit(
            "Python 3.12 is required by the portable package's offline "
            "wheelhouses. Use Python 3.12 or the portable installer."
        )


def environment_python(args: argparse.Namespace) -> Path:
    if args.use_current_python:
        return Path(sys.executable).resolve()

    if args.skip_install and not VENV_DIR.exists():
        raise SystemExit("--skip-install requires an existing .venv. Run once without it.")

    if not VENV_DIR.exists():
        print(
            f"Creating Python environment '{args.environment_name}' at {VENV_DIR}",
            flush=True,
        )
        venv.EnvBuilder(
            with_pip=True,
            clear=False,
            symlinks=platform.system() != "Windows",
            prompt=args.environment_name,
        ).create(VENV_DIR)

    if platform.system() == "Windows":
        python_path = VENV_DIR / "Scripts" / "python.exe"
    else:
        python_path = VENV_DIR / "bin" / "python"
    if not python_path.is_file():
        raise SystemExit(f"Virtual-environment Python was not created: {python_path}")
    return python_path


def latest_directory(parent: Path) -> Path:
    directories = [path for path in parent.iterdir() if path.is_dir()]
    if not directories:
        raise SystemExit(f"No output directory was created under: {parent}")
    return max(directories, key=lambda path: path.stat().st_mtime_ns)


def validate_generation(run_dir: Path) -> Path:
    scenario_path = run_dir / "scenarios.jsonl"
    if not scenario_path.is_file():
        raise SystemExit(f"Missing four-mode output: {scenario_path}")

    rows = [
        json.loads(line)
        for line in scenario_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    actual_modes = {str(row.get("mode")) for row in rows}
    missing_modes = sorted(EXPECTED_MODES - actual_modes)
    if missing_modes:
        raise SystemExit(f"Generation is missing modes: {', '.join(missing_modes)}")

    invalid_modes = sorted(
        str(row.get("mode"))
        for row in rows
        if not row.get("validation_passed")
    )
    if invalid_modes:
        raise SystemExit(
            "Generated scenarios failed engine validation in: "
            + ", ".join(invalid_modes)
        )

    prompt_rag_rows = [row for row in rows if row.get("mode") == "prompt_rag"]
    if not prompt_rag_rows or not prompt_rag_rows[0].get("rag_examples"):
        raise SystemExit("prompt_rag did not retrieve the included synthetic fixture.")

    print(
        f"Four-mode generation passed: {len(rows)} rows across "
        f"{', '.join(sorted(actual_modes))}"
    )
    return scenario_path


def validate_evaluation(run_dir: Path) -> None:
    required = (
        "ontology_validation.json",
        "scenario_scores.csv",
        "method_summary.csv",
        "evaluation_report.md",
        "run_metadata.json",
    )
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        raise SystemExit(
            "Evaluation is missing required outputs: " + ", ".join(missing)
        )

    metadata = json.loads(
        (run_dir / "run_metadata.json").read_text(encoding="utf-8")
    )
    record_count = int(metadata.get("scenario_record_count", 0))
    if record_count < 4:
        raise SystemExit("Evaluation loaded fewer than four scenario rows.")
    print(f"Three-layer evaluation passed: {record_count} scenario rows.")


def main() -> int:
    args = parse_args()
    require_python_312()
    if platform.system() != "Darwin" and not args.allow_non_macos:
        raise SystemExit(
            "This entry point is intended for macOS. Maintainers may use "
            "--allow-non-macos for portability validation."
        )
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1.")

    python = environment_python(args)
    if not args.skip_install and not args.use_current_python:
        run(
            "Upgrade pip",
            [python, "-m", "pip", "install", "--upgrade", "pip"],
        )
        run(
            "Install the macOS smoke and test environment",
            [python, "-m", "pip", "install", "-r", ROOT / "requirements-macos.txt"],
        )

    run(
        "Verify package checksums",
        [python, ROOT / "tools" / "package_integrity.py", "verify"],
    )
    ONTOLOGY_TEST_ROOT.mkdir(parents=True, exist_ok=True)
    run(
        "Run ontology competency questions",
        [
            python,
            ONTOLOGY_ROOT / "scripts" / "run_sparql_cq_v9_1.py",
            "--cq",
            "all",
            "--output",
            ONTOLOGY_TEST_ROOT / "sparql-cq-full-run-report.json",
        ],
    )
    run(
        "Run ontology validation cases",
        [
            python,
            ONTOLOGY_ROOT / "scripts" / "run_sparql_cq_v9_1.py",
            "--validate-cases",
            "--output",
            ONTOLOGY_TEST_ROOT / "sparql-cq-validation-report.json",
        ],
    )

    GENERATION_ROOT.mkdir(parents=True, exist_ok=True)
    generation_env = os.environ.copy()
    generation_env["PSQ_KB_DIR"] = str(ENGINE_ROOT / "minimal_kb")
    generation_env["PSQ_FORCE_LEXICAL_RAG"] = "1"
    run(
        "Generate one matched case in all four offline modes",
        [
            python,
            "generate_scenarios_sco.py",
            "--ontology-path",
            ONTOLOGY_PATH,
            "--mode",
            "all_modes",
            "--case-set",
            "single",
            "--limit",
            args.limit,
            "--llm",
            "qwen2_5_7b",
            "--out-dir",
            GENERATION_ROOT,
            "--dry-run",
            "--no-progress",
        ],
        cwd=ENGINE_ROOT,
        env=generation_env,
    )
    generation_run = latest_directory(GENERATION_ROOT)
    validate_generation(generation_run)

    per_mode_files = [
        generation_run / f"scenarios_{mode}.jsonl"
        for mode in (
            "prompt_only",
            "prompt_rag",
            "ontology_prompt_rag",
            "ontology_text_rag",
        )
    ]
    missing_inputs = [path for path in per_mode_files if not path.is_file()]
    if missing_inputs:
        raise SystemExit(
            "Missing evaluation inputs: " + ", ".join(map(str, missing_inputs))
        )

    EVALUATION_ROOT.mkdir(parents=True, exist_ok=True)
    evaluation_command: list[object] = [
        python,
        "evaluate_three_layer.py",
        "--ontology-root",
        ONTOLOGY_ROOT,
        "--ontology-path",
        ONTOLOGY_PATH,
        "--queries-dir",
        QUERIES_DIR,
        "--hermit-report",
        HERMIT_REPORT,
        "--out-dir",
        EVALUATION_ROOT,
        "--diversity-embedding-backend",
        "hash",
        "--standard-metrics-only",
        "--smoke-report",
    ]
    for input_path in per_mode_files:
        evaluation_command.extend(["--input-dir", input_path])
    run(
        "Evaluate the four generated scenarios",
        evaluation_command,
        cwd=ENGINE_ROOT,
    )
    evaluation_run = latest_directory(EVALUATION_ROOT)
    validate_evaluation(evaluation_run)

    if not args.skip_tests:
        run(
            "Run the primary portable test suite",
            [
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                "test_*.py",
                "-v",
            ],
            cwd=ENGINE_ROOT,
        )
        run(
            "Run the targeted evaluation test suite",
            [
                python,
                "-m",
                "unittest",
                "discover",
                "-s",
                "targeted_evaluation_repair/tests",
                "-p",
                "test_*.py",
                "-v",
            ],
            cwd=ENGINE_ROOT,
        )

    print("\nPSQ-SCO macOS test workflow passed.")
    print(f"Generation output: {generation_run}")
    print(f"Evaluation report: {evaluation_run / 'evaluation_report.md'}")
    if args.use_current_python:
        print(f"Current Python used for maintainer/CI validation: {python}")
    else:
        print(f"Environment name: {args.environment_name}")
        print(f"Environment folder: {VENV_DIR}")
        print(f"Activate later with: source {shlex.quote(str(VENV_DIR / 'bin' / 'activate'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
