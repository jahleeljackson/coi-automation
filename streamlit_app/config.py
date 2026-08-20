"""Streamlit app configuration from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    airtable_api_key: str
    airtable_base_id: str
    requests_table: str = "Requests"
    users_table: str = "Users"
    agency_settings_table: str = "AgencySettings"
    n8n_approve_webhook_url: str = ""
    session_secret: str = ""


def _normalize_airtable_base_id(raw: str) -> str:
    """Accept app ID or accidental base/table/view path; keep only appXXXX."""
    value = (raw or "").strip()
    if not value:
        return ""
    # Support pasted airtable.com URLs or app/tbl/viw paths from the UI.
    if "airtable.com" in value:
        parts = value.split("/")
        for part in parts:
            if part.startswith("app"):
                return part
    if "/" in value:
        first = value.split("/")[0].strip()
        if first.startswith("app"):
            return first
    return value


def get_settings() -> Settings:
    api_key_raw = os.getenv("AIRTABLE_API_KEY") or os.getenv("AIRTABLE_PAT") or ""
    api_key = api_key_raw.strip().strip('"').strip("'")
    base_id = _normalize_airtable_base_id(os.getenv("AIRTABLE_BASE_ID") or "")
    return Settings(
        airtable_api_key=api_key,
        airtable_base_id=base_id,
        requests_table=os.getenv("AIRTABLE_REQUESTS_TABLE", "Requests"),
        users_table=os.getenv("AIRTABLE_USERS_TABLE", "Users"),
        agency_settings_table=os.getenv(
            "AIRTABLE_AGENCY_SETTINGS_TABLE", "AgencySettings"
        ),
        n8n_approve_webhook_url=os.getenv("N8N_APPROVE_WEBHOOK_URL", ""),
        session_secret=os.getenv("SESSION_SECRET", "").strip(),
    )
