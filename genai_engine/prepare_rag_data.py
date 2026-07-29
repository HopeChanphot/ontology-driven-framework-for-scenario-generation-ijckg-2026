from __future__ import annotations

"""
PersonaShield Quest — Generic RAG Data Preparation Pipeline (v5.1)
==================================================================
Repairs and improves the generic v5 ingestion script.

Main fixes
- Fixes Python 3.12 regex error in parse_txt_or_md
- Raises CSV field size limit for large email corpora
- Adds source-specific policies for known datasets to reduce bad channel inference
- Treats awareness/reference PDFs more safely than raw scam-message datasets
- Writes a manifest for auditability

Supported input types
- .csv, .tsv
- .xlsx, .xls
- .txt, .md
- .json, .jsonl
- .pdf (text-based PDFs only)
"""

import argparse
import csv
import hashlib
import html
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

# Raise CSV field limit for large corpora like CEAS/Enron/TREC/Nazario/SpamAssassin
try:
    csv.field_size_limit(min(sys.maxsize, 10**9))
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_DIR = PROJECT_ROOT / "knowledge_base" / "raw_data"
OUTPUT_DIR = PROJECT_ROOT / "output"
MANIFEST_DIR = OUTPUT_DIR / "_manifest"

SUPPORTED_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xls", ".txt", ".md", ".json", ".jsonl", ".pdf"}

SCAM_FILENAME_HINTS = {
    "scam", "fraud", "phish", "smish", "vish", "spam", "malicious", "bogus", "nigerian", "nazario"
}
HAM_FILENAME_HINTS = {
    "ham", "legit", "normal", "nonscam", "non_scam", "safe", "genuine", "real", "enron"
}
SMS_HINTS = {"sms", "smish", "text", "message"}
EMAIL_HINTS = {"email", "mail", "spamassassin", "enron", "nazario", "ling", "ceas", "trec"}
VOICE_HINTS = {"voice", "call", "phone", "vish", "transcript", "ivr", "robocall"}

TEXT_COLS = [
    "text", "message", "messages", "content", "body", "body_text", "email_body",
    "transcript", "dialogue", "utterance", "sentence", "sms", "call_text", "script"
]
SUBJECT_COLS = ["subject", "title", "heading"]
SENDER_COLS = ["sender", "from", "from_address", "email", "caller", "caller_id"]
LABEL_COLS = ["label", "class", "category", "target", "is_scam", "spam", "type"]

THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
URL_RE = re.compile(r"https?://\S+", re.I)
NUMBERED_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] prepare_rag_data_v5_1: %(message)s",
)
logger = logging.getLogger("prepare_rag_data_v5_1")

# Known source policies to avoid bad inference
KNOWN_SOURCE_POLICIES: Dict[str, Dict[str, Any]] = {
    "dataset_kaggle": {"channel": "sms", "language": "en"},
    "smsfraud": {"channel": "sms", "language": "th", "is_scam": True},
    "smsnormal": {"channel": "sms", "language": "th", "is_scam": False},
    "english_scam": {"channel": "voice", "language": "en", "is_scam": True},
    "english_nonscam": {"channel": "voice", "language": "en", "is_scam": False},
    "thfraud": {"channel": "sms", "language": "th", "is_scam": True},
    "thham": {"channel": "sms", "language": "th", "is_scam": False},
    "irs_completecall_transcript": {"channel": "voice", "language": "en", "is_scam": True},
    "spamassasin": {"channel": "email", "language": "en"},
    "spamassassin": {"channel": "email", "language": "en"},
    "ceas_08": {"channel": "email", "language": "en"},
    "enron": {"channel": "email", "language": "en", "is_scam": False},
    "nazario": {"channel": "email", "language": "en", "is_scam": True},
    "nazario_5": {"channel": "email", "language": "en", "is_scam": True},
    "ling": {"channel": "email", "language": "en"},
    "trec_05": {"channel": "email", "language": "en"},
    "trec_06": {"channel": "email", "language": "en"},
    "trec_07": {"channel": "email", "language": "en"},
    "nigerian_fraud": {"channel": "email", "language": "en", "is_scam": True},
    "nigerian_5": {"channel": "email", "language": "en", "is_scam": True},
    # Awareness/reference PDFs: do not treat as direct scam message corpora by default
    "financialfraud": {"channel": "email", "language": "th", "is_scam": False, "knowledge_type": "conceptual", "interaction_pattern": "Recognize–Explain"},
    "ncsa_virtaul_summit_1_presentation_tb-cert": {"channel": "email", "language": "th", "is_scam": False, "knowledge_type": "conceptual", "interaction_pattern": "Recognize–Explain"},
}


