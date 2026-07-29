"""
PersonaShield Quest — Unified LLM Client (v4.2 telemetry)
=========================================================
Adds structured per-call telemetry for debugging and evaluation.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_OPENAI_COMPLETION_TOKEN_MODELS = ("o1", "o3", "gpt-5", "gpt-4.1")


class LLMClient:
    def __init__(self) -> None:
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        self._model_overrides: Dict[str, str] = {
            "openai": os.getenv("OPENAI_MODEL", ""),
            "ollama": os.getenv("OLLAMA_MODEL", ""),
            "gemini": os.getenv("GEMINI_MODEL", ""),
            "groq": os.getenv("GROQ_MODEL", ""),
        }
        self.last_call_info: Dict[str, Any] = {}

    def generate(
        self,
        provider: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 120,
        num_ctx: int = 4096,
    ) -> Optional[Dict[str, Any]]:
        override = self._model_overrides.get(provider, "")
        if override:
            model_name = override
            logger.debug("Model override applied: %s → %s", provider, model_name)

        started = time.perf_counter()
        info: Dict[str, Any] = {
            "provider": provider,
            "model_name": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
            "num_ctx": num_ctx,
            "system_chars": len(system_prompt or ""),
            "user_chars": len(user_prompt or ""),
            "prompt_chars": len((system_prompt or "") + (user_prompt or "")),
            "http_status": None,
            "success": False,
            "parse_success": False,
            "error_type": None,
            "error_message": None,
            "raw_text_chars": 0,
            "attempt_started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        raw_text: Optional[str] = None
        try:
            if provider == "openai":
                raw_text, status = self._call_openai(model_name, system_prompt, user_prompt, temperature, max_tokens, timeout)
            elif provider == "ollama":
                raw_text, status = self._call_ollama(model_name, system_prompt, user_prompt, temperature, max_tokens, timeout, num_ctx)
            elif provider == "gemini":
                raw_text, status = self._call_gemini(model_name, system_prompt, user_prompt, temperature, max_tokens, timeout)
            elif provider == "groq":
                raw_text, status = self._call_groq(model_name, system_prompt, user_prompt, temperature, max_tokens, timeout)
            else:
                info["error_type"] = "unknown_provider"
                info["error_message"] = f"Unknown provider: {provider!r}"
                self._finalize_info(info, started)
                logger.error(info["error_message"])
                return None
            info["http_status"] = status
            info["raw_text_chars"] = len(raw_text or "")
        except requests.Timeout:
            info["error_type"] = "timeout"
            info["error_message"] = f"Timeout after {timeout}s"
            self._finalize_info(info, started)
            logger.error("Timeout after %ss — %s/%s", timeout, provider, model_name)
            return None
        except requests.HTTPError as e:
            info["error_type"] = "http_error"
            info["http_status"] = getattr(e.response, "status_code", None)
            response_text = getattr(e.response, "text", "") or ""
            info["error_message"] = f"{e} | body={response_text[:500]}"
            self._finalize_info(info, started)
            logger.error("HTTP error %s — %s/%s: %s", info["http_status"], provider, model_name, response_text[:200])
            return None
        except Exception as e:
            info["error_type"] = type(e).__name__
            info["error_message"] = str(e)
            self._finalize_info(info, started)
            logger.error("LLM call failed for %s/%s: %s", provider, model_name, e)
            return None

        parsed = self._extract_json(raw_text or "")
        info["parse_success"] = parsed is not None
        if parsed is None:
            info["error_type"] = "parse_error"
            info["error_message"] = "Failed to parse extracted JSON"
            info["raw_text_preview"] = (raw_text or "")[:500]
            info["raw_text_tail"] = (raw_text or "")[-500:]
            self._finalize_info(info, started)
            logger.error("Failed to parse extracted JSON")
            return None

        info["success"] = True
        self._finalize_info(info, started)
        return parsed

    def _finalize_info(self, info: Dict[str, Any], started: float) -> None:
        info["duration_seconds"] = round(time.perf_counter() - started, 4)
        info["attempt_finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.last_call_info = info

    def _call_openai(self, model: str, system: str, user: str, temperature: float, max_tokens: int, timeout: int) -> tuple[Optional[str], Optional[int]]:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment")
        url = f"{self.openai_base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
        use_new_param = any(model.startswith(p) for p in _OPENAI_COMPLETION_TOKEN_MODELS)
        tokens_key = "max_completion_tokens" if use_new_param else "max_tokens"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            tokens_key: max_tokens,
            "response_format": {"type": "json_object"},
        }
        last_status = None
        for attempt in range(1, 4):
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            last_status = resp.status_code
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = int(resp.headers.get("Retry-After", 10 * attempt)) if resp.status_code == 429 else 5 * attempt
                logger.warning("OpenAI %s — waiting %ss before retry %s/3 …", resp.status_code, retry_after, attempt)
                time.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"], resp.status_code
        raise requests.HTTPError(f"OpenAI retries exhausted", response=resp)

    def _call_ollama(self, model: str, system: str, user: str, temperature: float, max_tokens: int, timeout: int, num_ctx: int = 4096) -> tuple[Optional[str], Optional[int]]:
        url = f"{self.ollama_base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": num_ctx},
        }
        # qwen3 in this local Ollama build returns an empty `content` field in
        # JSON-format mode and places its budget into the `thinking` field.
        # Normal chat mode returns parseable JSON content after concise-thinking
        # instructions, so avoid Ollama JSON mode for qwen3.
        if not model.lower().startswith("qwen3"):
            payload["format"] = "json"
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {})
        return message.get("content", ""), resp.status_code

    def _call_gemini(self, model: str, system: str, user: str, temperature: float, max_tokens: int, timeout: int) -> tuple[Optional[str], Optional[int]]:
        if not self.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set in environment")
        url = f"{self.gemini_base_url}/models/{model}:generateContent?key={self.gemini_api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"},
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = "".join(part.get("text", "") for part in parts)
        return text, resp.status_code

    def _call_groq(self, model: str, system: str, user: str, temperature: float, max_tokens: int, timeout: int) -> tuple[Optional[str], Optional[int]]:
        if not self.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not set in environment")
        url = f"{self.groq_base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            resp.raise_for_status()
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"], resp.status_code

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text or not text.strip():
            return None
        cleaned = text.strip()
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        first_brace = cleaned.find("{")
        if first_brace >= 0:
            try:
                parsed, _ = json.JSONDecoder().raw_decode(cleaned[first_brace:])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            balanced = LLMClient._extract_balanced_json_object(cleaned[first_brace:])
            if balanced:
                try:
                    parsed = json.loads(balanced)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("_extract_json: failed to parse output — first 200 chars: %r", text[:200])
        return None

    @staticmethod
    def _extract_balanced_json_object(text: str) -> Optional[str]:
        """Return the first balanced JSON object substring, respecting quoted strings."""

        start: Optional[int] = None
        depth = 0
        in_string = False
        escaped = False
        for index, char in enumerate(text):
            if start is None:
                if char == "{":
                    start = index
                    depth = 1
                continue
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return None

    def check_openai_health(self) -> bool:
        key = self.openai_api_key
        return bool(key and key.startswith("sk-") and len(key) > 20)

    def check_ollama_health(self) -> bool:
        try:
            resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def list_ollama_models(self) -> list:
        try:
            resp = requests.get(f"{self.ollama_base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pass
        return []

    def check_model_available(self, provider: str, model_name: str) -> bool:
        if provider == "ollama":
            return model_name in self.list_ollama_models()
        if provider == "openai":
            return self.check_openai_health()
        if provider == "gemini":
            return bool(self.gemini_api_key)
        if provider == "groq":
            return bool(self.groq_api_key)
        return False
