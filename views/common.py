"""Shared UI helpers and styling."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import batch as batch_mod
from core import config

PAGES: dict = {}   # filled in app.py, used for page links

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px;}
h1 {font-size: 1.55rem !important; font-weight: 600 !important; padding-bottom: 0 !important;}
h2 {font-size: 1.15rem !important; font-weight: 600 !important;}
h3 {font-size: 1.0rem !important; font-weight: 600 !important;}
.page-sub {color: #6B7280; font-size: 0.9rem; margin: -0.4rem 0 1.4rem 0;}
[data-testid="stMetric"] {
    background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 14px 18px;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.75rem; color: #6B7280; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600;
}
[data-testid="stMetricValue"] {font-size: 1.55rem; font-weight: 600; color: #111827;}
[data-testid="stSidebar"] {border-right: 1px solid #E5E7EB;}
.stTabs [data-baseweb="tab-list"] {gap: 1.5rem; border-bottom: 1px solid #E5E7EB;}
.stTabs [data-baseweb="tab"] {padding-left: 0; padding-right: 0;}
.pill {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78rem;
       font-weight: 600; margin-right: 6px; border: 1px solid transparent;}
.pill-green {background: #ECFDF3; color: #067647; border-color: #ABEFC6;}
.pill-amber {background: #FFFAEB; color: #B54708; border-color: #FEDF89;}
.pill-grey  {background: #F2F4F7; color: #475467; border-color: #E4E7EC;}
.pill-blue  {background: #EFF8FF; color: #175CD3; border-color: #B2DDFF;}
.muted {color: #6B7280; font-size: 0.85rem;}
</style>
"""


def apply_style():
    st.markdown(CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str | None = None):
    st.title(title)
    if subtitle:
        st.markdown(f"<div class='page-sub'>{subtitle}</div>", unsafe_allow_html=True)


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


MONEY_COLS = {"Overdue", "Charges", "Total Overdue", "Total Charges", "Total Outstanding",
              "Sum of Overdue", "Sum of Charges"}


def show_table(df: pd.DataFrame, height: int | None = None, **kw):
    if df is None or df.empty:
        st.markdown("<div class='muted'>No records.</div>", unsafe_allow_html=True)
        return
    cfg = {c: st.column_config.NumberColumn(c, format="localized") for c in df.columns if c in MONEY_COLS}
    args = dict(width="stretch", hide_index=True, column_config=cfg, **kw)
    if height:
        args["height"] = height
    st.dataframe(df, **args)


def batch_selector(key: str) -> str | None:
    df = batch_mod.list_batches()
    if df.empty:
        return None
    ids = df["batch_id"].tolist()
    pre = st.session_state.get("selected_batch")
    idx = ids.index(pre) if pre in ids else 0
    fmt = {r.batch_id: f"{r.batch_id}   ·   Calling date {r.calling_date}   ·   {r.total_cases} cases"
           for r in df.itertuples()}
    choice = st.selectbox("Batch", ids, index=idx, format_func=lambda b: fmt[b], key=key, label_visibility="collapsed")
    st.session_state["selected_batch"] = choice
    return choice


_PILL = {
    "Processed": "green", "Resolved": "green", "Sent": "green", "Updated": "green",
    "Processed with exceptions": "amber", "Pending": "amber",
    "Reprocessing": "blue",
}


def pill(text: str, label: str | None = None) -> str:
    color = _PILL.get(text, "grey")
    return f"<span class='pill pill-{color}'>{(label + ': ') if label else ''}{text}</span>"