@dataclass
class SourceResult:
    source_file: str
    suffix: str
    processed_records: int
    channel_counts: Dict[str, int]
    skipped_reason: Optional[str] = None


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def md5_text(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode("utf-8")).hexdigest()


def thai_ratio(text: str) -> float:
    if not text:
        return 0.0
    thai_chars = len(THAI_RE.findall(text))
    return thai_chars / max(1, len(text))


def get_source_policy(filename: str) -> Dict[str, Any]:
    stem = Path(filename).stem.lower().replace(" ", "_")
    stem = re.sub(r"[^a-z0-9_\-]+", "_", stem)
    return KNOWN_SOURCE_POLICIES.get(stem, {})


def infer_language(text: str, filename: str) -> str:
    policy = get_source_policy(filename)
    if policy.get("language") in {"en", "th"}:
        return policy["language"]
    name = filename.lower()
    if thai_ratio(text) > 0.05 or any(k in name for k in ["thai", "_th", "-th", "tb-cert", "bot", "fraudth"]):
        return "th"
    return "en"


def infer_region_scope(language: str, filename: str) -> str:
    name = filename.lower()
    if language == "th" or any(k in name for k in ["thai", "tb-cert", "bot", "etda"]):
        return "thailand"
    return "global"


def infer_corpus_mode(language: str, filename: str) -> str:
    name = filename.lower()
    if language == "th" or any(k in name for k in ["thai", "tb-cert", "bot", "etda"]):
        return "THAI_LOCAL"
    return "ENGLISH_GLOBAL"


def infer_channel(filename: str, text: str = "", explicit: Optional[str] = None) -> str:
    if explicit in {"sms", "email", "voice"}:
        return explicit
    policy = get_source_policy(filename)
    if policy.get("channel") in {"sms", "email", "voice"}:
        return policy["channel"]

    name = filename.lower()
    if any(k in name for k in VOICE_HINTS):
        return "voice"
    if any(k in name for k in SMS_HINTS):
        return "sms"
    if any(k in name for k in EMAIL_HINTS):
        return "email"

    text_l = text.lower()
    if re.search(r"\b(speaker|caller|agent|target|victim|police headquarters|call center)\b", text_l):
        return "voice"
    if "subject:" in text_l or "from:" in text_l or "<p>" in text_l:
        return "email"
    if len(text) < 500 and ("\n" not in text or text.count("\n") < 4):
        return "sms"
    return "email"


def infer_is_scam(filename: str, text: str = "", label_value: Any = None) -> bool:
    policy = get_source_policy(filename)
    if policy.get("is_scam") is not None:
        return bool(policy["is_scam"])

    if label_value is not None:
        lv = str(label_value).strip().lower()
        if lv in {"1", "spam", "scam", "fraud", "phishing", "smishing", "vishing", "malicious", "fake", "yes", "true"}:
            return True
        if lv in {"0", "ham", "legit", "legitimate", "real", "safe", "normal", "no", "false"}:
            return False

    name = filename.lower()
    if any(h in name for h in SCAM_FILENAME_HINTS):
        return True
    if any(h in name for h in HAM_FILENAME_HINTS):
        return False

    t = text.lower()
    score = 0
    if URL_RE.search(t):
        score += 1
    if any(w in t for w in ["urgent", "verify", "password", "pin", "bank account", "wire transfer", "processing fee", "arrest", "gift card"]):
        score += 2
    if any(w in t for w in ["lottery", "prize", "grant", "refund", "account suspended", "loan approved", "security deposit"]):
        score += 2
    return score >= 2


