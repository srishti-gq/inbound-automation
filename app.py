"""GrayQuest – Inbound Calling & Recovery Follow-up Dashboard.

Run from the project folder:
    streamlit run app.py
"""
import streamlit as st

from core.db import init_db
from views import allocation, batches, exceptions, overview, placeholders, settings_page, upload

st.set_page_config(page_title="Inbound Recovery Dashboard", page_icon="📞", layout="wide")
init_db()

pages = {
    "Home": [
        st.Page(overview.render, title="Dashboard Overview", icon="🏠", url_path="overview", default=True),
    ],
    "Inbound Processing": [
        st.Page(upload.render, title="Upload Inbound Report", icon="📤", url_path="upload"),
        st.Page(batches.render, title="Batch Management", icon="🗂️", url_path="batches"),
        st.Page(allocation.render, title="CM-wise Allocation", icon="👥", url_path="allocation"),
        st.Page(exceptions.render, title="Exception Management", icon="⚠️", url_path="exceptions"),
    ],
    "Follow-up (coming next)": [
        st.Page(placeholders.email, title="Email Management", icon="✉️", url_path="email"),
        st.Page(placeholders.recheck, title="Outstanding Recheck", icon="🔁", url_path="recheck"),
        st.Page(placeholders.mis, title="MIS & History", icon="📑", url_path="mis"),
        st.Page(placeholders.analytics, title="Recovery Analytics", icon="📈", url_path="analytics"),
    ],
    "Admin": [
        st.Page(settings_page.render, title="Settings", icon="⚙️", url_path="settings"),
    ],
}
st.navigation(pages).run()
