"""Module 1 – Upload inbound report, manage source files, create a batch."""
from __future__ import annotations

import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core import batch as batch_mod
from core import inbound, sources
from core.sources import SOURCE_KINDS, SourceFileError
from views.common import show_table


def _source_card(kind: str, required: bool):
    latest = sources.latest_source(kind)
    with st.container(border=True):
        st.markdown(f"**{SOURCE_KINDS[kind]}**")
        if latest:
            st.caption(f"Current: `{latest['original_name']}`")
            st.write(f"Data date: **{latest['as_of_date'] or '—'}**  \nUploaded: {latest['uploaded_at']}  \n"
                     f"Rows: {latest['row_count']:,} · Unique IDs: {latest['unique_ids']:,}"
                     + (f" · ⚠️ {latest['duplicate_ids']:,} duplicate rows" if latest["duplicate_ids"] else ""))
        else:
            st.warning("Not uploaded yet" if required else "Not uploaded (optional)")
        with st.expander("Upload new version", expanded=latest is None and required):
            f = st.file_uploader("Excel file", type=["xlsx", "xls"], key=f"up_{kind}")
            d = st.date_input("Data date of this file", value=date.today(), key=f"dt_{kind}", format="DD-MM-YYYY")
            if st.button("Save file", key=f"save_{kind}", disabled=f is None, type="primary"):
                data = f.getvalue()
                dup = sources.find_by_sha(kind, sources.sha256_bytes(data))
                if dup:
                    st.warning(f"This exact file was already uploaded on {dup['uploaded_at']} (version #{dup['id']}). Saved again as a new version.")
                with st.spinner("Reading and validating file… (large files take a few seconds)"):
                    try:
                        r = sources.register_source(kind, f.name, data, d.isoformat())
                    except SourceFileError as e:
                        st.error(str(e))
                        return
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not read the file: {e}")
                        return
                st.success(f"Saved: {r['rows']:,} rows from sheet '{r['sheet']}'.")
                st.json(r["columns"], expanded=False)
                st.rerun()


def _version_select(kind: str, label: str, optional: bool = False):
    df = sources.list_sources(kind)
    if df.empty:
        return None
    opts = df["id"].tolist()
    fmt = {r.id: f"#{r.id} · {r.original_name} · data date {r.as_of_date or '—'}" for r in df.itertuples()}
    if optional:
        opts = [None] + opts
        fmt[None] = "— Do not use —"
    return st.selectbox(label, opts, index=1 if optional and len(opts) > 1 else 0, format_func=lambda i: fmt[i])


def render():
    st.title("📤 Upload Inbound Report")
    st.caption("Each upload becomes an independent batch with its own Batch ID. Nothing is overwritten.")

    st.subheader("Step 1 · Source files")
    c1, c2, c3 = st.columns(3)
    with c1:
        _source_card("portfolio", True)
    with c2:
        _source_card("allocation", True)
    with c3:
        _source_card("charges_allocation", False)

    st.divider()
    st.subheader("Step 2 · Inbound calling report")
    f = st.file_uploader("Upload the report downloaded from the inbound calling panel", type=["xlsx", "xls"], key="up_inbound")
    if f is None:
        return

    data = f.getvalue()
    sha = sources.sha256_bytes(data)
    cache = st.session_state.get("inbound_parse")
    if not cache or cache["sha"] != sha:
        with st.spinner("Reading inbound report…"):
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

    prev = sources.find_by_sha("inbound", sha)
    if prev:
        st.warning(f"⚠️ This exact inbound file was already uploaded on {prev['uploaded_at']}. "
                   "Creating another batch from it will duplicate cases.")

    m = st.columns(5)
    m[0].metric("Calls (rows)", len(parsed.calls))
    m[1].metric("Unique App IDs", len(parsed.id_index))
    m[2].metric("IDs in >1 call", int((parsed.id_index["n_calls"] > 1).sum()))
    m[3].metric("Calls without App ID", len(parsed.unidentified))
    m[4].metric("Latest call date", parsed.calling_date or "—")

    with st.expander(f"Detected sheet '{det.sheet}' (header row {det.header_row + 1}) and column mapping"):
        st.table(pd.DataFrame({"Field": list(det.columns), "Column in file": list(det.columns.values())}))
        if det.missing_optional:
            st.caption("Optional fields not found: " + ", ".join(det.missing_optional))
    st.markdown("**Preview (first 20 calls)**")
    show_table(parsed.calls.drop(columns=["id_list"]).head(20))
    listed = parsed.id_index["listed_as"].value_counts().to_dict()
    st.caption("App IDs by inbound-report tag: " + ", ".join(f"{k}: {v}" for k, v in listed.items()))

    st.divider()
    st.subheader("Step 3 · Create batch")
    if sources.latest_source("portfolio") is None or sources.latest_source("allocation") is None:
        st.error("Upload the Loan Live Portfolio and CM Allocation files in Step 1 first.")
        return
    a, b = st.columns(2)
    with a:
        default_day = datetime.strptime(parsed.calling_date, "%Y-%m-%d").date() if parsed.calling_date else date.today()
        calling_date = st.date_input("Calling activity date", value=default_day, format="DD-MM-YYYY")
        notes = st.text_input("Notes (optional)")
    with b:
        pf = _version_select("portfolio", "Loan Live Portfolio version")
        al = _version_select("allocation", "CM Allocation version")
        ch = _version_select("charges_allocation", "Charges Allocation version (optional)", optional=True)
    confirm = True
    if prev:
        confirm = st.checkbox("I understand this file was processed before – create a new batch anyway")
    if st.button("▶ Process & create batch", type="primary", disabled=not confirm):
        with st.spinner("Enriching data and creating batch…"):
            try:
                fid = sources.register_inbound_file(cache["name"], cache["data"], det)
                bid = batch_mod.create_batch(parsed, fid, calling_date.isoformat(), pf, al, ch, notes or None)
            except Exception as e:  # noqa: BLE001
                st.error(f"Processing failed – nothing was saved. Details: {e}")
                return
        st.session_state["selected_batch"] = bid
        st.session_state.pop("inbound_parse", None)
        info = batch_mod.get_batch(bid)
        st.success(f"✅ Batch **{bid}** created: {info['total_cases']} cases from {info['total_app_ids']} App IDs.")
        st.info("Open **Batch Management** or **CM-wise Allocation** in the menu to review it.")