def infer_difficulty_band(text: str, is_scam: bool) -> str:
    t = text.lower()
    if not is_scam:
        return "easy"
    score = 0
    if URL_RE.search(t):
        score += 1
    if any(w in t for w in ["urgent", "immediately", "final notice", "within 24 hours", "today", "ด่วน", "ทันที"]):
        score += 1
    if any(w in t for w in ["authority", "police", "irs", "bank", "government", "กรม", "ธนาคาร", "ตำรวจ"]):
        score += 1
    if any(w in t for w in ["password", "pin", "otp", "remote access", "apk"]):
        score += 1
    if score <= 1:
        return "easy"
    if score == 2:
        return "moderate"
    return "hard"


def infer_stage_band_fit(difficulty_band: str) -> str:
    if difficulty_band == "easy":
        return "BEGINNER_INTRODUCTORY"
    if difficulty_band == "moderate":
        return "INTERMEDIATE_INTRODUCTORY"
    return "EXPERT_INTRODUCTORY"


def infer_knowledge_type(channel: str, is_scam: bool, text: str, filename: str) -> str:
    policy = get_source_policy(filename)
    if policy.get("knowledge_type"):
        return policy["knowledge_type"]
    t = text.lower()
    if any(w in t for w in ["why", "justify", "reason", "document", "rationale"]):
        return "metacognitive"
    if channel == "voice":
        return "procedural"
    if is_scam and any(w in t for w in ["verify", "confirm", "check", "workflow"]):
        return "procedural"
    if any(w in t for w in ["policy", "pattern", "indicator", "red flag", "แนวทาง", "ข้อสังเกต"]):
        return "conceptual"
    return "conceptual" if is_scam else "factual"


def infer_interaction_pattern(channel: str, knowledge_type: str, is_scam: bool, filename: str) -> str:
    policy = get_source_policy(filename)
    if policy.get("interaction_pattern"):
        return policy["interaction_pattern"]
    if knowledge_type == "metacognitive":
        return "Reflect–Justify"
    if knowledge_type == "procedural":
        return "Inspect–Verify" if channel != "voice" else "Challenge–Verify"
    if knowledge_type == "conceptual":
        return "Identify–Classify"
    return "Recognize–Explain"


def detect_attack_tactics(text: str, is_scam: bool, channel: str) -> List[str]:
    if not is_scam:
        return []
    t = text.lower()
    tactics: List[str] = []
    if channel == "sms":
        tactics.append("smishing")
    elif channel == "email":
        tactics.append("phishing")
    elif channel == "voice":
        tactics.append("vishing")
    if URL_RE.search(t):
        tactics.append("link_based_lure")
    if any(w in t for w in ["bank", "account", "password", "pin", "otp", "verify"]):
        tactics.append("credential_harvesting")
    if any(w in t for w in ["invoice", "payment", "beneficiary", "wire transfer"]):
        tactics.append("invoice_fraud")
    if any(w in t for w in ["remote access", "download", "apk", "tech support"]):
        tactics.append("tech_support_scam")
    if any(w in t for w in ["ceo", "manager", "director", "boss"]):
        tactics.append("business_email_compromise")
    return sorted(set(tactics))


def detect_psych_triggers(text: str, is_scam: bool) -> List[str]:
    if not is_scam:
        return []
    t = text.lower()
    triggers: List[str] = []
    if any(w in t for w in ["urgent", "immediately", "today", "now", "final notice", "ด่วน", "ทันที"]):
        triggers.append("urgency")
    if any(w in t for w in ["arrest", "lawsuit", "suspended", "locked", "disconnect", "ตำรวจ", "ระงับ"]):
        triggers.append("fear")
    if any(w in t for w in ["bank", "government", "irs", "police", "manager", "ธนาคาร", "กรม", "ตำรวจ"]):
        triggers.append("authority")
    if any(w in t for w in ["selected", "everyone", "others have", "already confirmed"]):
        triggers.append("social_proof")
    if any(w in t for w in ["prize", "bonus", "reward", "ฟรี", "รางวัล"]):
        triggers.append("greed")
    return sorted(set(triggers)) or ["urgency"]


