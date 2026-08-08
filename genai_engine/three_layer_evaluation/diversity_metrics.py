"""Semantic and lexical diversity metrics for generated scenario corpora."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .models import METHOD_CONDITION_NUMBERS, METHOD_LABELS, METHOD_ORDER, ScenarioScore


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+\-.]*", re.IGNORECASE)
DEFAULT_HASH_DIMS = 512
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DEPENDENCY_DIR = PROJECT_ROOT / ".codex_pydeps"
_SENTENCE_TRANSFORMER_CACHE: Dict[str, Any] = {}

if LOCAL_DEPENDENCY_DIR.exists() and str(LOCAL_DEPENDENCY_DIR) not in sys.path:
    sys.path.insert(0, str(LOCAL_DEPENDENCY_DIR))


def semantic_diversity_analysis(
    scores: Sequence[ScenarioScore],
    *,
    embedding_backend: str = "hash",
    embedding_model: str | None = None,
) -> List[Dict[str, Any]]:
    """Compute embedding diversity and Self-BLEU for each model x method corpus.

    The default backend is a deterministic local hashing embedding over scenario
    semantic fields. It keeps the evaluator reproducible without downloading
    sentence-transformer models. For final publication, callers can install a
    sentence-transformer backend and report the model name used.
    """

    grouped: Dict[Tuple[str, str], List[ScenarioScore]] = defaultdict(list)
    for score in scores:
        grouped[(score.model_key, score.method)].append(score)

    rows: List[Dict[str, Any]] = []
    for (model_key, method), group in sorted(grouped.items(), key=lambda item: (item[0][0], METHOD_ORDER.index(item[0][1]) if item[0][1] in METHOD_ORDER else 99)):
        texts = [_scenario_text_for_score(score) for score in sorted(group, key=lambda item: item.case_id)]
        texts = [text for text in texts if text.strip()]
        embeddings, backend_used, model_used = embed_texts(
            texts,
            backend=embedding_backend,
            model_name=embedding_model,
        )
        mean_cosine, embedding_diversity = pairwise_embedding_diversity(embeddings)
        self_bleu, self_bleu_backend = corpus_self_bleu_with_backend(texts)
        rows.append(
            {
                "granularity": "model_method",
                "model_key": model_key,
                "method": method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
                "condition_name": METHOD_LABELS.get(method, method),
                "n": len(texts),
                "embedding_backend": backend_used,
                "embedding_model": model_used,
                "mean_pairwise_cosine_similarity": mean_cosine,
                "embedding_diversity": embedding_diversity,
                "self_bleu_backend": self_bleu_backend,
                "self_bleu": self_bleu,
                "self_bleu_diversity": 1.0 - self_bleu if self_bleu is not None else None,
                "interpretation": _diversity_interpretation(embedding_diversity, self_bleu),
            }
        )
    return rows


def semantic_diversity_method_summary(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Average diversity rows across models for each generation method."""

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("granularity") == "model_method":
            grouped[str(row.get("method", ""))].append(row)

    summary: List[Dict[str, Any]] = []
    for method in METHOD_ORDER:
        method_rows = grouped.get(method, [])
        if not method_rows:
            continue
        summary.append(
            {
                "method": method,
                "condition_number": METHOD_CONDITION_NUMBERS.get(method, 0),
                "condition_name": METHOD_LABELS.get(method, method),
                "model_group_count": len(method_rows),
                "n_total": sum(int(row.get("n") or 0) for row in method_rows),
                "embedding_diversity_mean": _safe_mean(
                    [row.get("embedding_diversity") for row in method_rows if row.get("embedding_diversity") is not None]
                ),
                "mean_pairwise_cosine_similarity_mean": _safe_mean(
                    [
                        row.get("mean_pairwise_cosine_similarity")
                        for row in method_rows
                        if row.get("mean_pairwise_cosine_similarity") is not None
                    ]
                ),
                "self_bleu_mean": _safe_mean([row.get("self_bleu") for row in method_rows if row.get("self_bleu") is not None]),
                "self_bleu_diversity_mean": _safe_mean(
                    [row.get("self_bleu_diversity") for row in method_rows if row.get("self_bleu_diversity") is not None]
                ),
                "embedding_backend": "; ".join(sorted({str(row.get("embedding_backend")) for row in method_rows})),
                "embedding_model": "; ".join(sorted({str(row.get("embedding_model")) for row in method_rows})),
                "self_bleu_backend": "; ".join(sorted({str(row.get("self_bleu_backend")) for row in method_rows})),
            }
        )
    return summary


