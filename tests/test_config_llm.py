"""LLM provider configuration (Groq and other OpenAI-compatible endpoints)."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import httpx

from hld_assistant import config
from hld_assistant.rag.llm import LLMClient, LLMUnavailable


def _clear_llm_env(monkeypatch):
    for key in (
        "HLD_LLM_PROVIDER",
        "HLD_LLM_BASE_URL",
        "HLD_LLM_MODEL",
        "HLD_LLM_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "HLD_LLM_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)


def test_groq_provider_preset(monkeypatch, tmp_path):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("HLD_ENV_FILE", str(tmp_path / "nope.env"))
    monkeypatch.setenv("HLD_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    config.reset_settings_cache()
    try:
        settings = config.load_settings()
        assert settings.llm_provider == "groq"
        assert settings.llm_base_url == "https://api.groq.com/openai/v1"
        assert settings.llm_model == "openai/gpt-oss-120b"
        assert settings.llm_api_key == "gsk_test_key"
        assert settings.llm_key_env == "GROQ_API_KEY"
        assert settings.llm_enabled is True
    finally:
        config.reset_settings_cache()


def test_explicit_hld_variables_override_provider_preset(monkeypatch, tmp_path):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("HLD_ENV_FILE", str(tmp_path / "nope.env"))
    monkeypatch.setenv("HLD_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
    monkeypatch.setenv("HLD_LLM_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("HLD_LLM_BASE_URL", "https://proxy.example/v1/")
    config.reset_settings_cache()
    try:
        settings = config.load_settings()
        assert settings.llm_model == "llama-3.1-8b-instant"
        assert settings.llm_base_url == "https://proxy.example/v1"
        assert settings.llm_api_key == "gsk_test_key"
    finally:
        config.reset_settings_cache()


def test_default_stays_local_ollama_compatible(monkeypatch, tmp_path):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("HLD_ENV_FILE", str(tmp_path / "nope.env"))
    config.reset_settings_cache()
    try:
        settings = config.load_settings()
        assert settings.llm_provider == "custom"
        assert settings.llm_base_url == "http://localhost:11434/v1"
        assert settings.llm_model == "llama3.2"
    finally:
        config.reset_settings_cache()


def test_env_file_is_loaded_without_overriding_the_shell(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "HLD_LLM_PROVIDER=groq\n"
        "GROQ_API_KEY=from_file\n"
        "OPENAI_API_KEY=\"quoted_key\"\n"
        "NOT_A_LINE_without_equals\n",
        encoding="utf-8",
    )
    before = set(os.environ)
    monkey_added: list[str] = []
    try:
        os.environ["GROQ_API_KEY"] = "from_shell"
        loaded = config.load_env_file(env_file)
        assert loaded == env_file
        assert os.environ["HLD_LLM_PROVIDER"] == "groq"
        assert os.environ["GROQ_API_KEY"] == "from_shell"
        assert os.environ["OPENAI_API_KEY"] == "quoted_key"
        monkey_added = [k for k in set(os.environ) - before if k != "GROQ_API_KEY"]
    finally:
        for key in monkey_added:
            os.environ.pop(key, None)
        os.environ.pop("GROQ_API_KEY", None)


def test_status_explains_missing_groq_key(settings):
    settings = dataclasses.replace(
        settings,
        llm_enabled=True,
        llm_provider="groq",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_api_key="not-needed",
        llm_key_env="GROQ_API_KEY",
        llm_model="openai/gpt-oss-120b",
    )
    status = LLMClient(settings).status()
    assert status["available"] is False
    assert "GROQ_API_KEY" in status["reason"]
    assert status["provider"] == "groq"
    assert status["model"] == "openai/gpt-oss-120b"


def test_generate_posts_openai_compatible_payload(settings, monkeypatch):
    settings = dataclasses.replace(
        settings,
        llm_enabled=True,
        llm_provider="groq",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_api_key="gsk_test_key",
        llm_model="openai/gpt-oss-120b",
    )
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "  Grounded answer [1]  "}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    client = LLMClient(settings)
    answer = client.generate("system prompt", "user prompt")
    assert answer == "Grounded answer [1]"
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer gsk_test_key"
    assert captured["json"]["model"] == "openai/gpt-oss-120b"
    assert captured["json"]["temperature"] == 0.1
    assert captured["json"]["messages"][0]["role"] == "system"


def test_generate_reports_http_errors(settings, monkeypatch):
    settings = dataclasses.replace(
        settings,
        llm_enabled=True,
        llm_provider="groq",
        llm_base_url="https://api.groq.com/openai/v1",
        llm_api_key="bad_key",
        llm_model="openai/gpt-oss-120b",
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid API Key"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    try:
        LLMClient(settings).generate("s", "u")
        raise AssertionError("expected LLMUnavailable")
    except LLMUnavailable as exc:
        assert "401" in str(exc)
        assert "Invalid API Key" in str(exc)


def test_env_example_documents_the_groq_setup():
    example = Path(__file__).resolve().parents[1] / ".env.example"
    text = example.read_text(encoding="utf-8")
    assert "HLD_LLM_PROVIDER=groq" in text
    assert "GROQ_API_KEY=" in text
