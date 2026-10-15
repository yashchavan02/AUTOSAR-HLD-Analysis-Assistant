"""Runtime configuration loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# OpenAI-compatible LLM providers. Each preset fills in defaults for base URL,
# API key environment variable and model; explicit HLD_LLM_* variables win.
LLM_PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "model": "openai/gpt-oss-120b",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "key_env": "",
        "model": "llama3.2",
    },
    "custom": {
        "base_url": "http://localhost:11434/v1",
        "key_env": "",
        "model": "llama3.2",
    },
}


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        return default


def load_env_file(path: Path | str | None = None) -> Path | None:
    """Load KEY=VALUE pairs into the process environment.

    Existing environment variables are never overridden, so shell exports beat
    the file. Defaults to ``HLD_ENV_FILE`` or ``./.env``.
    """
    if path is None:
        candidate = _env("HLD_ENV_FILE", "")
        path = Path(candidate) if candidate else Path.cwd() / ".env"
    path = Path(path)
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value
    return path


def resolve_llm(provider: str) -> dict[str, str]:
    """Return base URL, API key and model for a provider preset."""
    preset = LLM_PROVIDERS.get(provider, LLM_PROVIDERS["custom"])
    api_key = _env("HLD_LLM_API_KEY", "")
    if not api_key and preset.get("key_env"):
        api_key = os.environ.get(preset["key_env"], "")
    return {
        "base_url": _env("HLD_LLM_BASE_URL", preset["base_url"]).rstrip("/"),
        "api_key": api_key or "not-needed",
        "model": _env("HLD_LLM_MODEL", preset["model"]),
        "key_env": preset.get("key_env", ""),
    }


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    vector_dir: Path
    export_dir: Path

    chunk_chars: int = 1200
    chunk_overlap: int = 200
    top_k: int = 6

    embedder: str = "auto"  # auto | hashing | fastembed | sentence-transformers
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    hashing_dim: int = 512

    llm_provider: str = "custom"  # groq | openai | ollama | custom
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "not-needed"
    llm_key_env: str = ""
    llm_model: str = "llama3.2"
    llm_timeout: float = 90.0
    llm_enabled: bool = True

    app_title: str = "AUTOSAR HLD Analysis Assistant"
    project: str = "default"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.vector_dir, self.export_dir):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    load_env_file()
    data_dir = Path(_env("HLD_DATA_DIR", "data")).expanduser().resolve()
    provider = _env("HLD_LLM_PROVIDER", "custom").strip().lower()
    if provider not in LLM_PROVIDERS:
        provider = "custom"
    llm = resolve_llm(provider)
    settings = Settings(
        data_dir=data_dir,
        db_path=Path(_env("HLD_DB_PATH", str(data_dir / "hld.sqlite3"))),
        vector_dir=Path(_env("HLD_VECTOR_DIR", str(data_dir / "vectors"))),
        export_dir=Path(_env("HLD_EXPORT_DIR", str(data_dir / "exports"))),
        chunk_chars=_env_int("HLD_CHUNK_CHARS", 1200),
        chunk_overlap=_env_int("HLD_CHUNK_OVERLAP", 200),
        top_k=_env_int("HLD_TOP_K", 6),
        embedder=_env("HLD_EMBEDDER", "auto"),
        embedding_model=_env("HLD_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        fastembed_model=_env("HLD_FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        hashing_dim=_env_int("HLD_HASHING_DIM", 512),
        llm_provider=provider,
        llm_base_url=llm["base_url"],
        llm_api_key=llm["api_key"],
        llm_key_env=llm["key_env"],
        llm_model=llm["model"],
        llm_timeout=_env_float("HLD_LLM_TIMEOUT", 90.0),
        llm_enabled=_env("HLD_LLM_ENABLED", "1").lower() not in {"0", "false", "no"},
        app_title=_env("HLD_APP_TITLE", "AUTOSAR HLD Analysis Assistant"),
        project=_env("HLD_PROJECT", "default"),
    )
    settings.ensure_dirs()
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
