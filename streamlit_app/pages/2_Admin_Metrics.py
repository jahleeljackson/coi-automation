"""Admin metrics dashboard (MVP formulas)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.auth import require_auth
from streamlit_app.utils.airtable_client import list_requests

st.set_page_config(page_title="Admin Metrics", layout="wide")
require_auth(allowed_roles=["admin"])

st.title("Admin metrics")

try:
    rows = list_requests()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load requests: {exc}")
    st.stop()

completed = [r for r in rows if (r.get("status") or "") == "Completed"]
approved = [r for r in rows if (r.get("status") or "") in {"Approved", "Completed"}]

hours_saved = (len(completed) * 15) / 60.0


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


durations = []
for r in approved:
    created = _parse_dt(r.get("created_at"))
    approved_at = _parse_dt(r.get("approved_at"))
    if created and approved_at:
        durations.append((approved_at - created).total_seconds() / 60.0)

avg_tta = sum(durations) / len(durations) if durations else None

c1, c2, c3 = st.columns(3)
c1.metric("Request count", len(rows))
c2.metric(
    "Avg time to approve (min)",
    f"{avg_tta:.1f}" if avg_tta is not None else "n/a",
)
c3.metric("Estimated hours saved", f"{hours_saved:.1f}")
st.caption("Hours saved = completed COIs × 15 minutes.")
