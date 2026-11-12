"""Module 3 – CM-wise case allocation (review before emails)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import batch as batch_mod
from core import reports, sources
from views.common import batch_selector, bucket_order, inr, show_table


def unassigned_editor(bid: str, key: str):
    k = reports.cases(bid)
    un = k[k["assigned_cm"].isna()]
    if un.empty:
        st.success("All cases in this batch have a CM assigned.")
        return
    b = batch_mod.get_batch(bid)
    cms = sources.distinct_cms(b["allocation_file_id"])
    st.warning(f"{len(un)} case(s) have no CM (not in allocation file, or marked Hold). Assign them below.")
    edit = pd.DataFrame({
        "Application ID": un["app_id"], "Student": un["student_name"], "Overdue": un["orig_overdue"],
        "Charges": un["orig_charges"], "DPD Bucket": un["orig_dpd_bucket"],
        "In allocation file": un["orig_alloc_cm"].fillna("— not found —"),
        "Charges CM (info)": un["orig_charges_cm"], "Assign CM": None,
    })
    out = st.data_editor(
        edit, hide_index=True, width="stretch", key=key,
        disabled=[c for c in edit.columns if c != "Assign CM"],
        column_config={"Assign CM": st.column_config.SelectboxColumn("Assign CM", options=cms, required=False),
                       "Overdue": st.column_config.NumberColumn(format="localized"),
                       "Charges": st.column_config.NumberColumn(format="localized")},
    )
    note = st.text_input("Reason / note for this assignment (saved in audit trail)", key=key + "_note")
    todo = out[out["Assign CM"].notna()]
    if st.button(f"Save {len(todo)} assignment(s)", disabled=todo.empty, type="primary", key=key + "_btn"):
        for r in todo.itertuples():
            batch_mod.assign_cm(bid, r[1], r[-1], note or None)
        st.success("Saved. The original allocation-file value is kept unchanged for history.")
        st.rerun()


def render():
    st.title("👥 CM-wise Allocation")
    bid = batch_selector("alloc_sel")
    if not bid:
        return
    k = reports.cases(bid)
    if k.empty:
        st.info("This batch has no cases with dues.")
        return
    h = reports.headline(k)
    m = st.columns(6)
    m[0].metric("Total inbound cases", h["Total inbound cases"])
    m[1].metric("With overdue", h["Cases with overdue"])
    m[2].metric("With charges", h["Cases with charges"])
    m[3].metric("With both", h["Cases with both"])
    m[4].metric("Total overdue", inr(h["Total overdue (₹)"]))
    m[5].metric("Total charges", inr(h["Total charges (₹)"]))

    st.subheader("Unassigned cases")
    unassigned_editor(bid, "alloc_unassigned")

    st.subheader("CM-wise summary")
    show_table(reports.cm_summary(k))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Case type / DPD bucket**")
        show_table(reports.case_type_pivot(k, bucket_order()))
    with c2:
        st.markdown("**CM × DPD bucket (case count)**")
        show_table(reports.cm_dpd_matrix(k, bucket_order()))

    st.subheader("Case list by CM")
    cms = reports.cm_summary(k)["CM / Team"].tolist()[:-1]
    cm = st.selectbox("CM / Team", cms)
    sub = reports.cases_display(k)
    sub = sub[sub["CM / Team"] == cm]
    st.caption(f"{len(sub)} cases · overdue {inr(sub['Overdue'].sum())} · charges {inr(sub['Charges'].sum())}")
    show_table(sub, height=400)
    st.download_button(f"⬇ Download {cm} cases (Excel)", reports.cm_workbook(bid, cm),
                       file_name=f"{bid}_{cm.replace(' ', '_')}.xlsx")
