"""Chat models behind one small interface, so the copilot doesn't care which one answers.

Pick one with LLM_PROVIDER in .env (default "ollama"). A Claude implementation is not
written yet; it slots in here as another class plus one line in get_llm().
"""
from typing import Optional, Protocol

import requests

from data.db import get_setting


class LLM(Protocol):
    name: str

    def generate(self, system: str, user: str, json_schema: Optional[dict] = None) -> str:
        """Reply text. With json_schema, the reply is constrained to valid JSON of that shape."""
        ...


class OllamaLLM:
    """A model running locally through Ollama (free, private, needs the Ollama app running)."""

    def __init__(self, model: str = "qwen3:latest", host: str = "http://127.0.0.1:11434", timeout: int = 600):
        self.name = f"ollama:{model}"
        self._model = model
        self._host = host.rstrip("/")
        self._timeout = timeout

    def generate(self, system: str, user: str, json_schema: Optional[dict] = None) -> str:
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,  # skip Qwen3's long hidden reasoning; answers are grounded in passages
            "options": {"temperature": 0.1, "num_ctx": 8192},
        }
        if json_schema:
            body["format"] = json_schema
        try:
            resp = requests.post(f"{self._host}/api/chat", json=body, timeout=self._timeout)
            resp.raise_for_status()
        except requests.ConnectionError as exc:
            raise RuntimeError(f"Can't reach Ollama at {self._host}. Is the Ollama app running?") from exc
        return resp.json()["message"]["content"]


def get_llm() -> LLM:
    provider = (get_setting("LLM_PROVIDER") or "ollama").lower()
    if provider == "ollama":
        return OllamaLLM(model=get_setting("OLLAMA_MODEL") or "qwen3:latest")
    raise RuntimeError(f"Unknown LLM_PROVIDER '{provider}'. Supported: ollama")
