"""Swappable model layer: any OpenAI-compatible API (Gemini, Groq, OpenRouter, Ollama, OpenAI, a company gateway),
plus 'replay' (answers read from files) for reproducible test runs."""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
import requests

PRESETS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash", "GEMINI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", "qwen2.5:14b", ""),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "custom": ("", "", "LLM_API_KEY"),
}


class PendingResponse(Exception):
    pass


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("no JSON in model output")
    return json.loads(text[s:e + 1])


class LLM:
    def __init__(self, provider="gemini", model=None, api_key=None, base_url=None, replay_dir="replay",
                 temperature=0.2, min_interval=0.0):
        self.provider, self.temperature, self.min_interval, self._last = provider, temperature, min_interval, 0.0
        if provider == "replay":
            self.dir = Path(replay_dir); self.dir.mkdir(parents=True, exist_ok=True); self.model = "replay"
            return
        base, dmodel, key_env = PRESETS[provider]
        self.base = (base_url or os.getenv("LLM_BASE_URL") or base).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL") or dmodel
        self.key = api_key or (os.getenv(key_env, "") if key_env else "")
        if key_env and not self.key:
            raise ValueError(f"Set {key_env} (or pass an API key) to use provider '{provider}'.")

    def chat(self, messages: list[dict], name: str = "call") -> tuple[dict, str]:
        if self.provider == "replay":
            (self.dir / f"{name}.prompt.json").write_text(json.dumps(messages, indent=1, ensure_ascii=False), encoding="utf-8")
            f = self.dir / f"{name}.response.json"
            if not f.exists():
                raise PendingResponse(name)
            raw = f.read_text(encoding="utf-8")
            return extract_json(raw), raw
        err = None
        for attempt in range(4):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = requests.post(f"{self.base}/chat/completions",
                                  headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
                                  json={"model": self.model, "temperature": self.temperature,
                                        "response_format": {"type": "json_object"}, "messages": messages},
                                  timeout=120)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                #r.raise_for_status()
                if r.status_code >= 400: raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
                raw = r.json()["choices"][0]["message"]["content"]
                return extract_json(raw), raw
            except Exception as e:
                err = e
                time.sleep(min(30, 3 * 2 ** attempt))
        raise RuntimeError(f"model call failed: {err}")
