"""GrayQuest – Inbound Calling & Recovery Follow-up Dashboard.

Run from the project folder:
    streamlit run app.py
"""
import streamlit as st

from core.db import init_db
from views import batches, common, dashboard, new_batch, settings_page, source_files

st.set_page_config(page_title="Inbound Recovery | GrayQuest", page_icon="assets/logo.svg", layout="wide")
init_db()
common.apply_style()
st.logo("assets/logo.svg", size="large")

common.PAGES.update({
    "dashboard": st.Page(dashboard.render, title="Dashboard", icon=":material/space_dashboard:", default=True),
    "new_batch": st.Page(new_batch.render, title="New Batch", icon=":material/upload_file:", url_path="new-batch"),
    "batches": st.Page(batches.render, title="Batches", icon=":material/folder_open:", url_path="batches"),
    "sources": st.Page(source_files.render, title="Source Files", icon=":material/database:", url_path="source-files"),
    "settings": st.Page(settings_page.render, title="Settings", icon=":material/settings:", url_path="settings"),
})
st.navigation(list(common.PAGES.values())).run()
