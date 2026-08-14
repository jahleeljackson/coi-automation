"""COI MVP Streamlit entrypoint — login + role-aware navigation."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Allow `streamlit run streamlit_app/app.py` from repo root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.auth import current_user, logout, render_login_form, require_auth

st.set_page_config(page_title="COI Request MVP", layout="wide")


def _nav() -> None:
    user = require_auth()
    st.sidebar.markdown(f"**{user.get('name') or user.get('email')}**")
    st.sidebar.caption(f"Role: {user.get('role')}")
    st.sidebar.page_link("pages/1_Queue.py", label="Request queue")
    if user.get("role") == "admin":
        st.sidebar.page_link("pages/2_Admin_Metrics.py", label="Metrics")
        st.sidebar.page_link("pages/3_Admin_Users.py", label="Users")
        st.sidebar.page_link("pages/4_Admin_Settings.py", label="Agency settings")
    if st.sidebar.button("Sign out"):
        logout()
        st.rerun()


def main() -> None:
    user = current_user()
    if not user:
        render_login_form()
        return
    _nav()
    st.title("COI Request MVP")
    st.write(
        "Use **Request queue** to review drafts. "
        "Admins can open metrics, users, and agency settings from the sidebar."
    )


if __name__ == "__main__":
    main()
else:
    # Streamlit executes the script at import/run time
    main()
