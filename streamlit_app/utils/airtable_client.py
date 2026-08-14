"""Thin Airtable client for COI MVP Streamlit app."""

from __future__ import annotations

from typing import Any

from pyairtable import Api, Table

from streamlit_app.config import Settings, get_settings


def _table(settings: Settings, name: str) -> Table:
    if not settings.airtable_api_key or not settings.airtable_base_id:
        raise RuntimeError(
            "AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in the environment."
        )
    key = settings.airtable_api_key
    if key.startswith("pat") and (len(key) < 40 or "." not in key):
        raise RuntimeError(
            "AIRTABLE_API_KEY looks truncated. Paste the full personal access token "
            "from Airtable (format patXXXX....YYYY, typically 80+ characters)."
        )
    return Api(settings.airtable_api_key).table(settings.airtable_base_id, name)


def users_table(settings: Settings | None = None) -> Table:
    settings = settings or get_settings()
    return _table(settings, settings.users_table)


def requests_table(settings: Settings | None = None) -> Table:
    settings = settings or get_settings()
    return _table(settings, settings.requests_table)


def agency_settings_table(settings: Settings | None = None) -> Table:
    settings = settings or get_settings()
    return _table(settings, settings.agency_settings_table)


def get_user_by_email(email: str, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    # Escape single quotes for Airtable formulas
    safe = email.replace("'", "\\'")
    try:
        records = users_table(settings).all(
            formula=f"LOWER({{email}}) = LOWER('{safe}')",
            max_records=1,
        )
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        if "403" in err or "INVALID_PERMISSIONS" in err:
            raise RuntimeError(
                "Airtable returned 403 for the Users table. Your token can see the base, "
                "but it is missing data access. Edit the personal access token and enable "
                "scopes data.records:read and data.records:write for this base, then restart Streamlit."
            ) from exc
        raise
    if not records:
        return None
    rec = records[0]
    fields = dict(rec.get("fields") or {})
    fields["id"] = rec["id"]
    return fields


def list_users(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    out: list[dict[str, Any]] = []
    for rec in users_table(settings).all():
        fields = dict(rec.get("fields") or {})
        fields["id"] = rec["id"]
        out.append(fields)
    return out


def get_agency_settings(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    records = agency_settings_table(settings).all(max_records=1)
    if not records:
        return {}
    fields = dict(records[0].get("fields") or {})
    fields["id"] = records[0]["id"]
    return fields


def update_agency_settings(
    record_id: str, fields: dict[str, Any], settings: Settings | None = None
) -> dict[str, Any]:
    settings = settings or get_settings()
    rec = agency_settings_table(settings).update(record_id, fields)
    out = dict(rec.get("fields") or {})
    out["id"] = rec["id"]
    return out


def list_requests(
    status: str | None = None, settings: Settings | None = None
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    kwargs: dict[str, Any] = {"sort": ["-created_at"]}
    if status and status != "All":
        safe = status.replace("'", "\\'")
        kwargs["formula"] = f"{{status}} = '{safe}'"
    out: list[dict[str, Any]] = []
    try:
        records = requests_table(settings).all(**kwargs)
    except Exception:
        # created_at sort may fail before schema exists; fall back unsorted
        kwargs.pop("sort", None)
        records = requests_table(settings).all(**kwargs)
    for rec in records:
        fields = dict(rec.get("fields") or {})
        fields["id"] = rec["id"]
        out.append(fields)
    return out


def get_request(record_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    rec = requests_table(settings).get(record_id)
    if not rec:
        return None
    fields = dict(rec.get("fields") or {})
    fields["id"] = rec["id"]
    return fields


def update_request(
    record_id: str, fields: dict[str, Any], settings: Settings | None = None
) -> dict[str, Any]:
    settings = settings or get_settings()
    rec = requests_table(settings).update(record_id, fields)
    out = dict(rec.get("fields") or {})
    out["id"] = rec["id"]
    return out


def create_user(fields: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    rec = users_table(settings).create(fields)
    out = dict(rec.get("fields") or {})
    out["id"] = rec["id"]
    return out


def update_user(
    record_id: str, fields: dict[str, Any], settings: Settings | None = None
) -> dict[str, Any]:
    settings = settings or get_settings()
    rec = users_table(settings).update(record_id, fields)
    out = dict(rec.get("fields") or {})
    out["id"] = rec["id"]
    return out
