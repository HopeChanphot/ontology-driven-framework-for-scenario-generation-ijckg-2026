
from __future__ import annotations
import hashlib, json, logging, os, re
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import KB_DIR, PROJECT_ROOT, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
except Exception:
    chromadb = None
    Settings = None

if os.getenv("PSQ_FORCE_LEXICAL_RAG", "").strip().lower() in {"1", "true", "yes"}:
    chromadb = None
    Settings = None

PROFILE_FILE_PATTERNS = {
    "quality": [
        "auto_English_NonScam_ham_en.jsonl","auto_English_Scam_scam_en.jsonl",
        "auto_IRS_CompleteCall_Transcript_scam_en.jsonl",
        "auto_smsfraud_scam_th.jsonl","auto_smsnormal_ham_th.jsonl",
        "auto_dataset_kaggle_ham_en.jsonl","auto_dataset_kaggle_scam_en.jsonl",
        "auto_CEAS_08_ham_en.jsonl","auto_CEAS_08_scam_en.jsonl",
        "auto_Enron_ham_en.jsonl","auto_SpamAssasin_ham_en.jsonl","auto_SpamAssasin_scam_en.jsonl",
        "auto_Ling_ham_en.jsonl","auto_Ling_scam_en.jsonl",
        "auto_Nazario_scam_en.jsonl","auto_Nazario_5_scam_en.jsonl",
        "auto_financialfraud_ham_th.jsonl","auto_NCSA_Virtaul_Summit_1_Presentation_TB-CERT_ham_th.jsonl",
    ],
    "balanced": [
        "auto_English_NonScam_ham_en.jsonl","auto_English_Scam_scam_en.jsonl",
        "auto_IRS_CompleteCall_Transcript_scam_en.jsonl",
        "auto_smsfraud_scam_th.jsonl","auto_smsnormal_ham_th.jsonl",
        "auto_dataset_kaggle_ham_en.jsonl","auto_dataset_kaggle_scam_en.jsonl",
        "auto_CEAS_08_ham_en.jsonl","auto_CEAS_08_scam_en.jsonl",
        "auto_Enron_ham_en.jsonl","auto_SpamAssasin_ham_en.jsonl","auto_SpamAssasin_scam_en.jsonl",
        "auto_Ling_ham_en.jsonl","auto_Ling_scam_en.jsonl",
        "auto_Nazario_scam_en.jsonl","auto_Nazario_5_scam_en.jsonl",
        "auto_TREC_05_ham_en.jsonl","auto_TREC_05_scam_en.jsonl",
        "auto_TREC_06_ham_en.jsonl","auto_TREC_06_scam_en.jsonl",
        "auto_TREC_07_ham_en.jsonl","auto_TREC_07_scam_en.jsonl",
        "auto_financialfraud_ham_th.jsonl","auto_NCSA_Virtaul_Summit_1_Presentation_TB-CERT_ham_th.jsonl",
    ],
    "full": [],
}