def detect_red_flags(text: str, is_scam: bool) -> List[str]:
    if not is_scam:
        return []
    t = text.lower()
    flags: List[str] = []
    if URL_RE.search(t):
        flags.append("Contains link or URL")
    if any(w in t for w in ["verify", "confirm your", "password", "pin", "otp", "ยืนยัน", "รหัสผ่าน"]):
        flags.append("Requests verification or sensitive details")
    if any(w in t for w in ["urgent", "immediately", "now", "today", "final notice", "ด่วน", "ทันที"]):
        flags.append("Uses urgency or deadline pressure")
    if any(w in t for w in ["gift card", "wire transfer", "bank transfer", "processing fee", "ค่าธรรมเนียม"]):
        flags.append("Requests money or unusual payment flow")
    if any(w in t for w in ["police", "irs", "government", "bank", "ตำรวจ", "ธนาคาร", "กรม"]):
        flags.append("Uses authority impersonation")
    return flags or ["Unsolicited suspicious contact"]


def build_correct_action(channel: str, is_scam: bool, language: str) -> str:
    if not is_scam:
        return (
            "Verify through the approved workflow or known contact, then continue with the normal process."
            if language == "en"
            else "ตรวจสอบผ่านกระบวนการที่ได้รับอนุมัติหรือช่องทางติดต่อที่เชื่อถือได้ก่อน แล้วจึงดำเนินการตามขั้นตอนปกติ"
        )
    if channel == "voice":
        return (
            "End the call politely, verify independently through an official channel, and report the incident."
            if language == "en"
            else "วางสายอย่างสุภาพ ตรวจสอบผ่านช่องทางทางการด้วยตนเอง และรายงานเหตุการณ์"
        )
    return (
        "Do not click, reply, or provide details. Verify through an official workflow or known contact and report it."
        if language == "en"
        else "อย่าคลิก อย่าตอบกลับ และอย่าให้ข้อมูล ตรวจสอบผ่านช่องทางทางการหรือผู้ติดต่อที่เชื่อถือได้ และรายงานเหตุการณ์"
    )


def chunk_text(text: str, max_chars: int = 1400) -> List[str]:
    text = clean_text(text)
    if len(text) <= max_chars:
        return [text] if text else []
    pieces = re.split(r"(?<=[.!?\n])\s+", text)
    out: List[str] = []
    cur = ""
    for p in pieces:
        if not p:
            continue
        if len(cur) + len(p) + 1 <= max_chars:
            cur = f"{cur} {p}".strip()
        else:
            if cur:
                out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return out


def normalize_record(
    *,
    source_file: str,
    source_stem: str,
    channel: str,
    language: str,
    is_scam: bool,
    text: str,
    subject: str = "",
    sender: str = "",
    explicit_messages: Optional[List[str]] = None,
    dialogue: Optional[List[Dict[str, Any]]] = None,
    page_num: Optional[int] = None,
) -> Dict[str, Any]:
    text = clean_text(text)
    difficulty_band = infer_difficulty_band(text, is_scam)
    knowledge_type = infer_knowledge_type(channel, is_scam, text, source_file)
    record: Dict[str, Any] = {
        "channel": channel,
        "language": language,
        "corpus_mode": infer_corpus_mode(language, source_file),
        "region_scope": infer_region_scope(language, source_file),
        "is_scam": is_scam,
        "difficulty_band": difficulty_band,
        "difficulty_score": {"easy": 3, "moderate": 5, "hard": 8}[difficulty_band],
        "knowledge_type": knowledge_type,
        "interaction_pattern": infer_interaction_pattern(channel, knowledge_type, is_scam, source_file),
        "age_band_fit": "all",
        "stage_band_fit": infer_stage_band_fit(difficulty_band),
        "attack_tactics": detect_attack_tactics(text, is_scam, channel),
        "psych_triggers": detect_psych_triggers(text, is_scam),
        "red_flags": detect_red_flags(text, is_scam),
        "correct_action": build_correct_action(channel, is_scam, language),
        "source": source_stem,
        "source_file": source_file,
    }
    if page_num is not None:
        record["source_page"] = page_num

    if channel == "sms":
        record["messages"] = explicit_messages or [text]
    elif channel == "email":
        record["from_address"] = sender or ""
        record["subject"] = subject or "(no subject)"
        record["body_text"] = text
    else:
        record["dialogue"] = dialogue or [{"speaker": "caller", "text": text, "emotion": None}]
    return record


