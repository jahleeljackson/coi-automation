"""Admin user management."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.auth import hash_password, require_auth
from streamlit_app.utils.airtable_client import create_user, list_users, update_user

st.set_page_config(page_title="Admin Users", layout="wide")
require_auth(allowed_roles=["admin"])

st.title("Users")

try:
    users = list_users()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load users: {exc}")
    users = []

if users:
    st.dataframe(
        [
            {
                "id": u.get("id"),
                "email": u.get("email"),
                "name": u.get("name"),
                "role": u.get("role"),
                "is_active": u.get("is_active", True),
            }
            for u in users
        ],
        use_container_width=True,
    )

st.subheader("Create user")
with st.form("create_user"):
    email = st.text_input("Email")
    name = st.text_input("Name")
    role = st.selectbox("Role", ["agent", "admin"])
    password = st.text_input("Temporary password", type="password")
    active = st.checkbox("Active", value=True)
    submitted = st.form_submit_button("Create")
if submitted:
    if not email or not password:
        st.error("Email and password required.")
    else:
        try:
            create_user(
                {
                    "email": email.strip(),
                    "name": name.strip(),
                    "role": role,
                    "password_hash": hash_password(password),
                    "is_active": active,
                }
            )
            st.success("User created.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))

st.subheader("Deactivate / role update")
if users:
    options = {f"{u.get('email')} ({u.get('id')})": u for u in users}
    key = st.selectbox("User", list(options.keys()))
    selected = options[key]
    new_role = st.selectbox(
        "Role",
        ["agent", "admin"],
        index=0 if (selected.get("role") or "agent") == "agent" else 1,
    )
    is_active = st.checkbox("Active", value=bool(selected.get("is_active", True)))
    if st.button("Update user"):
        try:
            update_user(
                selected["id"], {"role": new_role, "is_active": is_active}
            )
            st.success("Updated.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))
