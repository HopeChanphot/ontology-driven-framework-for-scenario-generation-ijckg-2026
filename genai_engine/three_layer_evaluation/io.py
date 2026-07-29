"""Input/output helpers for generated scenario evaluation files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from .models import ScenarioRecord


DEFAULT_SCENARIO_PATTERNS = (
    "scenarios*.jsonl",
    "*paper_120_live_recovered.jsonl",
    "scenarios_all.jsonl",
    "progress.jsonl",
)


def discover_scenario_files(
    roots: Sequence[Path],
    *,
    patterns: Sequence[str] = DEFAULT_SCENARIO_PATTERNS,
    include_progress: bool = False,
) -> List[Path]:
    """Find generated JSONL scenario files under one or more output roots."""

    files: List[Path] = []
    seen = set()
    for root in roots:
        if root.is_file() and root.suffix.lower() == ".jsonl":
            candidates = [root]
        elif root.exists():
            candidates = []
            for pattern in patterns:
                candidates.extend(root.rglob(pattern))
        else:
            continue
        for path in candidates:
            name = path.name.lower()
            if not include_progress and name == "progress.jsonl":
                continue
            if path.stat().st_size == 0:
                continue
            resolved = str(path.resolve()).lower()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files)


def load_jsonl_records(files: Iterable[Path], *, limit: int = 0, dedupe: bool = True) -> List[ScenarioRecord]:
    """Load generated scenario JSONL rows, preserving malformed rows as errors."""

    records: List[ScenarioRecord] = []
    keyed_records: Dict[str, ScenarioRecord] = {}
    key_order: List[str] = []
    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    dedupe_key = _record_key(raw)
                    record = ScenarioRecord(str(path), line_number, raw)
                    if dedupe and dedupe_key:
                        if dedupe_key not in keyed_records:
                            key_order.append(dedupe_key)
                            keyed_records[dedupe_key] = record
                        elif _record_rank(record.raw) >= _record_rank(keyed_records[dedupe_key].raw):
                            keyed_records[dedupe_key] = record
                    else:
                        records.append(record)
                except json.JSONDecodeError as exc:
                    records.append(
                        ScenarioRecord(
                            str(path),
                            line_number,
                            raw={},
                            parse_error=f"{type(exc).__name__}: {exc}",
                        )
                    )
                if limit > 0 and (len(records) + len(keyed_records)) >= limit:
                    break
    if dedupe:
        records.extend(keyed_records[key] for key in key_order)
    return records[:limit] if limit > 0 else records


def _record_key(raw: Dict) -> str:
    result_key = raw.get("result_key")
    if result_key:
        return str(result_key)
    scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
    case = raw.get("case") if isinstance(raw.get("case"), dict) else {}
    mode = raw.get("mode") or scenario.get("generation_meta", {}).get("mode") or ""
    if "prompt_only" in str(mode) or "default_template" in str(mode):
        mode = "prompt_only"
    return "|".join(
        str(part)
        for part in (
            raw.get("llm_key", ""),
            case.get("case_id", ""),
            mode,
        )
    )


def _record_rank(raw: Dict) -> tuple:
    """Prefer successful live rows over fallback/error rows for resumed runs."""

    prompt_metadata = raw.get("prompt_metadata") if isinstance(raw.get("prompt_metadata"), dict) else {}
    error = prompt_metadata.get("generation_error") or prompt_metadata.get("live_llm_error")
    return (
        1 if raw.get("used_live_llm") else 0,
        0 if raw.get("used_fallback") else 1,
        0 if error else 1,
    )


def write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