def write_grouped_jsonl(records: List[Dict[str, Any]], source_stem: str) -> Dict[str, int]:
    grouped: Dict[Tuple[str, str, bool], List[Dict[str, Any]]] = defaultdict(list)
    for rec in records:
        grouped[(rec["channel"], rec["language"], rec["is_scam"])].append(rec)

    counts: Dict[str, int] = {}
    for (channel, language, is_scam), items in grouped.items():
        subdir = OUTPUT_DIR / channel
        subdir.mkdir(parents=True, exist_ok=True)
        suffix = "scam" if is_scam else "ham"
        safe_stem = re.sub(r"[^A-Za-z0-9_\-]+", "_", source_stem)
        outfile = subdir / f"auto_{safe_stem}_{suffix}_{language}.jsonl"
        with outfile.open("w", encoding="utf-8") as f:
            for entry in items:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        counts[str(outfile.relative_to(OUTPUT_DIR))] = len(items)
    return counts


def parse_csv_or_tsv(filepath: Path) -> List[Dict[str, Any]]:
    sep = "\t" if filepath.suffix.lower() == ".tsv" else ","
    try:
        df = pd.read_csv(filepath, sep=sep, engine="python", encoding_errors="ignore")
    except Exception:
        try:
            df = pd.read_csv(filepath, sep=sep, engine="python", encoding="latin-1")
        except Exception as e:
            logger.warning("Could not read CSV/TSV %s: %s", filepath.name, e)
            return []
    return dataframe_to_records(df, filepath)


def parse_excel(filepath: Path) -> List[Dict[str, Any]]:
    try:
        sheets = pd.read_excel(filepath, sheet_name=None, header=0)
    except Exception:
        try:
            sheets = {"Sheet1": pd.read_excel(filepath, header=None)}
        except Exception as e:
            logger.warning("Could not read Excel %s: %s", filepath.name, e)
            return []

    all_records: List[Dict[str, Any]] = []
    for _, df in sheets.items():
        all_records.extend(dataframe_to_records(df, filepath))
    return all_records


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = []
    for i, c in enumerate(df.columns):
        c = clean_text(c)
        if not c or c.lower().startswith("unnamed:"):
            c = f"col_{i}"
        cols.append(c)
    df = df.copy()
    df.columns = cols
    return df


def choose_column(columns: Iterable[str], candidates: List[str]) -> Optional[str]:
    columns_list = list(columns)
    cols = [c.lower() for c in columns_list]
    for cand in candidates:
        for idx, col in enumerate(cols):
            if cand == col or cand in col:
                return columns_list[idx]
    return None


