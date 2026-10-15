"""Document ingestion page."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src"), str(Path(__file__).resolve().parents[1])]

import streamlit as st  # noqa: E402

from common import init_page, metric_row  # noqa: E402

services = init_page("Ingest HLD document")
settings = services.settings
metric_row(services)

st.divider()

uploaded = st.file_uploader("HLD PDF", type=["pdf"])
col1, col2 = st.columns(2)
with col1:
    version_label = st.text_input("Version label", placeholder="e.g. v2.1 or 2026-09-15")
with col2:
    status = st.selectbox("Source status", ["draft", "approved", "deprecated"])

replace_id = None
docs = services.list_documents()
if docs:
    replace_existing = st.checkbox("Replace an existing document (same slot)")
    if replace_existing:
        options = {f"{d['name']} [{d['version_label'] or '-'}]": d["id"] for d in docs}
        replace_id = options[st.selectbox("Document to replace", list(options.keys()))]

if st.button("Ingest document", type="primary", disabled=uploaded is None):
    if uploaded is None:
        st.warning("Select a PDF first.")
    else:
        upload_dir = settings.data_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{uuid.uuid4().hex[:8]}_{uploaded.name}"
        target.write_bytes(uploaded.getbuffer())
        with st.spinner("Extracting sections, tables and entities..."):
            try:
                result = services.ingest(
                    target,
                    name=uploaded.name,
                    version_label=version_label,
                    status=status,
                    replace_id=replace_id,
                )
            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")
            else:
                if "duplicate_of" in result:
                    st.warning(result["message"] + f" Existing: {result['duplicate_of']}")
                else:
                    st.success(
                        f"Ingested: {result['pages']} pages -> {result['chunks']} chunks, "
                        f"{result['entities']} entities, {result['headings']} headings."
                    )
                    for warning in result.get("warnings", []):
                        st.warning(warning)

st.divider()
st.subheader("Indexed documents")

if not docs:
    st.info("Nothing ingested yet.")
else:
    for doc in services.list_documents():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
            c1.markdown(
                f"**{doc['name']}**  \nversion `{doc['version_label'] or '-'}` · "
                f"status `{doc['status']}` · {doc['pages']} pages · "
                f"{doc['chunks']} chunks · {doc['headings']} headings"
            )
            warnings = (doc.get("metadata") or {}).get("warnings") or []
            for warning in warnings:
                c1.caption(warning)
            c2.caption(f"id: `{doc['id']}`  \n{doc['created_at']}")
            if c3.button("Reindex", key=f"reindex_{doc['id']}"):
                with st.spinner("Rebuilding vectors..."):
                    result = services.reindex(doc["id"])
                st.success(f"{result['chunks']} chunks reindexed")
            if c4.button("Delete", key=f"del_{doc['id']}"):
                services.delete_document(doc["id"])
                st.rerun()
