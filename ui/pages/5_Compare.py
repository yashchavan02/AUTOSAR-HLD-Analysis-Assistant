"""Revision comparison page."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src"), str(Path(__file__).resolve().parents[1])]

import streamlit as st  # noqa: E402

from common import init_page, metric_row  # noqa: E402

services = init_page("Revision comparison")
metric_row(services)
st.divider()

docs = services.list_documents()
if len(docs) < 2:
    st.info("Compare needs at least two ingested revisions.")
    st.stop()

options = {f"{d['name']} [{d['version_label'] or '-'}] ({d['id']})": d["id"] for d in docs}
labels = list(options.keys())
col1, col2 = st.columns(2)
with col1:
    a = st.selectbox("Revision A (baseline)", labels, index=0)
with col2:
    b = st.selectbox("Revision B (candidate)", labels, index=min(1, len(labels) - 1))

if a == b:
    st.warning("Select two different revisions.")
    st.stop()

if st.button("Compare", type="primary"):
    with st.spinner("Comparing entities, sections and text..."):
        report = services.compare(options[a], options[b])
    st.session_state["comparison"] = report

report = st.session_state.get("comparison")
if not report:
    st.stop()

summary = report["summary"]
cols = st.columns(6)
cols[0].metric("Entities +", summary["entities_added"])
cols[1].metric("Entities -", summary["entities_removed"])
cols[2].metric("Entities ~", summary["entities_modified"])
cols[3].metric("Sections +", summary["sections_added"])
cols[4].metric("Sections -", summary["sections_removed"])
cols[5].metric("Sections ~", summary["sections_changed"])

entities = report["entities"]
sections = report["sections"]

tab1, tab2, tab3, tab4 = st.tabs(
    ["Entities", "Sections", "Changed text", "Raw diff"]
)

with tab1:
    for label, key in [("Added", "added"), ("Removed", "removed"), ("Modified", "modified")]:
        items = entities.get(key) or []
        st.markdown(f"**{label} ({len(items)})**")
        for item in items:
            if key == "modified":
                st.markdown(
                    f"- {item['name']}: {item['from_kind']} -> {item['to_kind']} "
                    f"(p.{item['page_a']} -> p.{item['page_b']})"
                )
            else:
                st.markdown(f"- {item.get('kind')}: {item.get('name')} (p.{item.get('page')})")
        if not items:
            st.caption("none")

with tab2:
    for label, key in [("Added", "added"), ("Removed", "removed")]:
        items = sections.get(key) or []
        st.markdown(f"**{label} sections ({len(items)})**")
        for item in items:
            st.markdown(f"- {item}")
        if not items:
            st.caption("none")

with tab3:
    changed = report["sections_changed"]
    if not changed:
        st.caption("No shared section text changed.")
    for item in changed:
        st.markdown(
            f"**{item['section']}** - similarity {item['similarity']} "
            f"(+{item['lines_added']}/-{item['lines_removed']})"
        )

with tab4:
    for item in report["sections_changed"][:10]:
        st.markdown(f"**{item['section']}**")
        st.code("\n".join(item["diff"][:40]), language="diff")

if st.button("Export comparison"):
    paths = services.export_comparison(report)
    st.success("Written: " + ", ".join(str(p.name) for p in paths))
