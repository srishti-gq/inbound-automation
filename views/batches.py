"""Batches – everything about one batch on a single page."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import batch as batch_mod
from core import reports, sources
from core.db import query_df
from core.exception_types import EXCEPTION_TYPES
from views.common import PAGES, batch_selector, bucket_order, inr, page_header, pill, show_table


def _assign_section(bid: str, k: pd.DataFrame):
    un = k[k["assigned_cm"].isna()]
    if un.empty:
        return
    b = batch_mod.get_batch(bid)
    cms = sources.distinct_cms(b["allocation_file_id"])
    with st.container(border=True):
        st.markdown(f"**{len(un)} cases need a CM** "
                    "<span class='muted'>— not in the allocation file, or marked Hold</span>", unsafe_allow_html=True)
        edit = pd.DataFrame({
            "Application ID": un["app_id"].values, "Student": un["student_name"].values,
            "Overdue": un["orig_overdue"].values, "Charges": un["orig_charges"].values,
            "Allocation file": un["orig_alloc_cm"].fillna("Not found").values,
            "Assign CM": [None] * len(un),
        })
        out = st.data_editor(
            edit, hide_index=True, width="stretch", key=f"assign_{bid}",
            disabled=[c for c in edit.columns if c != "Assign CM"],
            column_config={"Assign CM": st.column_config.SelectboxColumn("Assign CM", options=cms),
                           "Overdue": st.column_config.NumberColumn(format="localized"),
                           "Charges": st.column_config.NumberColumn(format="localized")},
        )
        todo = out[out["Assign CM"].notna()]
        a, b2 = st.columns([3, 1])
        note = a.text_input("Note", placeholder="Reason for assignment (optional)", label_visibility="collapsed",
                            key=f"note_{bid}")
        if b2.button(f"Save ({len(todo)})", disabled=todo.empty, type="primary", width="stretch", key=f"save_{bid}"):
            for r in todo.itertuples(index=False):
                batch_mod.assign_cm(bid, r[0], r[-1], note or None)
            st.rerun()


def _allocation_tab(bid: str, k: pd.DataFrame):
    _assign_section(bid, k)
    st.subheader("CM-wise summary")
    show_table(reports.cm_summary(k))
    st.subheader("DPD bucket")
    left, right = st.columns(2, gap="large")
    with left:
        show_table(reports.case_type_pivot(k, bucket_order()))
    with right:
        show_table(reports.cm_dpd_matrix(k, bucket_order()))


def _cases_tab(bid: str, k: pd.DataFrame):
    disp = reports.cases_display(k)
    cms = ["All CMs"] + sorted(disp["CM / Team"].unique().tolist())
    a, b = st.columns([2, 1])
    cm = a.selectbox("CM", cms, label_visibility="collapsed")
    if cm != "All CMs":
        disp = disp[disp["CM / Team"] == cm]
        b.download_button("Download CM list", reports.cm_workbook(bid, cm), width="stretch",
                          file_name=f"{bid}_{cm.replace(' ', '_')}.xlsx", icon=":material/download:")
    st.caption(f"{len(disp)} cases · Overdue {inr(disp['Overdue'].sum())} · Charges {inr(disp['Charges'].sum())}")
    cols = ["Application ID", "Student Name", "Institute", "Overdue", "Charges", "DPD (Days)", "DPD Bucket",
            "Case Type", "CM / Team", "Issue Category", "Customer Concern", "Calling Mobile"]
    show_table(disp[cols], height=480)


def _exceptions_tab(bid: str):
    df = reports.exceptions(bid)
    if df.empty:
        st.markdown("<div class='muted'>No exceptions.</div>", unsafe_allow_html=True)
        return
    status = st.segmented_control("Status", ["Pending", "Resolved", "All"], default="Pending",
                                  label_visibility="collapsed", key=f"exs_{bid}") or "Pending"
    if status != "All":
        df = df[df["status"] == status] if status == "Resolved" else df[df["status"] != "Resolved"]
    view = pd.DataFrame({
        "Select": False, "ID": df["id"], "Application ID": df["app_id"], "Exception": df["exception"],
        "Detail": df["detail"], "Status": df["status"], "Note": df["resolution_note"],
    })
    out = st.data_editor(view, hide_index=True, width="stretch", height=380, key=f"exc_{bid}_{status}",
                         disabled=[c for c in view.columns if c != "Select"],
                         column_config={"ID": None})
    sel = out.loc[out["Select"], "ID"].tolist()
    if status != "Resolved":
        a, b = st.columns([3, 1])
        note = a.text_input("Resolution note", placeholder="Resolution note (required)",
                            label_visibility="collapsed", key=f"exn_{bid}")
        if b.button(f"Mark resolved ({len(sel)})", disabled=not sel or not note.strip(),
                    width="stretch", key=f"exb_{bid}"):
            batch_mod.resolve_exceptions([int(i) for i in sel], "Resolved", note.strip())
            st.rerun()
    st.caption("CM-related exceptions are resolved automatically when a CM is assigned in the Allocation tab.")


def _calls_tab(bid: str):
    calls = reports.calls(bid).rename(columns={
        "call_no": "#", "call_time": "Time", "calling_mobile": "Mobile", "student_name": "Student",
        "institute": "Institute", "issue_category": "Issue Category", "issue_details": "Issue Details",
        "outcome": "Outcome", "app_ids": "App IDs"})
    show_table(calls[["#", "Time", "Mobile", "Student", "Institute", "Issue Category", "Issue Details",
                      "Outcome", "App IDs"]], height=420)
    st.subheader("Application IDs in report")
    ids = reports.app_ids(bid).rename(columns={
        "app_id": "Application ID", "n_calls": "Calls", "listed_as": "Tag in report", "match_status": "Result"})
    st.caption(" · ".join(f"{k}: {v}" for k, v in ids["Result"].value_counts().items()))
    show_table(ids[["Application ID", "Result", "Tag in report", "Calls"]], height=320)


def _history_tab(bid: str, b):
    src = query_df(
        "SELECT kind, original_name, as_of_date, uploaded_at FROM source_files WHERE id IN (?,?,?,?)",
        (b["inbound_file_id"], b["portfolio_file_id"], b["allocation_file_id"], b["charges_file_id"] or -1),
    ).rename(columns={"kind": "Type", "original_name": "File", "as_of_date": "Data date", "uploaded_at": "Uploaded"})
    st.subheader("Files used")
    show_table(src)
    st.subheader("Activity")
    show_table(query_df(
        "SELECT ts AS Time, user AS User, action AS Action, detail AS Detail FROM audit_log WHERE batch_id=? ORDER BY id DESC",
        (bid,)))


def render():
    if msg := st.session_state.pop("batch_msg", None):
        st.toast(msg)
    head_l, head_r = st.columns([3, 2], vertical_alignment="bottom")
    with head_l:
        page_header("Batches")
    with head_r:
        bid = batch_selector("batch_sel")
    if not bid:
        st.info("No batches yet.")
        st.page_link(PAGES["new_batch"], label="Create a batch", icon=":material/arrow_forward:")
        return

    b = batch_mod.get_batch(bid)
    k = reports.cases(bid)
    st.markdown(
        pill(b["processing_status"]) + pill(b["email_status"], "Email") + pill(b["recheck_status"], "Recheck")
        + pill(b["mis_status"], "MIS")
        + f"<span class='muted'> &nbsp; Calling date {b['calling_date']} · created {b['created_at'][:16]}</span>",
        unsafe_allow_html=True)
    st.write("")

    h = reports.headline(k) if len(k) else {}
    m = st.columns(4)
    m[0].metric("Cases", b["total_cases"], help=f"{b['total_app_ids']} App IDs from {b['total_calls']} calls")
    m[1].metric("Overdue", inr(h.get("Total overdue (₹)", 0)))
    m[2].metric("Charges", inr(h.get("Total charges (₹)", 0)))
    m[3].metric("Unassigned", h.get("Unassigned cases", 0))

    st.download_button("Download batch report", reports.batch_workbook(bid, bucket_order()),
                       file_name=f"{bid}_processed.xlsx", icon=":material/download:")

    open_exc = int((reports.exceptions(bid)["status"] != "Resolved").sum())
    t = st.tabs(["Allocation", "Cases", f"Exceptions ({open_exc})", "Calls", "History"])
    with t[0]:
        _allocation_tab(bid, k) if len(k) else st.info("No cases with dues in this batch.")
    with t[1]:
        _cases_tab(bid, k) if len(k) else st.info("No cases.")
    with t[2]:
        _exceptions_tab(bid)
    with t[3]:
        _calls_tab(bid)
    with t[4]:
        _history_tab(bid, b)
