"""Browser cookie read/write via Streamlit Components v2.

CCv2 runs in the app page (not an iframe), so ``document.cookie`` actually
persists across reloads. extra-streamlit-components cannot do that reliably.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

_COOKIE_JS = """
function decodeCookiePart(value) {
  try {
    return decodeURIComponent(value);
  } catch (_error) {
    return value;
  }
}

function parseCookies() {
  const snapshot = {};
  const rawCookie = document.cookie || "";
  if (!rawCookie.trim()) {
    return snapshot;
  }
  rawCookie.split(";").forEach((part) => {
    const trimmed = part.trim();
    if (!trimmed) {
      return;
    }
    const separatorIndex = trimmed.indexOf("=");
    const rawName =
      separatorIndex >= 0 ? trimmed.slice(0, separatorIndex) : trimmed;
    const rawValue =
      separatorIndex >= 0 ? trimmed.slice(separatorIndex + 1) : "";
    snapshot[decodeCookiePart(rawName)] = decodeCookiePart(rawValue);
  });
  return snapshot;
}

function isLocalhost() {
  return ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
}

function shouldUseSecureAttribute(secure) {
  if (!secure) {
    return false;
  }
  if (window.location.protocol === "https:") {
    return true;
  }
  return !isLocalhost();
}

function buildCookieAttributes(options, includeExpiryReset) {
  const attributes = [];
  const normalizedOptions = options ?? {};
  if (includeExpiryReset) {
    attributes.push("expires=Thu, 01 Jan 1970 00:00:00 GMT");
    attributes.push("max-age=0");
  } else {
    if (normalizedOptions.max_age !== undefined && normalizedOptions.max_age !== null) {
      attributes.push(`max-age=${normalizedOptions.max_age}`);
    }
    if (normalizedOptions.expires) {
      attributes.push(
        `expires=${new Date(normalizedOptions.expires).toUTCString()}`
      );
    }
  }
  if (normalizedOptions.path) {
    attributes.push(`path=${normalizedOptions.path}`);
  }
  if (normalizedOptions.domain) {
    attributes.push(`domain=${normalizedOptions.domain}`);
  }
  if (shouldUseSecureAttribute(normalizedOptions.secure)) {
    attributes.push("secure");
  }
  if (normalizedOptions.samesite) {
    attributes.push(`samesite=${normalizedOptions.samesite}`);
  }
  return attributes;
}

function setCookie(name, value, options) {
  const encodedName = encodeURIComponent(name);
  const encodedValue = encodeURIComponent(value);
  const attributes = buildCookieAttributes(options, false);
  document.cookie = [`${encodedName}=${encodedValue}`, ...attributes].join("; ");
}

function deleteCookie(name, options) {
  const encodedName = encodeURIComponent(name);
  const attributes = buildCookieAttributes(options, true);
  document.cookie = [`${encodedName}=`, ...attributes].join("; ");
}