PROFILE_MAX_DOCS_PER_FILE = {
    "quality": {
        "auto_CEAS_08_ham_en.jsonl": 5000, "auto_CEAS_08_scam_en.jsonl": 5000,
        "auto_Enron_ham_en.jsonl": 6000,
        "auto_SpamAssasin_ham_en.jsonl": 2500, "auto_SpamAssasin_scam_en.jsonl": 2500,
        "auto_Ling_ham_en.jsonl": 2000, "auto_Ling_scam_en.jsonl": 2000,
        "auto_Nazario_scam_en.jsonl": 2500, "auto_Nazario_5_scam_en.jsonl": 2500,
        "auto_dataset_kaggle_ham_en.jsonl": 1200, "auto_dataset_kaggle_scam_en.jsonl": 1200,
        "auto_English_NonScam_ham_en.jsonl": 400, "auto_English_Scam_scam_en.jsonl": 400,
        "auto_IRS_CompleteCall_Transcript_scam_en.jsonl": 300,
        "auto_smsfraud_scam_th.jsonl": 357, "auto_smsnormal_ham_th.jsonl": 355,
        "auto_financialfraud_ham_th.jsonl": 27, "auto_NCSA_Virtaul_Summit_1_Presentation_TB-CERT_ham_th.jsonl": 30,
    },
    "balanced": {
        "auto_CEAS_08_ham_en.jsonl": 8000, "auto_CEAS_08_scam_en.jsonl": 8000,
        "auto_Enron_ham_en.jsonl": 10000,
        "auto_SpamAssasin_ham_en.jsonl": 4000, "auto_SpamAssasin_scam_en.jsonl": 4000,
        "auto_Ling_ham_en.jsonl": 2500, "auto_Ling_scam_en.jsonl": 2500,
        "auto_Nazario_scam_en.jsonl": 3000, "auto_Nazario_5_scam_en.jsonl": 3000,
        "auto_TREC_05_ham_en.jsonl": 4000, "auto_TREC_05_scam_en.jsonl": 4000,
        "auto_TREC_06_ham_en.jsonl": 3000, "auto_TREC_06_scam_en.jsonl": 3000,
        "auto_TREC_07_ham_en.jsonl": 4000, "auto_TREC_07_scam_en.jsonl": 4000,
        "auto_dataset_kaggle_ham_en.jsonl": 2000, "auto_dataset_kaggle_scam_en.jsonl": 2000,
        "auto_English_NonScam_ham_en.jsonl": 400, "auto_English_Scam_scam_en.jsonl": 400,
        "auto_IRS_CompleteCall_Transcript_scam_en.jsonl": 300,
        "auto_smsfraud_scam_th.jsonl": 357, "auto_smsnormal_ham_th.jsonl": 355,
        "auto_financialfraud_ham_th.jsonl": 27, "auto_NCSA_Virtaul_Summit_1_Presentation_TB-CERT_ham_th.jsonl": 30,
    },
    "full": {},
}

def _scalarize(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)):
        return v
    if v is None:
        return "unknown"
    if isinstance(v, list):
        return "|".join(str(x) for x in v[:20]) if v else "unknown"
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)[:1000]
    return str(v)

