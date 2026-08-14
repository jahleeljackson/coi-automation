"""Authentication and RBAC helpers for the COI Streamlit app."""

from __future__ import annotations

from typing import Iterable

import bcrypt
import streamlit as st

from streamlit_app.utils.airtable_client import get_user_by_email, update_user


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def login(email: str, password: str) -> dict | None:
    user = get_user_by_email(email.strip())
    if not user:
        return None
    if user.get("is_active") is False:
        return None
    password_hash = user.get("password_hash") or ""
    if not password_hash or not verify_password(password, password_hash):
        return None
    # Best-effort last_login update; ignore failures
    try:
        from datetime import datetime, timezone

        update_user(
            user["id"],
            {"last_login": datetime.now(timezone.utc).isoformat()},
        )
    except Exception:
        pass
    return {
        "id": user["id"],
        "email": user.get("email"),
        "name": user.get("name") or user.get("email"),
        "role": (user.get("role") or "agent").lower(),
    }


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def current_user() -> dict | None:
    return st.session_state.get("user")


def require_auth(allowed_roles: Iterable[str] | None = None) -> dict:
    user = current_user()
    if not user:
        st.warning("Please log in to continue.")
        st.stop()
    if allowed_roles is not None:
        roles = {r.lower() for r in allowed_roles}
        if user.get("role", "").lower() not in roles:
            st.error("Access denied for your role.")
            st.stop()
    return user


def render_login_form() -> None:
    st.title("COI Request MVP")
    st.caption("Sign in to review certificate drafts.")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        if not email or not password:
            st.error("Email and password are required.")
            return
        try:
            user = login(email, password)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Login failed: {exc}")
            return
        if not user:
            st.error("Invalid credentials or inactive account.")
            return
        st.session_state["user"] = user
        st.rerun()
