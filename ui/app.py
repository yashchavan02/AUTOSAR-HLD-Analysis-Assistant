"""Home page: system status, governance note and workflow overview."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src")]

import streamlit as st  # noqa: E402

from common import init_page, metric_row  # noqa: E402

services = init_page("AUTOSAR HLD Analysis Assistant")

metric_row(services)

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Workflow")
    st.markdown(
        """
1. **Ingest** an approved HLD PDF (text, tables, headings, metadata).
2. Content is **chunked by section** and embedded into the local vector store.
3. **Ask** architecture questions in natural language - answers carry page/section citations.
4. **Inventory** extracted components, interfaces, ports, signals and dependencies.
5. **Checks** flag terminology drift, undefined references and direction conflicts.
6. **Compare** two revisions before a design review.
7. **Export** structured JSON/CSV/Markdown for downstream tooling.
        """
    )

with right:
    st.subheader("System status")
    status = services.status()
    llm = status["llm"]
    if llm.get("available"):
        st.success(
            f"LLM ready: `{llm.get('model')}` via `{llm.get('provider')}` "
            f"at `{llm.get('endpoint')}`"
        )
    else:
        st.warning(
            "LLM offline - Q&A runs in **retrieval mode** (grounded evidence "
            f"excerpts only). Reason: {llm.get('reason', 'n/a')}"
        )
        st.caption(
            "Enable a provider with `HLD_LLM_PROVIDER=groq` (set `GROQ_API_KEY`), "
            "or point `HLD_LLM_BASE_URL` / `HLD_LLM_MODEL` at any OpenAI-compatible "
            "endpoint. See .env.example."
        )
    st.caption(f"Data directory: `{status['data_dir']}`")
    st.caption(f"Embedder: `{status['embedder']}`")
    if status["documents"] and not status["index_complete"]:
        st.warning(
            f"Vector index is out of date ({status['chunks_indexed']} of "
            f"{status['chunks_stored']} chunks). Reindex from the Ingest page "
            "after changing the embedding model."
        )

st.divider()

st.subheader("Documents")
docs = services.list_documents()
if not docs:
    st.info("No documents yet - upload your first HLD on the **Ingest** page.")
else:
    st.dataframe(
        [
            {
                "name": d["name"],
                "version": d["version_label"],
                "status": d["status"],
                "pages": d["pages"],
                "chunks": d["chunks"],
                "entities": "",
                "scanned pages": d["scanned_pages"],
                "ingested": d["created_at"],
                "id": d["id"],
            }
            for d in docs
        ],
        hide_index=True,
    )

st.divider()
st.caption(
    "Governance: AI-generated content must be traceable to approved source material "
    "and reviewed by authorised engineering specialists before use for compliance, "
    "design approval, software release or vehicle validation."
)
