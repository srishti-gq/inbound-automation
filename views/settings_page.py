"""Settings: source file history, column mapping, rules, audit log."""
from __future__ import annotations

import streamlit as st

from core import config, sources
from core.db import query_df
from views.common import show_table


def _yaml_editor(path, key):
    text = st.text_area("YAML", config.read_text(path), height=420, key=key)
    if st.button("Save", key=key + "_save", type="primary"):
        try:
            config.save_yaml_text(path, text)
            st.success("Saved. New uploads will use this configuration (existing batches are not changed).")
        except Exception as e:  # noqa: BLE001
            st.error(f"Not saved – invalid configuration: {e}")


def render():
    st.title("⚙️ Settings")
    t = st.tabs(["Source file history", "Column mapping", "Business rules", "Audit log"])
    with t[0]:
        st.caption("Every uploaded file is kept as a separate version. Batches always point to the exact version they used.")
        show_table(sources.list_sources())
    with t[1]:
        st.caption("For each field, list the possible column headers. Matching ignores case, spaces and punctuation, "
                   "so new file formats can be supported without code changes.")
        _yaml_editor(config.MAPPING_FILE, "map")
    with t[2]:
        st.caption("DPD buckets, missing-value markers, hold patterns and thresholds.")
        _yaml_editor(config.SETTINGS_FILE, "settings")
    with t[3]:
        show_table(query_df("SELECT ts, user, action, batch_id, detail FROM audit_log ORDER BY id DESC LIMIT 500"), height=500)
