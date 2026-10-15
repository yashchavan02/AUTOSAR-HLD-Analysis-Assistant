"""Shared helpers for the Streamlit UI."""

from __future__ import annotations

from functools import lru_cache

import streamlit as st

from hld_assistant.config import get_settings
from hld_assistant.services import AssistantServices


@st.cache_resource(show_spinner=False)
def get_services() -> AssistantServices:
    return AssistantServices(get_settings())


@lru_cache(maxsize=1)
def _title() -> str:
    return get_settings().app_title


def init_page(title: str) -> AssistantServices:
    st.set_page_config(page_title=f"{title} | HLD Assistant", layout="wide")
    st.title(title)
    st.caption(_title())
    return get_services()


def doc_selector(
    services: AssistantServices,
    label: str = "HLD document",
    key: str = "doc_selector",
    only_versions: bool = False,
) -> str | None:
    docs = services.list_documents()
    if only_versions:
        docs = [d for d in docs if len(docs) > 1]
    if not docs:
        st.info("No documents ingested yet. Start on the **Ingest** page.")
        return None
    options = {f"{d['name']}  [{d['version_label'] or 'no version'}] ({d['id']})": d["id"]
               for d in docs}
    choice = st.selectbox(label, list(options.keys()), key=key)
    return options[choice]


def multi_doc_selector(services: AssistantServices, key: str = "docs_multi") -> list[str] | None:
    docs = services.list_documents()
    if not docs:
        st.info("No documents ingested yet. Start on the **Ingest** page.")
        return None
    labels = {f"{d['name']} [{d['version_label'] or '-'}]": d["id"] for d in docs}
    selected = st.multiselect(
        "Limit to documents (empty = all)", list(labels.keys()), key=key
    )
    return [labels[s] for s in selected] or None


def metric_row(services: AssistantServices) -> None:
    status = services.status()
    llm = status["llm"]
    cols = st.columns(5)
    cols[0].metric("Documents", status["documents"])
    cols[1].metric("Indexed chunks", status["chunks_indexed"])
    cols[2].metric("Embedder", status["embedder"])
    cols[3].metric("LLM", "ready" if llm.get("available") else "offline")
    cols[4].metric("Project", status["project"])


def render_citations(citations: list) -> None:
    if not citations:
        return
    st.markdown("**Sources**")
    for citation in citations:
        label = citation if isinstance(citation, str) else citation.get("citation", str(citation))
        st.markdown(f"- {label}")


def render_review_form(services: AssistantServices, target: str, target_id: str) -> None:
    with st.expander("Record engineer review"):
        verdict = st.selectbox(
            "Verdict", ["accepted", "corrected", "rejected", "needs discussion"],
            key=f"verdict_{target}_{target_id}",
        )
        comment = st.text_area(
            "Comment", key=f"comment_{target}_{target_id}", height=100
        )
        reviewer = st.text_input(
            "Reviewer", key=f"reviewer_{target}_{target_id}",
            placeholder="name / badge id",
        )
        if st.button("Save review", key=f"save_review_{target}_{target_id}"):
            review_id = services.add_review(target, target_id, verdict, comment, reviewer)
            st.success(f"Review saved: {review_id}")


def severity_counts(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for finding in findings:
        severity = finding.get("severity", "info")
        counts[severity] = counts.get(severity, 0) + 1
    return counts
