#!/usr/bin/env python3
"""Compute lightweight judge agreement statistics from judge_scores_long.csv.

This script intentionally avoids heavy dependencies. It exports simple percent
agreement on ordinal qualifier labels and leaves Fleiss' Kappa /
Krippendorff's Alpha as optional extensions for a statistics environment.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Tuple


def read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def percent_agreement(rows: List[Dict[str, str]]) -> Dict[str, float]:
    by_item: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for row in rows:
        key = (row.get("scenario_id", ""), row.get("criterion", ""))
        if row.get("qualifier"):
            by_item[key].append(row["qualifier"])

    agreements = []
    for labels in by_item.values():
        if len(labels) < 2:
            continue
        pairs = list(combinations(labels, 2))
        agreements.extend(1.0 if a == b else 0.0 for a, b in pairs)
    return {
        "pairwise_percent_agreement": round(sum(agreements) / len(agreements), 4) if agreements else 0.0,
        "rated_items": len(by_item),
        "pair_count": len(agreements),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute agreement statistics for PersonaShield judge exports.")
    parser.add_argument("judge_scores_long_csv", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.judge_scores_long_csv)
    result = {
        **percent_agreement(rows),
        "fleiss_kappa": None,
        "krippendorff_alpha": None,
        "notes": (
            "Fleiss' Kappa and Krippendorff's Alpha are intentionally left as optional "
            "extensions. Use statsmodels, scipy, or krippendorff in a publication "
            "analysis environment if full agreement statistics are required."
        ),
    }
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
