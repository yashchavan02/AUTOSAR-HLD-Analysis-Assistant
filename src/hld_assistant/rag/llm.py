"""OpenAI-compatible chat client (Groq, OpenAI, Ollama or any private endpoint)."""

from __future__ import annotations

import logging

import httpx

from hld_assistant.config import Settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    """Raised when the configured LLM endpoint cannot be reached."""


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.llm_enabled

    def status(self) -> dict:
        base = {
            "provider": self.settings.llm_provider,
            "endpoint": self.settings.llm_base_url,
            "model": self.settings.llm_model,
        }
        if not self.settings.llm_enabled:
            return {**base, "available": False, "reason": "LLM disabled by configuration"}
        key_env = self.settings.llm_key_env
        if key_env and self.settings.llm_api_key == "not-needed":
            return {
                **base,
                "available": False,
                "reason": f"No API key: set {key_env} (or HLD_LLM_API_KEY) in the environment or .env",
            }
        try:
            response = httpx.get(
                f"{self.settings.llm_base_url}/models",
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                timeout=8.0,
            )
            response.raise_for_status()
            models = [m.get("id") for m in response.json().get("data", [])]
            return {**base, "available": True, "models": models[:20]}
        except Exception as exc:
            return {**base, "available": False, "reason": f"{type(exc).__name__}: {exc}"}

    def generate(self, system: str, user: str, max_tokens: int = 900) -> str:
        if not self.settings.llm_enabled:
            raise LLMUnavailable("LLM disabled by configuration")
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            response = httpx.post(
                f"{self.settings.llm_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.settings.llm_timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise LLMUnavailable(
                f"HTTP {exc.response.status_code} from {self.settings.llm_provider} "
                f"({self.settings.llm_base_url}): {detail}"
            ) from exc
        except Exception as exc:
            raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailable(f"Unexpected LLM response shape: {exc}") from exc
