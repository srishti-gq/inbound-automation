"""Source Files – Loan Live Portfolio and CM allocation files."""
from __future__ import annotations

from datetime import date

import streamlit as st

from core import sources
from core.sources import SOURCE_KINDS, SourceFileError
from views.common import page_header, show_table

KINDS = [("portfolio", True), ("allocation", True), ("charges_allocation", False)]


def _card(kind: str, required: bool):
    latest = sources.latest_source(kind)
    with st.container(border=True):
        st.markdown(f"**{SOURCE_KINDS[kind].replace(' (optional)', '')}**"
                    + ("" if required else " <span class='muted'>(optional)</span>"), unsafe_allow_html=True)
        if latest:
            st.markdown(
                f"<div class='muted'>{latest['original_name']}<br>"
                f"Data date <b>{latest['as_of_date'] or '—'}</b> · {latest['row_count']:,} rows<br>"
                f"Uploaded {latest['uploaded_at']}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='muted'>Not uploaded yet</div>", unsafe_allow_html=True)
        st.write("")
        with st.popover("Upload new version", width="stretch"):
            f = st.file_uploader("Excel file", type=["xlsx", "xls"], key=f"up_{kind}")
            d = st.date_input("Data date", value=date.today(), key=f"dt_{kind}", format="DD-MM-YYYY")
            if st.button("Save", key=f"save_{kind}", disabled=f is None, type="primary", width="stretch"):
                with st.spinner("Reading file…"):
                    try:
                        r = sources.register_source(kind, f.name, f.getvalue(), d.isoformat())
                    except SourceFileError as e:
                        st.error(str(e))
                        return
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not read the file: {e}")
                        return
                st.session_state["src_msg"] = f"{SOURCE_KINDS[kind]} saved: {r['rows']:,} rows (sheet '{r['sheet']}')."
                st.rerun()


def show_saved_message():
    if msg := st.session_state.pop("src_msg", None):
        st.success(msg)


def render():
    page_header("Source Files", "Upload a new version whenever you have a newer file. Older versions are kept.")
    show_saved_message()
    cols = st.columns(3, gap="medium")
    for col, (kind, req) in zip(cols, KINDS):
        with col:
            _card(kind, req)
    st.write("")
    st.subheader("Version history")
    df = sources.list_sources()
    df = df[df["kind"] != "inbound"].rename(columns={
        "id": "Version", "kind": "Type", "original_name": "File", "as_of_date": "Data date",
        "uploaded_at": "Uploaded", "uploaded_by": "By", "row_count": "Rows", "duplicate_ids": "Duplicate rows"})
    df["Type"] = df["Type"].map(lambda k: SOURCE_KINDS.get(k, k).replace(" (optional)", ""))
    show_table(df[["Version", "Type", "File", "Data date", "Uploaded", "By", "Rows", "Duplicate rows"]])
