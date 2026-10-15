"""Natural language search and cited Q&A."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src"), str(Path(__file__).resolve().parents[1])]

import streamlit as st  # noqa: E402

from common import (  # noqa: E402
    init_page,
    metric_row,
    multi_doc_selector,
    render_citations,
    render_review_form,
)

services = init_page("Ask the HLD")
metric_row(services)
st.divider()

doc_ids = multi_doc_selector(services)
question = st.text_area(
    "Question",
    placeholder=(
        "e.g. Which components provide the main signal, and which "
        "interfaces are involved?"
    ),
    height=100,
)
k = st.slider("Passages to retrieve", 3, 15, services.settings.top_k)

if st.button("Ask", type="primary", disabled=not question.strip()):
    with st.spinner("Retrieving and grounding..."):
        result = services.ask(question.strip(), doc_ids=doc_ids, k=k)

    mode = result["mode"]
    badge = {
        "generate": "generated with citations",
        "retrieval": "grounded evidence (LLM offline)",
        "empty": "no match",
    }.get(mode, mode)
    st.markdown(f"**Mode:** {badge} · **Grounded:** {'yes' if result['grounded'] else 'no'}")
    if result.get("query_id"):
        st.caption(f"query id: {result['query_id']}")

    st.markdown(result["answer"])
    render_citations(result["citations"])

    if result["passages"]:
        with st.expander(f"Retrieved evidence ({len(result['passages'])})"):
            for index, passage in enumerate(result["passages"], start=1):
                st.markdown(
                    f"**[{index}] {passage['citation']}** · "
                    f"score {passage['score']} (vector {passage['vector_score']}, "
                    f"lexical {passage['lexical_score']})"
                )
                st.write(passage["text"][:1200])
                st.divider()

    render_review_form(services, target="answer", target_id=result.get("query_id", ""))

st.divider()
st.subheader("Recent queries")
queries = services.list_queries(25)
if not queries:
    st.caption("No questions asked yet.")
else:
    for query in queries:
        with st.container(border=True):
            st.markdown(f"**Q:** {query['question']}")
            st.caption(
                f"{query['created_at']} · mode `{query['mode']}` · "
                f"grounded {query['grounded']}"
            )
            st.markdown(query["answer"][:1500])
            render_citations([c.get("citation", c) for c in query["citations"]])

st.divider()
st.subheader("Reviews")
for review in services.list_reviews(20):
    st.markdown(
        f"- `{review['verdict']}` on {review['target']} by "
        f"{review['reviewer'] or 'n/a'} — {review['comment'][:120]}"
    )
