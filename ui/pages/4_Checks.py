"""Potential mismatch and completeness checks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src"), str(Path(__file__).resolve().parents[1])]

import streamlit as st  # noqa: E402

from common import (  # noqa: E402
    doc_selector,
    init_page,
    metric_row,
    render_review_form,
    severity_counts,
)
from hld_assistant.export.exporter import findings_csv  # noqa: E402

services = init_page("Consistency & completeness checks")
metric_row(services)
st.divider()

doc_id = doc_selector(services)
if not doc_id:
    st.stop()

doc = services.get_document(doc_id)
st.caption(f"{doc['name']} · version {doc['version_label'] or '-'} · {doc['pages']} pages")

if st.button("Run checks", type="primary"):
    with st.spinner("Scanning entities, sections and dependencies..."):
        try:
            findings = services.checks(doc_id)
        except FileNotFoundError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:
            st.error(f"Checks failed: {exc}")
            st.stop()
    st.success(f"{len(findings)} finding(s)")

findings = services.get_findings(doc_id)
if not findings:
    st.info("No findings stored yet - run the checks.")
    st.stop()

counts = severity_counts(findings)
cols = st.columns(3)
cols[0].metric("Errors", counts.get("error", 0))
cols[1].metric("Warnings", counts.get("warning", 0))
cols[2].metric("Info", counts.get("info", 0))

severity_filter = st.multiselect(
    "Severity", ["error", "warning", "info"], default=["error", "warning"]
)
filtered = [f for f in findings if f["severity"] in severity_filter]

for finding in filtered:
    colour = {"error": "red", "warning": "orange", "info": "blue"}.get(finding["severity"], "gray")
    with st.container(border=True):
        st.markdown(
            f":{colour}[{finding['severity'].upper()}] **{finding['rule']}** - "
            f"{finding['message']}"
        )
        for evidence in finding.get("evidence", []):
            st.caption(
                f"p.{evidence.get('page')} {evidence.get('section', '')} - "
                f"{evidence.get('quote', '')[:220]}"
            )
        if finding.get("suggestion"):
            st.caption(f"suggestion: {finding['suggestion']}")
        render_review_form(services, target="finding", target_id=finding["id"])

st.download_button(
    "Download findings CSV",
    findings_csv(findings).encode("utf-8"),
    file_name="findings.csv",
    mime="text/csv",
)
