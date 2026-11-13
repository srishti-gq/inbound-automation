"""New Batch – upload the inbound calling report and create a batch."""
from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core import batch as batch_mod
from core import inbound, sources
from views.common import PAGES, page_header, show_table


def _version_select(kind: str, label: str, optional: bool = False):
    df = sources.list_sources(kind)
    if df.empty:
        return None
    opts = df["id"].tolist()
    fmt = {r.id: f"v{r.id} · {r.original_name} · data date {r.as_of_date or '—'}" for r in df.itertuples()}
    if optional:
        opts = opts + [None]
        fmt[None] = "Do not use"
    return st.selectbox(label, opts, index=0, format_func=lambda i: fmt[i])


def render():
    page_header("New Batch", "Upload the report from the inbound calling panel. Each upload becomes a separate batch.")

    pf, al = sources.latest_source("portfolio"), sources.latest_source("allocation")
    if pf is None or al is None:
        st.warning("Upload the Loan Live Portfolio and CM Allocation files first.")
        st.page_link(PAGES["sources"], label="Go to Source Files", icon=":material/arrow_forward:")
        return
    st.markdown(
        f"<div class='muted'>Using portfolio dated <b>{pf['as_of_date']}</b> and CM allocation dated "
        f"<b>{al['as_of_date']}</b>.</div>", unsafe_allow_html=True)
    st.write("")

    f = st.file_uploader("Inbound calling report (.xlsx / .xls)", type=["xlsx", "xls"], key="up_inbound")
    if f is None:
        return

    data = f.getvalue()
    sha = sources.sha256_bytes(data)
    cache = st.session_state.get("inbound_parse")
    if not cache or cache["sha"] != sha:
        with st.spinner("Reading report…"):
            with tempfile.NamedTemporaryFile(suffix=Path(f.name).suffix, delete=False) as tmp:
                tmp.write(data)
            try:
                parsed = inbound.parse_inbound(tmp.name)
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
                return
            finally:
                Path(tmp.name).unlink(missing_ok=True)
        cache = {"sha": sha, "name": f.name, "parsed": parsed, "data": data}
        st.session_state["inbound_parse"] = cache
    parsed: inbound.InboundParse = cache["parsed"]
    det = parsed.detection

    st.subheader("Preview")
    m = st.columns(4)
    m[0].metric("Calls", len(parsed.calls))
    m[1].metric("Application IDs", len(parsed.id_index))
    m[2].metric("Calls without App ID", len(parsed.unidentified))
    m[3].metric("Latest call date", parsed.calling_date or "—")

    with st.expander("View calls"):
        show_table(parsed.calls.drop(columns=["id_list"]).rename(columns=lambda c: c.replace("_", " ").title()),
                   height=320)
    with st.expander("Column mapping"):
        st.caption(f"Sheet '{det.sheet}', header row {det.header_row + 1}")
        show_table(pd.DataFrame({"Field": list(det.columns), "Column in file": list(det.columns.values())}))

    prev = sources.find_by_sha("inbound", sha)
    st.subheader("Create batch")
    with st.form("create_batch", border=True):
        a, b = st.columns(2)
        default_day = datetime.strptime(parsed.calling_date, "%Y-%m-%d").date() if parsed.calling_date else date.today()
        calling_date = a.date_input("Calling activity date", value=default_day, format="DD-MM-YYYY")
        notes = b.text_input("Notes (optional)")
        with st.expander("Source file versions"):
            pfv = _version_select("portfolio", "Loan Live Portfolio")
            alv = _version_select("allocation", "CM Allocation")
            chv = _version_select("charges_allocation", "Charges Allocation (optional)", optional=True)
        confirm = True
        if prev:
            st.warning(f"This file was already uploaded on {prev['uploaded_at']}. A new batch will duplicate cases.")
            confirm = st.checkbox("Create a new batch anyway")
        submitted = st.form_submit_button("Create batch", type="primary")

    if submitted:
        if not confirm:
            st.error("Tick the confirmation to create a duplicate batch.")
            return
        with st.spinner("Processing…"):
            try:
                fid = sources.register_inbound_file(cache["name"], cache["data"], det)
                bid = batch_mod.create_batch(parsed, fid, calling_date.isoformat(), pfv, alv, chv, notes or None)
            except Exception as e:  # noqa: BLE001
                st.error(f"Processing failed. Nothing was saved. Details: {e}")
                return
        st.session_state["selected_batch"] = bid
        st.session_state.pop("inbound_parse", None)
        st.session_state["batch_msg"] = f"Batch {bid} created."
        st.switch_page(PAGES["batches"])
