"""Authentication and RBAC helpers for the COI Streamlit app."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import unquote

import tomllib
import bcrypt
import streamlit as st

from streamlit_app.config import get_settings
from streamlit_app.utils.airtable_client import (
    get_user_by_email,
    get_user_by_id,
    update_user,
)
from streamlit_app.utils.browser_cookies import (
    queue_cookie_delete,
    queue_cookie_set,
    sync_browser_cookies,
)


with open("streamlit_app/.streamlit/config.toml", "rb") as f:
    config = tomllib.load(f)

agency_name = config["agency-settings"]["name"]

AUTH_COOKIE_NAME = "coi_auth"
AUTH_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
_COOKIE_COMPONENT_KEY = "coi_auth_cm"
_PERSIST_KEY = "_persist_auth"
_SKIP_RESTORE_KEY = "_skip_cookie_restore"
_RESTORE_DONE_KEY = "_auth_restore_done"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user.get("email"),
        "name": user.get("name") or user.get("email"),
        "role": (user.get("role") or "agent").lower(),
    }


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
        update_user(
            user["id"],
            {"last_login": datetime.now(timezone.utc).isoformat()},
        )
    except Exception:
        pass
    return _public_user(user)


def logout() -> None:
    st.session_state.clear()
    st.session_state[_PERSIST_KEY] = "clear"
    st.session_state[_SKIP_RESTORE_KEY] = True


def current_user() -> dict | None:
    _queue_pending_auth_cookie()
    # Restore from the HTTP cookie before mounting the JS component.
    # Mounting CCv2 triggers a rerun; if restore_done is set first, that
    # rerun skips restore while Airtable is still in flight.
    if (
        not st.session_state.get("user")
        and not st.session_state.get(_SKIP_RESTORE_KEY)
        and not st.session_state.get(_RESTORE_DONE_KEY)
    ):
        restored = _restore_from_cookie()
        st.session_state[_RESTORE_DONE_KEY] = True
        if restored:
            st.session_state["user"] = restored
    sync_browser_cookies(key=_COOKIE_COMPONENT_KEY)
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
    st.title(f"{agency_name} COI Request Queue")
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
        st.session_state[_PERSIST_KEY] = "set"
        st.session_state.pop(_SKIP_RESTORE_KEY, None)
        st.rerun()


def _signing_key() -> bytes:
    settings = get_settings()
    secret = (settings.session_secret or "").strip()
    if secret:
        return secret.encode("utf-8")
    material = settings.airtable_api_key or "coi-mvp-dev-insecure"
    return hashlib.sha256(f"coi-auth-v1|{material}".encode("utf-8")).digest()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(body: str) -> str:
    digest = hmac.new(_signing_key(), body.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def issue_auth_token(user_id: str) -> str:
    payload = {"id": user_id, "exp": int(time.time()) + AUTH_MAX_AGE_SECONDS}
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def parse_auth_token(token: str) -> str | None:
    if not token or "." not in token:
        return None
    body, sig = token.split(".", 1)
    try:
        expected = _sign(body)
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError, TypeError):
        return None
    try:
        exp = int(payload.get("exp", 0))
    except (TypeError, ValueError):
        return None
    if exp < time.time():
        return None
    user_id = payload.get("id")
    if not isinstance(user_id, str) or not user_id:
        return None
    return user_id


def _normalize_cookie_value(raw: str) -> str:
    value = unquote(raw.strip())
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    if value.startswith('"'):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(loaded, str):
            return loaded
    return value


def _raw_auth_cookie() -> str | None:
    cookies = getattr(st.context, "cookies", None)
    if cookies is None:
        return None
    raw = cookies.get(AUTH_COOKIE_NAME)
    if not raw or not isinstance(raw, str):
        return None
    return _normalize_cookie_value(raw)


def _restore_from_cookie() -> dict | None:
    token = _raw_auth_cookie()
    if not token:
        return None
    user_id = parse_auth_token(token)
    if not user_id:
        return None
    try:
        record = get_user_by_id(user_id)
    except Exception:
        return None
    if not record or record.get("is_active") is False:
        return None
    return _public_user(record)


def _queue_pending_auth_cookie() -> None:
    action = st.session_state.pop(_PERSIST_KEY, None)
    if action == "set":
        user = st.session_state.get("user")
        if user:
            queue_cookie_set(
                AUTH_COOKIE_NAME,
                issue_auth_token(user["id"]),
                component_key=_COOKIE_COMPONENT_KEY,
                max_age=AUTH_MAX_AGE_SECONDS,
            )
    elif action == "clear":
        queue_cookie_delete(
            AUTH_COOKIE_NAME,
            component_key=_COOKIE_COMPONENT_KEY,
        )
