"""
Audit a generated scenario_pool.json for quality, contamination, repetition,
and stage-fit issues.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from validator import BundleValidator


def iter_scenarios(pool: dict):
    for persona_path, payload in pool.items():
        if persona_path.startswith("_"):
            continue
        for channel in ("sms", "email", "voice"):
            if channel not in payload:
                continue
            for variant in ("fake", "real"):
                slot = payload[channel].get(variant, {})
                for llm_key, scenario in slot.items():
                    if isinstance(scenario, dict) and "scenario_id" in scenario:
                        yield persona_path, llm_key, scenario


def normalize(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"[^a-zA-Z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario_pool", nargs="?", default="scenario_pool.json")
    args = ap.parse_args()

    path = Path(args.scenario_pool)
    pool = json.loads(path.read_text(encoding="utf-8"))
    validator = BundleValidator()

    counters = Counter()
    title_counter = Counter()
    hook_counter = Counter()
    choice_counter = Counter()
    by_llm = defaultdict(Counter)

    for persona_path, llm_key, scenario in iter_scenarios(pool):
        counters["scenarios"] += 1
        by_llm[llm_key]["scenarios"] += 1

        title_counter[normalize(scenario.get("title", ""))] += 1
        hook_counter[normalize(scenario.get("opening_hook", ""))] += 1
        choice_sig = "|".join(normalize(c.get("label", "")) for c in scenario.get("game_choices", []))
        choice_counter[choice_sig] += 1

        ok, issues = validator.validate_scenario(
            scenario,
            scenario["channel"],
            scenario["variant"],
            scenario["stage_index"],
            scenario["vocabulary_band"],
            scenario["knowledge_type"],
            scenario["role"],
        )
        if not ok:
            counters["invalid"] += 1
            by_llm[llm_key]["invalid"] += 1

        if scenario.get("variant") == "fake" and scenario.get("safe_indicators"):
            counters["fake_contamination"] += 1
            by_llm[llm_key]["fake_contamination"] += 1

        if scenario.get("variant") == "real" and (scenario.get("attack_tactics") or scenario.get("psych_triggers") or scenario.get("red_flags")):
            counters["real_contamination"] += 1
            by_llm[llm_key]["real_contamination"] += 1

        if any(x in json.dumps(scenario, ensure_ascii=False).lower() for x in ["company_name", "manager_name", "tool_1", "tool1"]):
            counters["placeholder_leak"] += 1
            by_llm[llm_key]["placeholder_leak"] += 1

        if scenario.get("quality_score", 0) <= 0:
            counters["zero_quality"] += 1
            by_llm[llm_key]["zero_quality"] += 1

        rag_count = int((scenario.get('generation_meta') or {}).get('rag_example_count', 0) or (((scenario.get('generation_meta') or {}).get('llm_metrics') or {}).get('rag_count', 0) or 0))
        if rag_count <= 0:
            counters["zero_rag_grounding"] += 1
            by_llm[llm_key]["zero_rag_grounding"] += 1

    report = {
        "file": str(path),
        "totals": dict(counters),
        "repetition": {
            "repeated_titles": sum(1 for _, v in title_counter.items() if v > 1),
            "repeated_hooks": sum(1 for _, v in hook_counter.items() if v > 1),
            "repeated_choice_patterns": sum(1 for _, v in choice_counter.items() if v > 1),
        },
        "by_llm": {k: dict(v) for k, v in by_llm.items()},
        "top_repeated_titles": title_counter.most_common(10),
        "top_repeated_hooks": hook_counter.most_common(10),
        "top_repeated_choice_patterns": choice_counter.most_common(10),
    }

    out_json = path.with_name(path.stem + "_audit.json")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved audit report to {out_json}")


if __name__ == "__main__":
    main()
