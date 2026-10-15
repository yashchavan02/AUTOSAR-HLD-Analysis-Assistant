from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import pytest  # noqa: E402

from hld_assistant.config import Settings  # noqa: E402


@pytest.fixture(scope="session")
def sample_pdfs(tmp_path_factory) -> dict[str, Path]:
    from sample_data.generate_sample import build_document

    out = tmp_path_factory.mktemp("pdfs")
    path_a = out / "hld_revision_a.pdf"
    path_b = out / "hld_revision_b.pdf"
    build_document(path_a, "A")
    build_document(path_b, "B")
    return {"a": path_a, "b": path_b}


@pytest.fixture()
def settings(tmp_path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        db_path=data_dir / "hld.sqlite3",
        vector_dir=data_dir / "vectors",
        export_dir=data_dir / "exports",
        embedder="hashing",
        hashing_dim=256,
        llm_enabled=False,
        top_k=5,
    )


@pytest.fixture()
def services(settings):
    from hld_assistant.services import AssistantServices

    return AssistantServices(settings)
