"""Modules that will be built in the next phases."""
import streamlit as st


def _soon(title: str, phase: str, points: list[str]):
    st.title(title)
    st.info(f"Planned for **{phase}**. The data needed for this (original snapshot, CM allocation, "
            "batch history) is already being stored for every batch.")
    for p in points:
        st.markdown(f"- {p}")


def email():
    _soon("✉️ Email Management", "Phase 2", [
        "CM-wise email drafts with preview", "Approve-before-send", "No duplicate email per batch / CM / cycle",
        "Send log, failures and retry"])


def recheck():
    _soon("🔁 Outstanding Recheck", "Phase 3", [
        "Compare latest portfolio with the frozen original snapshot",
        "No Payment / Partially Paid / Fully Paid / Outstanding Increased / Data Not Found",
        "Actual payment from payment data where available; ambiguous cases flagged",
        "Second follow-up list with only No-Payment cases"])


def mis():
    _soon("📑 MIS & History", "Phase 4", [
        "Update the Google Sheet MIS keyed on Batch ID + Application ID", "No duplicate rows", "Error log"])


def analytics():
    _soon("📈 Recovery Analytics", "Phase 5", [
        "Batch, CM and DPD-bucket recovery", "Actual cash recovered vs outstanding reduction"])