export default function (component) {
  const { data, setStateValue } = component;
  const operations = data?.operations ?? [];
  let lastProcessedOperationId = data?.last_processed_operation_id ?? 0;
  operations.forEach((operation) => {
    if (operation.type === "set") {
      setCookie(operation.name, operation.value, operation.options);
    } else if (operation.type === "delete") {
      deleteCookie(operation.name, operation.options);
    }
    lastProcessedOperationId = Math.max(
      lastProcessedOperationId,
      operation.id ?? lastProcessedOperationId
    );
  });
  const snapshot = parseCookies();
  const sortedEntries = Object.entries(snapshot).sort(([left], [right]) =>
    left.localeCompare(right)
  );
  setStateValue("ready", true);
  setStateValue("snapshot_json", JSON.stringify(Object.fromEntries(sortedEntries)));
  setStateValue("last_processed_operation_id", lastProcessedOperationId);
  return () => {};
}
"""

_COMPONENT = None
_RESULTS: dict[str, BrowserCookies] = {}


def _component():
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = st.components.v2.component(
            "coi_mvp.browser_cookies",
            html=" ",
            css=":host { display: none !important; height: 0 !important; overflow: hidden !important; }",
            js=_COOKIE_JS,
            isolate_styles=True,
        )
    return _COMPONENT


def _store_key(component_key: str) -> str:
    return f"{component_key}__cookie_ops"


def cookie_ops_store(component_key: str) -> dict[str, Any]:
    return st.session_state.setdefault(
        _store_key(component_key),
        {"next_operation_id": 1, "pending_operations": []},
    )


def queue_cookie_set(
    name: str,
    value: str,
    *,
    component_key: str,
    max_age: int,
    path: str = "/",
    secure: bool = True,
    samesite: Literal["strict", "lax", "none"] = "lax",
) -> None:
    store = cookie_ops_store(component_key)
    operation_id = store["next_operation_id"]
    store["next_operation_id"] += 1
    store["pending_operations"].append(
        {
            "id": operation_id,
            "type": "set",
            "name": name,
            "value": value,
            "options": {
                "max_age": max_age,
                "path": path,
                "secure": secure,
                "samesite": samesite,
            },
        }
    )


def queue_cookie_delete(
    name: str,
    *,
    component_key: str,
    path: str = "/",
    secure: bool = True,
    samesite: Literal["strict", "lax", "none"] = "lax",
) -> None:
    store = cookie_ops_store(component_key)
    operation_id = store["next_operation_id"]
    store["next_operation_id"] += 1
    store["pending_operations"].append(
        {
            "id": operation_id,
            "type": "delete",
            "name": name,
            "value": None,
            "options": {
                "path": path,
                "secure": secure,
                "samesite": samesite,
            },
        }
    )


class BrowserCookies:
    def __init__(self, snapshot: dict[str, str], ready: bool) -> None:
        self._snapshot = snapshot
        self._ready = ready

    def ready(self) -> bool:
        return self._ready

    def get(self, name: str) -> str | None:
        value = self._snapshot.get(name)
        return value if isinstance(value, str) and value else None


def sync_browser_cookies(key: str = "coi_cookies") -> BrowserCookies:
    """Mount the cookie component so queued writes run in the browser.

    Call this once per script run, after any ``queue_cookie_*`` calls.
    Safe to call again in the same run; later calls reuse the mounted result.
    """
    ctx = get_script_run_ctx()
    already_mounted = bool(
        ctx is not None and key in ctx.shared.widget_user_keys_this_run
    )
    if already_mounted and key in _RESULTS:
        return _RESULTS[key]

    store = cookie_ops_store(key)
    component_state = st.session_state.get(key, {})
    last_processed_operation_id = component_state.get("last_processed_operation_id", 0)
    if last_processed_operation_id:
        store["pending_operations"] = [
            operation
            for operation in store["pending_operations"]
            if operation["id"] > last_processed_operation_id
        ]

    default_snapshot_json = component_state.get("snapshot_json", "{}")
    default_ready = component_state.get("ready", False)
    result = _component()(
        key=key,
        data={
            "operations": store["pending_operations"],
            "last_processed_operation_id": last_processed_operation_id,
        },
        default={
            "ready": default_ready,
            "snapshot_json": default_snapshot_json,
            "last_processed_operation_id": last_processed_operation_id,
        },
        on_ready_change=lambda: None,
        on_snapshot_json_change=lambda: None,
        on_last_processed_operation_id_change=lambda: None,
        width="content",
        height="content",
    )
    try:
        snapshot = json.loads(result.snapshot_json or "{}")
    except (TypeError, json.JSONDecodeError):
        snapshot = {}
    if not isinstance(snapshot, dict):
        snapshot = {}
    cookies = BrowserCookies(
        snapshot={str(k): str(v) for k, v in snapshot.items()},
        ready=bool(result.ready),
    )
    _RESULTS[key] = cookies
    return cookies
