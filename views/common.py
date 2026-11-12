"""Shared UI helpers."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import batch as batch_mod
from core import config


def inr(x) -> str:
    """Indian number format: 1234567 -> ₹12,34,567"""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    n = int(round(float(x)))
    sign, s = ("-" if n < 0 else ""), str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"{sign}₹{s}"


def bucket_order() -> list[str]:
    return [b["label"] for b in config.settings()["dpd_buckets"]]


MONEY_COLS = ["Overdue", "Charges", "Total Overdue", "Total Charges", "Total Outstanding",
              "Sum of Overdue", "Sum of Charges", "orig_overdue", "orig_charges"]


def money_config(df: pd.DataFrame) -> dict:
    return {c: st.column_config.NumberColumn(c, format="localized") for c in df.columns if c in MONEY_COLS}


def show_table(df: pd.DataFrame, height: int | None = None, **kw):
    if df is None or df.empty:
        st.info("No records.")
        return
    args = dict(width="stretch", hide_index=True, column_config=money_config(df), **kw)
    if height:
        args["height"] = height
    st.dataframe(df, **args)


def batch_selector(key: str, label: str = "Select batch") -> str | None:
    df = batch_mod.list_batches()
    if df.empty:
        st.info("No batches yet. Start with **Upload Inbound Report**.")
        return None
    ids = df["batch_id"].tolist()
    pre = st.session_state.get("selected_batch")
    idx = ids.index(pre) if pre in ids else 0
    fmt = {r.batch_id: f"{r.batch_id}  ·  calling {r.calling_date}  ·  {r.total_cases} cases" for r in df.itertuples()}
    choice = st.selectbox(label, ids, index=idx, format_func=lambda b: fmt[b], key=key)
    st.session_state["selected_batch"] = choice
    return choice


STATUS_ICON = {
    "Processed": "🟢", "Processed with exceptions": "🟠", "Not started": "⚪", "Not due": "⚪",
    "Not updated": "⚪", "Pending": "🟠", "Resolved": "🟢", "Reprocessing": "🔵",
}


def status_badge(label: str, value: str) -> str:
    return f"**{label}:** {STATUS_ICON.get(value, '•')} {value}"