def embed_texts(
    texts: Sequence[str],
    *,
    backend: str = "hash",
    model_name: str | None = None,
) -> Tuple[List[List[float]], str, str]:
    """Embed texts using an optional sentence-transformer or deterministic fallback."""

    if backend in {"auto", "sentence_transformers"}:
        sentence_embeddings = _sentence_transformer_embeddings(texts, model_name)
        if sentence_embeddings is not None:
            return sentence_embeddings, "sentence_transformers", model_name or "sentence-transformers default"
        if backend == "sentence_transformers":
            raise RuntimeError("sentence_transformers backend requested but package/model is unavailable.")
    return [_hash_embedding(text) for text in texts], "local_hashing_ngram", f"scenario_structure_hashing_v1_{DEFAULT_HASH_DIMS}d"


def pairwise_embedding_diversity(embeddings: Sequence[Sequence[float]]) -> Tuple[float | None, float | None]:
    """Return mean pairwise cosine similarity and 1 - mean cosine similarity."""

    if len(embeddings) < 2:
        return None, None
    total = 0.0
    count = 0
    normalized = [_normalize_vector(vector) for vector in embeddings]
    for i in range(len(normalized)):
        left = normalized[i]
        for j in range(i + 1, len(normalized)):
            total += sum(a * b for a, b in zip(left, normalized[j]))
            count += 1
    if count == 0:
        return None, None
    mean_cosine = total / count
    return mean_cosine, 1.0 - mean_cosine


def corpus_self_bleu(texts: Sequence[str], *, max_order: int = 4) -> float | None:
    """Compute mean smoothed Self-BLEU for a corpus; lower is more diverse."""

    score, _backend = corpus_self_bleu_with_backend(texts, max_order=max_order)
    return score


def corpus_self_bleu_with_backend(texts: Sequence[str], *, max_order: int = 4) -> Tuple[float | None, str]:
    """Compute Self-BLEU and report which implementation was used."""

    sacrebleu_score = _sacrebleu_self_bleu(texts)
    if sacrebleu_score is not None:
        return sacrebleu_score, "sacrebleu_sentence_bleu"

    tokenized = [_tokens(text) for text in texts if text.strip()]
    if len(tokenized) < 2:
        return None, "internal_smoothed_bleu"
    ngram_counters_by_doc = [
        {n: Counter(_ngrams(tokens, n)) for n in range(1, max_order + 1)}
        for tokens in tokenized
    ]
    lengths = [len(tokens) for tokens in tokenized]
    scores = []
    for idx, candidate_tokens in enumerate(tokenized):
        references = [j for j in range(len(tokenized)) if j != idx]
        scores.append(_bleu_against_references(idx, candidate_tokens, references, ngram_counters_by_doc, lengths, max_order=max_order))
    return mean(scores), "internal_smoothed_bleu"


def _sacrebleu_self_bleu(texts: Sequence[str]) -> float | None:
    clean_texts = [_clean_text(text) for text in texts if _clean_text(text)]
    if len(clean_texts) < 2:
        return None
    try:
        from sacrebleu.metrics import BLEU  # type: ignore
    except Exception:
        return None
    try:
        bleu = BLEU(effective_order=True)
        scores = []
        for idx, candidate in enumerate(clean_texts):
            references = [text for ref_idx, text in enumerate(clean_texts) if ref_idx != idx]
            scores.append(float(bleu.sentence_score(candidate, references).score) / 100.0)
        return mean(scores)
    except Exception:
        return None


def _sentence_transformer_embeddings(texts: Sequence[str], model_name: str | None) -> List[List[float]] | None:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        return None
    try:
        resolved_model_name = model_name or "all-MiniLM-L6-v2"
        if resolved_model_name not in _SENTENCE_TRANSFORMER_CACHE:
            _SENTENCE_TRANSFORMER_CACHE[resolved_model_name] = SentenceTransformer(resolved_model_name)
        model = _SENTENCE_TRANSFORMER_CACHE[resolved_model_name]
        encode_texts = list(texts)
        if "e5" in resolved_model_name.lower():
            encode_texts = [f"passage: {text}" for text in encode_texts]
        vectors = model.encode(encode_texts, normalize_embeddings=True, show_progress_bar=False)
        return [[float(value) for value in vector] for vector in vectors]
    except Exception:
        return None