def dataframe_to_records(df: pd.DataFrame, filepath: Path) -> List[Dict[str, Any]]:
    df = normalize_columns(df)
    records: List[Dict[str, Any]] = []
    seen = set()

    label_col = choose_column(df.columns, LABEL_COLS)
    text_col = choose_column(df.columns, TEXT_COLS)
    subject_col = choose_column(df.columns, SUBJECT_COLS)
    sender_col = choose_column(df.columns, SENDER_COLS)

    if text_col is None and len(df.columns) == 1:
        text_col = df.columns[0]
    elif text_col is None:
        non_empty_cols = [c for c in df.columns[:6]]
        if non_empty_cols:
            text_col = "__combined__"
            df[text_col] = df[non_empty_cols].fillna("").astype(str).agg(" | ".join, axis=1)

    if text_col is None:
        return []

    for _, row in df.iterrows():
        text = clean_text(row[text_col])
        if len(text) < 8 or text.lower() in {"nan", "none"}:
            continue
        dedup_key = md5_text(text)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        subject = clean_text(row[subject_col]) if subject_col else ""
        sender = clean_text(row[sender_col]) if sender_col else ""
        label_val = row[label_col] if label_col else None

        combined = f"{subject} {text}".strip()
        language = infer_language(combined, filepath.name)
        channel = infer_channel(filepath.name, combined)
        is_scam = infer_is_scam(filepath.name, combined, label_val)

        explicit_messages = None
        dialogue = None
        if channel == "sms":
            explicit_messages = [text]
        elif channel == "voice":
            dialogue = [{"speaker": "caller", "text": text, "emotion": None}]

        rec = normalize_record(
            source_file=filepath.name,
            source_stem=filepath.stem,
            channel=channel,
            language=language,
            is_scam=is_scam,
            text=combined,
            subject=subject,
            sender=sender,
            explicit_messages=explicit_messages,
            dialogue=dialogue,
        )
        records.append(rec)
    return records


def parse_txt_or_md(filepath: Path) -> List[Dict[str, Any]]:
    try:
        raw = filepath.read_text(encoding="utf-8")
    except Exception:
        try:
            raw = filepath.read_text(encoding="latin-1")
        except Exception as e:
            logger.warning("Could not read text file %s: %s", filepath.name, e)
            return []

    raw = raw.replace("\r\n", "\n")
    # Python 3.12-safe split: apply MULTILINE via flags instead of inline (?m)
    blocks = re.split(r"\n\s*\n+|^\s*\d+[.)]\s+", raw, flags=re.MULTILINE)
    blocks = [clean_text(b) for b in blocks if clean_text(b)]

    records: List[Dict[str, Any]] = []
    seen = set()

    for block in blocks:
        if len(block) < 12:
            continue
        for chunk in chunk_text(block, max_chars=1400):
            key = md5_text(chunk)
            if key in seen:
                continue
            seen.add(key)
            language = infer_language(chunk, filepath.name)
            channel = infer_channel(filepath.name, chunk)
            is_scam = infer_is_scam(filepath.name, chunk)
            if channel == "sms":
                rec = normalize_record(
                    source_file=filepath.name,
                    source_stem=filepath.stem,
                    channel=channel,
                    language=language,
                    is_scam=is_scam,
                    text=chunk,
                    explicit_messages=[chunk],
                )
            elif channel == "voice":
                rec = normalize_record(
                    source_file=filepath.name,
                    source_stem=filepath.stem,
                    channel=channel,
                    language=language,
                    is_scam=is_scam,
                    text=chunk,
                    dialogue=[{"speaker": "caller", "text": chunk, "emotion": None}],
                )
            else:
                rec = normalize_record(
                    source_file=filepath.name,
                    source_stem=filepath.stem,
                    channel=channel,
                    language=language,
                    is_scam=is_scam,
                    text=chunk,
                    subject=filepath.stem,
                )
            records.append(rec)
    return records


