"""Settings – column mapping, business rules, audit log."""
from __future__ import annotations

import streamlit as st

from core import config
from core.db import query_df
from views.common import page_header, show_table


def _yaml_editor(path, key):
    text = st.text_area("Configuration", config.read_text(path), height=440, key=key, label_visibility="collapsed")
    if st.button("Save changes", key=key + "_save", type="primary"):
        try:
            config.save_yaml_text(path, text)
            st.success("Saved. Applies to new uploads; existing batches are not changed.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Not saved – invalid configuration: {e}")


def render():
    page_header("Settings", "Configuration used when reading files and creating batches")
    t = st.tabs(["Column mapping", "Business rules", "Audit log"])
    with t[0]:
        st.caption("Possible column headers for each field. Matching ignores case, spaces and punctuation.")
        _yaml_editor(config.MAPPING_FILE, "map")
    with t[1]:
        st.caption("DPD buckets, missing-value markers, hold patterns and Batch ID prefix.")
        _yaml_editor(config.SETTINGS_FILE, "settings")
    with t[2]:
        show_table(query_df(
            "SELECT ts AS Time, user AS User, action AS Action, batch_id AS Batch, detail AS Detail "
            "FROM audit_log ORDER BY id DESC LIMIT 500"), height=480)
