"""Module 8 – Batch Management: the full journey of each batch."""
from __future__ import annotations

import json

import streamlit as st

from core import batch as batch_mod
from core import reports
from core.db import query_df
from views.common import batch_selector, bucket_order, inr, show_table, status_badge


def render():
    st.title("🗂️ Batch Management")
    all_b = batch_mod.list_batches()
    if not all_b.empty:
        with st.expander(f"All batches ({len(all_b)})", expanded=False):
            show_table(all_b)
    bid = batch_selector("batch_sel")
    if not bid:
        return
    b = batch_mod.get_batch(bid)
    st.markdown(" &nbsp;|&nbsp; ".join([
        status_badge("Processing", b["processing_status"]),
        status_badge("Email", b["email_status"]),
        status_badge("Recheck", b["recheck_status"]),
        status_badge("MIS", b["mis_status"]),
    ]))
    st.caption(f"Calling date {b['calling_date']} · created {b['created_at']} by {b['created_by']}"
               + (f" · Notes: {b['notes']}" if b["notes"] else ""))

    k = reports.cases(bid)
    h = reports.headline(k) if len(k) else {}
    m = st.columns(6)
    m[0].metric("Calls", b["total_calls"])
    m[1].metric("App IDs in report", b["total_app_ids"])
    m[2].metric("Cases (with dues)", b["total_cases"])
    m[3].metric("Total overdue", inr(h.get("Total overdue (₹)", 0)))
    m[4].metric("Total charges", inr(h.get("Total charges (₹)", 0)))
    m[5].metric("Unassigned cases", h.get("Unassigned cases", 0))

    st.download_button("⬇ Download full batch report (Excel)", reports.batch_workbook(bid, bucket_order()),
                       file_name=f"{bid}_processed.xlsx", type="primary")

    t = st.tabs(["Cases", "CM Summary", "Calls", "All App IDs", "Exceptions", "Source files", "Audit trail"])
    with t[0]:
        show_table(reports.cases_display(k) if len(k) else k, height=500)
    with t[1]:
        show_table(reports.cm_summary(k))
        st.markdown("**Case type / DPD bucket**")
        show_table(reports.case_type_pivot(k, bucket_order()))
    with t[2]:
        show_table(reports.calls(bid), height=500)
    with t[3]:
        ids = reports.app_ids(bid)
        st.caption("Every App ID mentioned in the inbound report and what happened to it. Nothing is dropped silently.")
        st.write(ids["match_status"].value_counts().to_dict())
        show_table(ids, height=450)
    with t[4]:
        show_table(reports.exceptions(bid))
    with t[5]:
        src = query_df(
            """SELECT s.id, s.kind, s.original_name, s.as_of_date, s.uploaded_at, s.sheet, s.row_count, s.column_map
               FROM source_files s WHERE s.id IN (?,?,?,?)""",
            (b["inbound_file_id"], b["portfolio_file_id"], b["allocation_file_id"], b["charges_file_id"] or -1),
        )
        show_table(src)
    with t[6]:
        log = query_df("SELECT ts, user, action, detail FROM audit_log WHERE batch_id=? ORDER BY id DESC", (bid,))
        show_table(log)
