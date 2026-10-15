"""Smoke tests: every Streamlit page must render without raising."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.ui

STREAMLIT_AVAILABLE = True
try:
    from streamlit.testing.v1 import AppTest
except Exception:  # pragma: no cover - optional test dependency
    STREAMLIT_AVAILABLE = False


@pytest.mark.skipif(not STREAMLIT_AVAILABLE, reason="streamlit not installed")
@pytest.mark.parametrize(
    "script",
    ["ui/app.py", "ui/pages/2_Ask.py"],
)
def test_pages_render_without_exceptions(script: str, settings, monkeypatch):
    monkeypatch.setenv("HLD_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("HLD_EMBEDDER", "hashing")
    monkeypatch.setenv("HLD_LLM_ENABLED", "0")
    from hld_assistant.config import reset_settings_cache

    reset_settings_cache()
    try:
        script_path = Path(__file__).resolve().parents[1] / script
        at = AppTest.from_file(script_path, default_timeout=120)
        at.run()
        assert not at.exception, f"{script} raised: {at.exception}"
    finally:
        reset_settings_cache()
