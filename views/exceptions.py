"""Module 9 – Exception Management."""
from __future__ import annotations

import streamlit as st

from core import batch as batch_mod
from core import reports
from core.exception_types import EXCEPTION_TYPES
from views.allocation import unassigned_editor
from views.common import show_table


def render():
    st.title("⚠️ Exception Management")
    allb = batch_mod.list_batches()
    c = st.columns(3)
    batch = c[0].selectbox("Batch", ["All"] + allb["batch_id"].tolist())
    status = c[1].selectbox("Status", ["Pending", "Reprocessing", "Resolved", "All"])
    types = c[2].multiselect("Type", list(EXCEPTION_TYPES), format_func=lambda t: EXCEPTION_TYPES[t])

    df = reports.exceptions(None if batch == "All" else batch, None if status == "All" else status)
    if types:
        df = df[df["type"].isin(types)]
    if not df.empty:
        st.write(df["exception"].value_counts().rename("count").to_frame())

    if batch != "All":
        with st.expander("Assign CM to unallocated cases", expanded=True):
            unassigned_editor(batch, "exc_unassigned")

    st.subheader(f"Exceptions ({len(df)})")
    if df.empty:
        st.success("No exceptions for this filter.")
        return
    view = df[["id", "batch_id", "app_id", "call_no", "exception", "detail", "status", "created_at",
               "resolved_by", "resolution_note"]].copy()
    view.insert(0, "Select", False)
    out = st.data_editor(view, hide_index=True, width="stretch", height=420,
                         disabled=[c for c in view.columns if c != "Select"], key="exc_editor")
    sel = out.loc[out["Select"], "id"].tolist()
    a, b, c2 = st.columns([1, 2, 1])
    new_status = a.selectbox("Set status", ["Resolved", "Reprocessing", "Pending"])
    note = b.text_input("Resolution note (required)")
    if c2.button(f"Apply to {len(sel)} selected", disabled=not sel or not note.strip(), type="primary"):
        batch_mod.resolve_exceptions([int(i) for i in sel], new_status, note.strip())
        st.success("Updated.")
        st.rerun()