def _scenario_text_for_score(score: ScenarioScore) -> str:
    raw = _raw_for_score(score)
    scenario = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
    parts: List[str] = []
    for field in (
        "title",
        "opening_hook",
        "sender_or_caller",
        "from_address",
        "subject",
        "body_html",
        "correct_action",
        "hint_text",
        "attack_type",
        "channel",
        "variant",
        "role",
        "stage_id",
    ):
        if scenario.get(field):
            parts.append(str(scenario[field]))
    for list_field in (
        "messages",
        "dialogue",
        "red_flags",
        "safe_indicators",
        "attack_tactics",
        "psych_triggers",
        "learning_focus",
        "referenced_entities",
    ):
        values = scenario.get(list_field) or []
        if isinstance(values, list):
            parts.extend(str(value) for value in values if value)
    for choice in scenario.get("game_choices") or []:
        if isinstance(choice, dict):
            for key in ("label", "outcome", "feedback"):
                if choice.get(key):
                    parts.append(str(choice[key]))
    return _clean_text(" ".join(parts))


def _raw_for_score(score: ScenarioScore) -> Dict[str, Any]:
    try:
        with open(score.source_file, "r", encoding="utf-8") as handle:
            for current_line, line in enumerate(handle, start=1):
                if current_line == score.line_number:
                    return json.loads(line)
    except Exception:
        return {}
    return {}


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _hash_embedding(text: str, dims: int = DEFAULT_HASH_DIMS) -> List[float]:
    vector = [0.0] * dims
    tokens = _tokens(text)
    features: List[Tuple[str, float]] = []
    features.extend((f"tok:{token}", 1.0) for token in tokens)
    features.extend((f"bi:{a}_{b}", 1.4) for a, b in zip(tokens, tokens[1:]))
    features.extend((f"tri:{a}_{b}_{c}", 1.8) for a, b, c in zip(tokens, tokens[1:], tokens[2:]))
    compact = " ".join(tokens)
    for idx in range(max(0, len(compact) - 4)):
        features.append((f"char:{compact[idx:idx + 5]}", 0.35))
    for feature, weight in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign * weight
    return _normalize_vector(vector)


def _normalize_vector(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0 for _ in vector]
    return [float(value) / norm for value in vector]


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(_clean_text(text)) if len(token) > 1]


def _ngrams(tokens: Sequence[str], n: int) -> List[Tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[idx : idx + n]) for idx in range(0, len(tokens) - n + 1)]


def _bleu_against_references(
    candidate_index: int,
    candidate_tokens: Sequence[str],
    reference_indices: Sequence[int],
    counters_by_doc: Sequence[Dict[int, Counter]],
    lengths: Sequence[int],
    *,
    max_order: int = 4,
) -> float:
    if not candidate_tokens:
        return 0.0
    log_precision_sum = 0.0
    for n in range(1, max_order + 1):
        candidate_counts = counters_by_doc[candidate_index][n]
        if not candidate_counts:
            log_precision_sum += math.log(1.0 / (len(candidate_tokens) + 1.0))
            continue
        reference_max: Counter = Counter()
        for ref_idx in reference_indices:
            for ngram, count in counters_by_doc[ref_idx][n].items():
                if count > reference_max[ngram]:
                    reference_max[ngram] = count
        overlap = sum(min(count, reference_max.get(ngram, 0)) for ngram, count in candidate_counts.items())
        total = sum(candidate_counts.values())
        precision = (overlap + 1.0) / (total + 1.0)
        log_precision_sum += math.log(precision)

    candidate_len = len(candidate_tokens)
    reference_lengths = [lengths[idx] for idx in reference_indices if lengths[idx] > 0]
    if not reference_lengths:
        brevity_penalty = 1.0
    else:
        closest_ref_len = min(reference_lengths, key=lambda ref_len: (abs(ref_len - candidate_len), ref_len))
        brevity_penalty = 1.0 if candidate_len > closest_ref_len else math.exp(1.0 - closest_ref_len / max(1, candidate_len))
    return brevity_penalty * math.exp(log_precision_sum / max_order)


def _diversity_interpretation(embedding_diversity: float | None, self_bleu: float | None) -> str:
    if embedding_diversity is None and self_bleu is None:
        return "not available"
    return "relative within-study comparison only; no universal diversity threshold is applied"


def _safe_mean(values: Sequence[Any]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None
