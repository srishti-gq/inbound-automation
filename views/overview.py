"""Dashboard overview."""
from __future__ import annotations

import streamlit as st

from core import batch as batch_mod
from core import sources
from core.db import query_df
from core.sources import SOURCE_KINDS
from views.common import inr, show_table


def render():
    st.title("🏠 Inbound Calling & Recovery Dashboard")
    tot = query_df(
        """SELECT COUNT(*) AS cases,
                  COALESCE(SUM(orig_overdue),0) AS overdue,
                  COALESCE(SUM(orig_charges),0) AS charges,
                  SUM(CASE WHEN assigned_cm IS NOT NULL THEN 1 ELSE 0 END) AS allocated
           FROM cases"""
    ).iloc[0]
    r1 = st.columns(4)
    r1[0].metric("Total Inbound Cases", int(tot["cases"]))
    r1[1].metric("Total Overdue", inr(tot["overdue"]))
    r1[2].metric("Total Pending Charges", inr(tot["charges"]))
    r1[3].metric("Cases Allocated", int(tot["allocated"] or 0))
    r2 = st.columns(4)
    for col, lbl in zip(r2, ["No Payment", "Partially Paid", "Fully Paid", "Pending Follow-ups"]):
        col.metric(lbl, "—", help="Available after Outstanding Recheck is built (Phase 3)")

    st.subheader("Recent batches")
    b = batch_mod.list_batches()
    show_table(b.head(8) if not b.empty else b)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Open exceptions")
        ex = query_df("""SELECT batch_id, type, COUNT(*) AS n FROM exceptions WHERE status!='Resolved'
                         GROUP BY batch_id, type ORDER BY batch_id DESC""")
        show_table(ex)
    with c2:
        st.subheader("Source files in use")
        rows = []
        for kind in ("portfolio", "allocation", "charges_allocation"):
            s = sources.latest_source(kind)
            rows.append({"File": SOURCE_KINDS[kind], "Name": s["original_name"] if s else "— not uploaded —",
                         "Data date": s["as_of_date"] if s else None, "Uploaded": s["uploaded_at"] if s else None})
        import pandas as pd
        show_table(pd.DataFrame(rows))
