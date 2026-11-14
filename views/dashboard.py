"""Dashboard – a short summary of where things stand."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import batch as batch_mod
from core import sources
from core.db import query_df
from core.sources import SOURCE_KINDS
from views.common import PAGES, inr, page_header, show_table


def render():
    head, btn = st.columns([4, 1], vertical_alignment="center")
    with head:
        page_header("Dashboard", "Inbound calling follow-up summary across all batches")
    with btn:
        if st.button("Upload inbound report", type="primary", icon=":material/upload_file:", width="stretch"):
            st.switch_page(PAGES["new_batch"])

    tot = query_df(
        """SELECT COUNT(*) AS cases, COALESCE(SUM(orig_overdue),0) AS overdue,
                  COALESCE(SUM(orig_charges),0) AS charges,
                  SUM(CASE WHEN assigned_cm IS NULL THEN 1 ELSE 0 END) AS unassigned
           FROM cases"""
    ).iloc[0]
    open_exc = int(query_df("SELECT COUNT(*) AS n FROM exceptions WHERE status!='Resolved'").iloc[0]["n"])

    c = st.columns(4)
    c[0].metric("Inbound cases", f"{int(tot['cases']):,}")
    c[1].metric("Total overdue", inr(tot["overdue"]))
    c[2].metric("Pending charges", inr(tot["charges"]))
    c[3].metric("Needs attention", f"{int(tot['unassigned'] or 0) + open_exc:,}",
                help="Unassigned cases + open exceptions")

    st.write("")
    left, right = st.columns([2, 1], gap="large")
    with left:
        st.subheader("Recent batches")
        b = batch_mod.list_batches()
        if b.empty:
            st.info("No batches yet.")
            st.page_link(PAGES["new_batch"], label="Upload the first inbound report", icon=":material/arrow_forward:")
        else:
            view = b.head(10).rename(columns={
                "batch_id": "Batch ID", "calling_date": "Calling date", "total_cases": "Cases",
                "processing_status": "Status", "email_status": "Email", "recheck_status": "Recheck",
                "open_exceptions": "Open exceptions"})
            show_table(view[["Batch ID", "Calling date", "Cases", "Status", "Open exceptions"]])
            st.page_link(PAGES["batches"], label="Open batches", icon=":material/arrow_forward:")
    with right:
        st.subheader("Source files")
        rows = []
        for kind in ("portfolio", "allocation", "charges_allocation"):
            s = sources.latest_source(kind)
            rows.append({"File": SOURCE_KINDS[kind].replace(" (optional)", ""),
                         "Data date": (s["as_of_date"] if s else "Not uploaded")})
        show_table(pd.DataFrame(rows))
        st.page_link(PAGES["sources"], label="Manage source files", icon=":material/arrow_forward:")