class RAGEngine:
    def __init__(self, persist_dir: Optional[str] = None) -> None:
        self.profile = os.getenv("PSQ_RAG_PROFILE", "quality").strip().lower()
        if self.profile not in {"quality","balanced","full"}:
            self.profile = "quality"
        self.batch_size = int(os.getenv("PSQ_RAG_BATCH_SIZE", "1000"))
        self._persist_dir = Path(persist_dir or str(PROJECT_ROOT / f"chroma_db_{self.profile}"))
        self._meta_path = self._persist_dir / ".kb_meta.json"
        self._collection_name = f"scenario_examples_{self.profile}"
        self._collection = None
        self._indexed = False
        self._fallback_docs: Optional[List[Dict[str, Any]]] = None
        self.last_error: Optional[Dict[str, str]] = None
        self._retrieval_disabled_reason: Optional[str] = None
        self.client = None
        if chromadb is None:
            logger.warning("chromadb not installed; using JSONL lexical RAG fallback")
            return
        self.client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

    def _ensure_collection(self):
        if chromadb is None or self.client is None:
            return None
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    @property
    def collection(self):
        return self._ensure_collection()

    def _selected_files(self) -> List[Path]:
        all_files = []
        for channel_dir in sorted(KB_DIR.iterdir()):
            if channel_dir.is_dir():
                all_files.extend(sorted(channel_dir.glob("*.jsonl")))
        if self.profile == "full":
            return all_files
        wanted = set(PROFILE_FILE_PATTERNS[self.profile])
        selected = [fp for fp in all_files if fp.name in wanted]
        return selected or all_files

    def _max_docs_for(self, filename: str):
        return PROFILE_MAX_DOCS_PER_FILE[self.profile].get(filename)

    def _compute_fingerprint(self, files: List[Path]) -> str:
        payload = {
            "profile": self.profile,
            "files": [{"name": fp.name, "size": fp.stat().st_size, "mtime_ns": fp.stat().st_mtime_ns, "cap": self._max_docs_for(fp.name)} for fp in files],
            "batch_size": self.batch_size,
        }
        return hashlib.md5(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def _load_meta(self) -> Dict[str, Any]:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_meta(self, payload: Dict[str, Any]) -> None:
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _entry_to_text(self, entry: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ["text","subject","body_text","body_html","title","opening_hook","correct_action"]:
            if entry.get(key):
                parts.append(str(entry[key]))
        if entry.get("messages"):
            parts.append(" ".join(str(x) for x in entry.get("messages", []) if x))
        if entry.get("dialogue"):
            turns = []
            for d in entry.get("dialogue", []):
                turns.append(str(d.get("text","")) if isinstance(d, dict) else str(d))
            parts.append(" ".join(turns))
        for key in ["red_flags","safe_indicators","attack_tactics","psych_triggers","learning_focus"]:
            if entry.get(key):
                parts.append(" ".join(str(x) for x in entry[key]) if isinstance(entry[key], list) else str(entry[key]))
        return "\n".join(p.strip() for p in parts if str(p).strip())

    def index_knowledge_base(self, force: bool = False, scam_only: bool = False) -> int:
        if chromadb is None or self.client is None:
            return self._ensure_fallback_docs(force=force, scam_only=scam_only)
        files = self._selected_files()
        if not files:
            logger.warning("No JSONL files selected for profile=%s under KB_DIR=%s", self.profile, KB_DIR)
            self._indexed = True
            return 0

        current_fp = self._compute_fingerprint(files)
        saved = self._load_meta()
        existing_count = self.collection.count()

        if not force and saved.get("fingerprint") == current_fp and existing_count > 0:
            self._indexed = True
            logger.info("RAG reuse: profile=%s fingerprint unchanged, using existing index with %s docs", self.profile, existing_count)
            return existing_count

        if force or existing_count > 0:
            try:
                self.client.delete_collection(self._collection_name)
            except Exception:
                pass
            self._collection = None
            self._ensure_collection()

        docs, metas, ids = [], [], []
        seen_hashes = set()
        skipped_dupes = 0
        logger.info("RAG indexing from KB_DIR=%s | profile=%s | selected_files=%s", KB_DIR, self.profile, len(files))

        for jsonl_file in files:
            file_kept = 0
            max_docs = self._max_docs_for(jsonl_file.name)
            channel = jsonl_file.parent.name
            with jsonl_file.open("r", encoding="utf-8") as f:
                for line_num, line in enumerate(f):
                    if max_docs is not None and file_kept >= max_docs:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if scam_only and entry.get("is_scam") is False:
                        continue
                    text = self._entry_to_text(entry)
                    if len(text) < 20:
                        continue
                    text_hash = hashlib.md5(text.strip().lower().encode("utf-8")).hexdigest()
                    if text_hash in seen_hashes:
                        skipped_dupes += 1
                        continue
                    seen_hashes.add(text_hash)
                    metas.append({
                        "channel": _scalarize(entry.get("channel", channel)),
                        "language": _scalarize(entry.get("language", self._extract_lang(jsonl_file.name))),
                        "corpus_mode": _scalarize(entry.get("corpus_mode", "THAI_LOCAL" if entry.get("language") == "th" else "ENGLISH_GLOBAL")),
                        "region_scope": _scalarize(entry.get("region_scope", "global")),
                        "is_scam": bool(entry.get("is_scam", True)),
                        "difficulty_band": _scalarize(entry.get("difficulty_band", "moderate")),
                        "knowledge_type": _scalarize(entry.get("knowledge_type", "conceptual")),
                        "interaction_pattern": _scalarize(entry.get("interaction_pattern", "Identify–Classify")),
                        "age_band_fit": _scalarize(entry.get("age_band_fit", "all")),
                        "stage_band_fit": _scalarize(entry.get("stage_band_fit", "all")),
                        "source_file": jsonl_file.name,
                        "source_dataset": _scalarize(entry.get("source", jsonl_file.stem)),
                    })
                    docs.append(text)
                    ids.append(hashlib.md5(f"{jsonl_file.name}:{line_num}:{text_hash}".encode("utf-8")).hexdigest())
                    file_kept += 1
            logger.info("  selected %s from %s (cap=%s)", file_kept, jsonl_file.name, max_docs if max_docs is not None else "none")

        for start in range(0, len(docs), self.batch_size):
            end = min(start + self.batch_size, len(docs))
            self.collection.add(documents=docs[start:end], metadatas=metas[start:end], ids=ids[start:end])
            if end % 5000 == 0 or end == len(docs):
                logger.info("  indexed %s / %s documents", end, len(docs))

        self._indexed = True
        self._save_meta({"fingerprint": current_fp, "profile": self.profile, "indexed_documents": len(docs), "dedupe_skipped": skipped_dupes})
        logger.info("RAG indexing complete — indexed=%s dedupe_skipped=%s profile=%s", len(docs), skipped_dupes, self.profile)
        return self.collection.count()

    def retrieve(self, query: str, *, channel: Optional[str]=None, language: Optional[str]=None, retrieval_mode: Optional[str]=None, is_scam: Optional[bool]=None, knowledge_type: Optional[str]=None, difficulty_band: Optional[str]=None, age_band_fit: Optional[str]=None, stage_band_fit: Optional[str]=None, n_results: int=4) -> List[Dict[str, Any]]:
        if chromadb is None or self.client is None:
            return self._retrieve_fallback(
                query,
                channel=channel,
                language=language,
                retrieval_mode=retrieval_mode,
                is_scam=is_scam,
                knowledge_type=knowledge_type,
                difficulty_band=difficulty_band,
                age_band_fit=age_band_fit,
                stage_band_fit=stage_band_fit,
                n_results=n_results,
            )
        if self._retrieval_disabled_reason:
            return []
        try:
            self.index_knowledge_base(force=False)
            collection = self.collection
            if collection is None or collection.count() == 0:
                return []
            results = collection.query(query_texts=[query], n_results=max(n_results * 16, 64))
        except Exception as exc:
            self.last_error = {
                "type": type(exc).__name__,
                "message": str(exc)[:1000],
            }
            self._retrieval_disabled_reason = f"{type(exc).__name__}: {str(exc)[:500]}"
            logger.exception(
                "RAG retrieval disabled for this run after local embedding/query failure: %s",
                self._retrieval_disabled_reason,
            )
            return []
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        ids = (results.get("ids") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        out = []
        for raw_rank, (text, meta) in enumerate(zip(docs, metas), start=1):
            meta = meta or {}
            if channel and str(meta.get("channel")) != channel: continue
            if language and str(meta.get("language")) != language: continue
            if retrieval_mode and retrieval_mode != "HYBRID_COMPARE" and str(meta.get("corpus_mode")) != retrieval_mode: continue
            if is_scam is not None and bool(meta.get("is_scam")) != is_scam: continue
            if knowledge_type and not self._matches(meta.get("knowledge_type"), knowledge_type): continue
            if difficulty_band and not self._matches(meta.get("difficulty_band"), difficulty_band): continue
            if age_band_fit and not self._matches(meta.get("age_band_fit"), age_band_fit): continue
            if stage_band_fit and not self._matches(meta.get("stage_band_fit"), stage_band_fit): continue
            result_index = raw_rank - 1
            source_record_id = ids[result_index] if result_index < len(ids) else meta.get("source_record_id")
            distance = distances[result_index] if result_index < len(distances) else None
            out.append(
                {
                    "text": text,
                    **meta,
                    "source_record_id": source_record_id,
                    "retrieval_query": query,
                    "retrieval_rank": raw_rank,
                    "distance": float(distance) if distance is not None else None,
                    "retrieval_score_semantics": "Chroma cosine distance; lower is closer",
                }
            )
            if len(out) >= n_results: break
        return out

    def retrieve_for_profile_v2(self, seed, n_results: int = 3) -> List[Dict[str, Any]]:
        query = f"{seed.role} workplace persona {seed.job_title_hint} {seed.department_hint} {seed.age_group_name} {seed.language_mode}"
        ladders = [
            ("profile_strict", dict(language=seed.language_mode, retrieval_mode=seed.retrieval_mode, age_band_fit=seed.age_group_code, n_results=n_results)),
            ("profile_relaxed", dict(language=seed.language_mode, retrieval_mode=seed.retrieval_mode, n_results=n_results)),
            ("profile_global", dict(language=seed.language_mode, n_results=n_results)),
        ]
        for tier, kwargs in ladders:
            out = self.retrieve(query, **kwargs)
            if out:
                for item in out: item["retrieval_tier"] = tier
                return out
        return []

    def retrieve_for_scenario_v2(self, seed, channel: str, variant: str, n_results: int = 4) -> List[Dict[str, Any]]:
        query = f"{seed.role} {seed.job_title_hint} {channel} {variant} {seed.knowledge_type} {seed.interaction_pattern} {seed.development_focus} {seed.age_group_name}"
        ladders = [
            ("strict", dict(channel=channel, language=seed.language_mode, retrieval_mode=seed.retrieval_mode, is_scam=(variant=='fake'), knowledge_type=seed.knowledge_type, difficulty_band=seed.difficulty_band, age_band_fit=seed.age_group_code, stage_band_fit=seed.stage_id, n_results=n_results)),
            ("drop_age_stage", dict(channel=channel, language=seed.language_mode, retrieval_mode=seed.retrieval_mode, is_scam=(variant=='fake'), knowledge_type=seed.knowledge_type, difficulty_band=seed.difficulty_band, n_results=n_results)),
            ("drop_knowledge_difficulty", dict(channel=channel, language=seed.language_mode, retrieval_mode=seed.retrieval_mode, is_scam=(variant=='fake'), n_results=n_results)),
            ("mixed_mode", dict(channel=channel, language=seed.language_mode, is_scam=(variant=='fake'), n_results=n_results)),
        ]
        for tier, kwargs in ladders:
            out = self.retrieve(query, **kwargs)
            if out:
                for item in out: item["retrieval_tier"] = tier
                return out
        return []

    def retrieve_mixed(self, seed, channel: str, n_results: int = 4) -> List[Dict[str, Any]]:
        fake_examples = self.retrieve_for_scenario_v2(seed, channel, "fake", max(1, n_results // 2))
        real_examples = self.retrieve_for_scenario_v2(seed, channel, "real", max(1, n_results - len(fake_examples)))
        return fake_examples + real_examples

    def get_stats(self) -> Dict[str, Any]:
        if chromadb is None or self.client is None:
            count = self._ensure_fallback_docs(force=False)
            return {
                "available": count > 0,
                "backend": "jsonl_lexical_fallback",
                "reason": "chromadb not installed",
                "profile": self.profile,
                "total_documents": count,
                "selected_files": len(self._selected_files()) if KB_DIR.exists() else 0,
                "kb_dir": str(KB_DIR),
                "kb_dir_exists": KB_DIR.exists(),
            }
        if self._retrieval_disabled_reason:
            return {
                "available": False,
                "reason": "retrieval_disabled_after_runtime_error",
                "profile": self.profile,
                "persist_dir": str(self._persist_dir),
                "indexed": self._indexed,
                "last_error": self.last_error,
                "kb_dir": str(KB_DIR),
                "kb_dir_exists": KB_DIR.exists(),
            }
        try:
            total_documents = self.collection.count()
        except Exception as exc:
            self.last_error = {"type": type(exc).__name__, "message": str(exc)[:1000]}
            total_documents = None
        return {"available": True, "profile": self.profile, "persist_dir": str(self._persist_dir), "indexed": self._indexed, "total_documents": total_documents, "last_error": self.last_error, "kb_dir": str(KB_DIR), "kb_dir_exists": KB_DIR.exists()}

    @staticmethod
    def _extract_lang(filename: str) -> str:
        lowered = filename.lower()
        for lang in SUPPORTED_LANGUAGES:
            if f"_{lang}.jsonl" in lowered:
                return lang
        return "en"

    @staticmethod
    def _matches(meta_value: Any, expected: str) -> bool:
        if meta_value is None: return False
        mv = str(meta_value)
        if mv == "all" or mv == expected: return True
        if "|" in mv: return expected in {p.strip() for p in mv.split("|")}
        return False

    def _ensure_fallback_docs(self, force: bool = False, scam_only: bool = False) -> int:
        """Build a dependency-free JSONL lexical retrieval cache when Chroma is unavailable."""

        if self._fallback_docs is not None and not force:
            return len(self._fallback_docs)
        files = self._selected_files()
        if not files:
            self._fallback_docs = []
            self._indexed = True
            return 0

        docs: List[Dict[str, Any]] = []
        seen_hashes = set()
        for jsonl_file in files:
            file_kept = 0
            max_docs = self._max_docs_for(jsonl_file.name)
            channel = jsonl_file.parent.name
            try:
                handle = jsonl_file.open("r", encoding="utf-8")
            except OSError:
                continue
            with handle as f:
                for line_num, line in enumerate(f):
                    if max_docs is not None and file_kept >= max_docs:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if scam_only and entry.get("is_scam") is False:
                        continue
                    text = self._entry_to_text(entry)
                    if len(text) < 20:
                        continue
                    text_hash = hashlib.md5(text.strip().lower().encode("utf-8")).hexdigest()
                    if text_hash in seen_hashes:
                        continue
                    seen_hashes.add(text_hash)
                    meta = {
                        "channel": _scalarize(entry.get("channel", channel)),
                        "language": _scalarize(entry.get("language", self._extract_lang(jsonl_file.name))),
                        "corpus_mode": _scalarize(entry.get("corpus_mode", "THAI_LOCAL" if entry.get("language") == "th" else "ENGLISH_GLOBAL")),
                        "region_scope": _scalarize(entry.get("region_scope", "global")),
                        "is_scam": bool(entry.get("is_scam", True)),
                        "difficulty_band": _scalarize(entry.get("difficulty_band", entry.get("difficulty_score", "moderate"))),
                        "knowledge_type": _scalarize(entry.get("knowledge_type", "conceptual")),
                        "interaction_pattern": _scalarize(entry.get("interaction_pattern", "Identify-Classify")),
                        "age_band_fit": _scalarize(entry.get("age_band_fit", "all")),
                        "stage_band_fit": _scalarize(entry.get("stage_band_fit", "all")),
                        "source_file": jsonl_file.name,
                        "source_dataset": _scalarize(entry.get("source", jsonl_file.stem)),
                        "retrieval_backend": "jsonl_lexical_fallback",
                    }
                    docs.append({"text": text, "meta": meta, "tokens": self._tokenize(text), "line_num": line_num})
                    file_kept += 1

        self._fallback_docs = docs
        self._indexed = True
        return len(docs)

    def _retrieve_fallback(
        self,
        query: str,
        *,
        channel: Optional[str] = None,
        language: Optional[str] = None,
        retrieval_mode: Optional[str] = None,
        is_scam: Optional[bool] = None,
        knowledge_type: Optional[str] = None,
        difficulty_band: Optional[str] = None,
        age_band_fit: Optional[str] = None,
        stage_band_fit: Optional[str] = None,
        n_results: int = 4,
    ) -> List[Dict[str, Any]]:
        self._ensure_fallback_docs(force=False)
        docs = self._fallback_docs or []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            query_tokens = set(str(query).lower().split())
        scored: List[tuple[float, Dict[str, Any]]] = []
        for doc in docs:
            meta = doc["meta"]
            if channel and str(meta.get("channel")) != channel:
                continue
            if language and str(meta.get("language")) != language:
                continue
            if retrieval_mode and retrieval_mode != "HYBRID_COMPARE" and str(meta.get("corpus_mode")) != retrieval_mode:
                continue
            if is_scam is not None and bool(meta.get("is_scam")) != is_scam:
                continue
            if knowledge_type and not self._matches(meta.get("knowledge_type"), knowledge_type):
                continue
            if difficulty_band and not self._matches(meta.get("difficulty_band"), difficulty_band):
                continue
            if age_band_fit and not self._matches(meta.get("age_band_fit"), age_band_fit):
                continue
            if stage_band_fit and not self._matches(meta.get("stage_band_fit"), stage_band_fit):
                continue
            overlap = len(query_tokens & doc["tokens"])
            if overlap <= 0:
                continue
            score = overlap / max(len(query_tokens), 1)
            if channel and str(meta.get("channel")) == channel:
                score += 0.25
            if is_scam is not None and bool(meta.get("is_scam")) == is_scam:
                score += 0.20
            scored.append((score, doc))
        scored.sort(key=lambda item: (-item[0], str(item[1]["meta"].get("source_file")), item[1]["line_num"]))
        out: List[Dict[str, Any]] = []
        for rank, (score, doc) in enumerate(scored[:n_results], start=1):
            out.append(
                {
                    "text": doc["text"],
                    "retrieval_score": round(score, 4),
                    **doc["meta"],
                    "retrieval_query": query,
                    "retrieval_rank": rank,
                    "retrieval_score_semantics": "project lexical overlap score; higher is closer",
                }
            )
        return out

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        stopwords = {
            "the", "and", "or", "to", "of", "a", "an", "in", "on", "for", "with", "is", "are",
            "be", "this", "that", "it", "as", "by", "from", "at", "you", "your", "we", "our",
        }
        return {token for token in re.findall(r"[A-Za-z0-9_]{3,}", str(text).lower()) if token not in stopwords}
