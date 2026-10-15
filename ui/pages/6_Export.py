"""Structured export page."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src"), str(Path(__file__).resolve().parents[1])]

import streamlit as st  # noqa: E402

from common import doc_selector, init_page, metric_row  # noqa: E402

services = init_page("Export structured findings")
metric_row(services)
st.divider()

doc_id = doc_selector(services)
if not doc_id:
    st.stop()

doc = services.get_document(doc_id)
st.caption(
    f"{doc['name']} · version {doc['version_label'] or '-'} · status {doc['status']}"
)

st.markdown(
    "Exports include the component/interface inventory, extracted entities, "
    "consistency findings and the Q&A history as **CSV**, **JSON** and **Markdown**."
)

if st.button("Generate export package", type="primary"):
    with st.spinner("Running checks and writing files..."):
        try:
            paths = services.export_document(doc_id)
        except Exception as exc:
            st.error(f"Export failed: {exc}")
            st.stop()
    st.session_state["export_paths"] = [str(p) for p in paths]
    st.success(f"{len(paths)} file(s) written")

paths = st.session_state.get("export_paths", [])
export_dir = services.settings.export_dir
if not paths:
    existing = sorted(export_dir.glob("*")) if export_dir.exists() else []
    paths = [str(p) for p in existing]

if not paths:
    st.info("No exports yet.")
    st.stop()

st.subheader("Available files")
for raw in paths:
    path = Path(raw)
    if not path.is_file():
        continue
    col1, col2 = st.columns([4, 1])
    col1.markdown(f"`{path.name}`")
    col1.caption(f"{path.stat().st_size:,} bytes")
    data = path.read_bytes()
    col2.download_button(
        "Download",
        data,
        file_name=path.name,
        key=f"dl_{path.name}",
        mime="text/plain",
    )