def parse_json_like(filepath: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    def normalize_existing(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if "channel" in obj:
            channel = obj.get("channel") or infer_channel(filepath.name, json.dumps(obj, ensure_ascii=False))
            language = obj.get("language") or infer_language(json.dumps(obj, ensure_ascii=False), filepath.name)
            is_scam = bool(obj.get("is_scam", infer_is_scam(filepath.name, json.dumps(obj, ensure_ascii=False))))
            text = obj.get("body_text") or " ".join(obj.get("messages", []) or []) or json.dumps(obj, ensure_ascii=False)
            rec = normalize_record(
                source_file=filepath.name,
                source_stem=filepath.stem,
                channel=channel,
                language=language,
                is_scam=is_scam,
                text=text,
                subject=obj.get("subject", ""),
                sender=obj.get("from_address", ""),
                explicit_messages=obj.get("messages"),
                dialogue=obj.get("dialogue"),
            )
            for k in ["attack_tactics", "psych_triggers", "red_flags", "correct_action"]:
                if obj.get(k):
                    rec[k] = obj[k]
            return rec
        candidate_text = ""
        for k in ["text", "message", "content", "body", "body_text", "transcript", "prompt"]:
            if k in obj and clean_text(obj[k]):
                candidate_text = clean_text(obj[k])
                break
        if not candidate_text:
            return None
        channel = infer_channel(filepath.name, candidate_text)
        language = infer_language(candidate_text, filepath.name)
        is_scam = infer_is_scam(filepath.name, candidate_text, obj.get("label"))
        return normalize_record(
            source_file=filepath.name,
            source_stem=filepath.stem,
            channel=channel,
            language=language,
            is_scam=is_scam,
            text=candidate_text,
            subject=clean_text(obj.get("subject", "")),
            sender=clean_text(obj.get("from", "")),
        )

    try:
        if filepath.suffix.lower() == ".jsonl":
            with filepath.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    rec = normalize_existing(obj)
                    if rec:
                        records.append(rec)
        else:
            obj = json.loads(filepath.read_text(encoding="utf-8"))
            items = obj if isinstance(obj, list) else [obj]
            for item in items:
                if isinstance(item, dict):
                    rec = normalize_existing(item)
                    if rec:
                        records.append(rec)
    except Exception as e:
        logger.warning("Could not read JSON/JSONL %s: %s", filepath.name, e)
    return records


def parse_pdf(filepath: Path) -> List[Dict[str, Any]]:
    if PyPDF2 is None:
        logger.warning("PyPDF2 not installed; skipping PDF %s", filepath.name)
        return []

    try:
        reader = PyPDF2.PdfReader(str(filepath))
    except Exception as e:
        logger.warning("Could not open PDF %s: %s", filepath.name, e)
        return []

    records: List[Dict[str, Any]] = []
    seen = set()
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = clean_text(page.extract_text() or "")
        except Exception:
            text = ""
        if len(text) < 20:
            continue

        language = infer_language(text, filepath.name)
        channel = infer_channel(filepath.name, text)
        is_scam = infer_is_scam(filepath.name, text)

        # transcript-like PDF
        if channel == "voice" and re.search(r"\b(speaker|caller|agent|victim|target)\b", text.lower()):
            dialogue = []
            for line in re.split(r"(?<=[.!?])\s+|\n", text):
                line = clean_text(line)
                if not line:
                    continue
                dialogue.append({"speaker": "caller", "text": line, "emotion": None})
            rec = normalize_record(
                source_file=filepath.name,
                source_stem=filepath.stem,
                channel="voice",
                language=language,
                is_scam=is_scam,
                text=text,
                dialogue=dialogue[:12],
                page_num=page_num,
            )
            if md5_text(text) not in seen:
                seen.add(md5_text(text))
                records.append(rec)
            continue

        for chunk in chunk_text(text, max_chars=1400):
            key = md5_text(f"{page_num}:{chunk}")
            if key in seen:
                continue
            seen.add(key)
            if channel == "sms":
                rec = normalize_record(
                    source_file=filepath.name,
                    source_stem=filepath.stem,
                    channel=channel,
                    language=language,
                    is_scam=is_scam,
                    text=chunk,
                    explicit_messages=[chunk],
                    page_num=page_num,
                )
            elif channel == "voice":
                rec = normalize_record(
                    source_file=filepath.name,
                    source_stem=filepath.stem,
                    channel=channel,
                    language=language,
                    is_scam=is_scam,
                    text=chunk,
                    dialogue=[{"speaker": "caller", "text": chunk, "emotion": None}],
                    page_num=page_num,
                )
            else:
                rec = normalize_record(
                    source_file=filepath.name,
                    source_stem=filepath.stem,
                    channel=channel,
                    language=language,
                    is_scam=is_scam,
                    text=chunk,
                    subject=f"{filepath.stem} page {page_num}",
                    page_num=page_num,
                )
            records.append(rec)
    return records


def process_file(filepath: Path) -> List[Dict[str, Any]]:
    suffix = filepath.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return []
    if suffix in {".csv", ".tsv"}:
        return parse_csv_or_tsv(filepath)
    if suffix in {".xlsx", ".xls"}:
        return parse_excel(filepath)
    if suffix in {".txt", ".md"}:
        return parse_txt_or_md(filepath)
    if suffix in {".json", ".jsonl"}:
        return parse_json_like(filepath)
    if suffix == ".pdf":
        return parse_pdf(filepath)
    return []


def iter_supported_files(root: Path) -> Iterable[Path]:
    for fp in sorted(root.rglob("*")):
        if fp.is_file() and fp.suffix.lower() in SUPPORTED_SUFFIXES:
            yield fp


def save_manifest(results: List[SourceResult]) -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "input_dir": str(INPUT_DIR),
        "output_dir": str(OUTPUT_DIR),
        "sources": [],
        "totals": {
            "files_seen": len(results),
            "files_processed": sum(1 for r in results if not r.skipped_reason),
            "records_written": sum(r.processed_records for r in results),
            "channel_counts": dict(sum_counters([Counter(r.channel_counts) for r in results])),
        },
    }
    for r in results:
        summary["sources"].append(
            {
                "source_file": r.source_file,
                "suffix": r.suffix,
                "processed_records": r.processed_records,
                "channel_counts": r.channel_counts,
                "skipped_reason": r.skipped_reason,
            }
        )
    out = MANIFEST_DIR / "rag_prepare_manifest_v5_1.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved manifest: %s", out)


