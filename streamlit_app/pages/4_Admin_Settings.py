"""Admin agency / producer ACORD block settings."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.auth import require_auth
from streamlit_app.utils.airtable_client import get_agency_settings, update_agency_settings

st.set_page_config(page_title="Agency Settings", layout="wide")
require_auth(allowed_roles=["admin"])

st.title("Agency settings")
st.caption("Producer block values autofilled onto ACORD 25.")

FIELDS = [
    "producer_name",
    "producer_address_line1",
    "producer_address_line2",
    "producer_city",
    "producer_state",
    "producer_postal",
    "producer_contact_name",
    "producer_phone",
    "producer_fax",
    "producer_email",
]

try:
    settings = get_agency_settings()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load AgencySettings: {exc}")
    st.stop()

if not settings.get("id"):
    st.warning(
        "No AgencySettings row found. Create one row in Airtable, then reload."
    )
    st.stop()

with st.form("agency_settings"):
    edited = {}
    for field in FIELDS:
        edited[field] = st.text_input(field, value=str(settings.get(field) or ""))
    saved = st.form_submit_button("Save")
if saved:
    try:
        update_agency_settings(settings["id"], edited)
        st.success("Saved.")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
