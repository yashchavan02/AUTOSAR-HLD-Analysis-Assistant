"""Extracted architecture entity inventory."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "src"), str(Path(__file__).resolve().parents[1])]

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common import doc_selector, init_page, metric_row  # noqa: E402
from hld_assistant.export.exporter import inventory_csv  # noqa: E402

services = init_page("Component & interface inventory")
metric_row(services)
st.divider()

doc_id = doc_selector(services)
if not doc_id:
    st.stop()

inventory = services.inventory(doc_id)
if not inventory:
    st.info("No entities extracted for this document.")
    st.stop()

total = sum(len(v) for v in inventory.values())
st.caption(f"{total} distinct entities across {len(inventory)} kinds")

kind = st.selectbox("Entity kind", sorted(inventory.keys()))
rows = inventory[kind]
df = pd.DataFrame(
    [
        {
            "name": r["name"],
            "page": r["page"],
            "section": r["section_path"],
            "occurrences": r.get("occurrences", 1),
            "confidence": r.get("confidence"),
            "context": (r.get("context") or "")[:160],
        }
        for r in rows
    ]
)
st.dataframe(df, hide_index=True)

st.download_button(
    f"Download {kind} CSV",
    df.to_csv(index=False).encode("utf-8"),
    file_name=f"inventory_{kind.lower()}.csv",
    mime="text/csv",
)
st.download_button(
    "Download full inventory CSV",
    inventory_csv(inventory).encode("utf-8"),
    file_name="inventory_full.csv",
    mime="text/csv",
)

with st.expander("All kinds"):
    summary = pd.DataFrame(
        [{"kind": k, "entities": len(v)} for k, v in sorted(inventory.items())]
    )
    st.dataframe(summary, hide_index=True)