def sum_counters(counters: List[Counter]) -> Counter:
    total = Counter()
    for c in counters:
        total.update(c)
    return total


def main() -> None:
    global INPUT_DIR, OUTPUT_DIR, MANIFEST_DIR
    ap = argparse.ArgumentParser(description="Convert many file types into JSONL for PersonaShield Quest RAG.")
    ap.add_argument("--input-dir", default=str(INPUT_DIR))
    ap.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = ap.parse_args()

    INPUT_DIR = Path(args.input_dir)
    OUTPUT_DIR = Path(args.output_dir)
    MANIFEST_DIR = OUTPUT_DIR / "_manifest"

    if not INPUT_DIR.exists():
        raise SystemExit(f"Input directory does not exist: {INPUT_DIR}")

    logger.info("Scanning raw data directory: %s", INPUT_DIR)
    results: List[SourceResult] = []

    for fp in iter_supported_files(INPUT_DIR):
        logger.info("Processing: %s", fp.name)
        try:
            records = process_file(fp)
        except Exception as e:
            logger.exception("Unexpected error while processing %s: %s", fp.name, e)
            results.append(SourceResult(source_file=fp.name, suffix=fp.suffix.lower(), processed_records=0, channel_counts={}, skipped_reason=str(e)))
            continue

        if not records:
            results.append(SourceResult(source_file=fp.name, suffix=fp.suffix.lower(), processed_records=0, channel_counts={}, skipped_reason="no usable records extracted"))
            logger.warning("No usable records extracted from %s", fp.name)
            continue

        counts = write_grouped_jsonl(records, fp.stem)
        channel_counts = dict(Counter(rec["channel"] for rec in records))
        results.append(SourceResult(source_file=fp.name, suffix=fp.suffix.lower(), processed_records=len(records), channel_counts=channel_counts))
        logger.info("Wrote %s records from %s", len(records), fp.name)
        for outfile, n in counts.items():
            logger.info("  -> %s (%s records)", outfile, n)

    save_manifest(results)
    total_written = sum(r.processed_records for r in results)
    logger.info("Done. Files seen=%s, records written=%s", len(results), total_written)


if __name__ == "__main__":
    main()
