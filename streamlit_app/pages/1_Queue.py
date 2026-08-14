"""Agent/admin request queue with detail pane, confidence cues, approve/deny."""

from __future__ import annotations

import base64
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests as http_requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_app.auth import require_auth
from streamlit_app.config import get_settings
from streamlit_app.utils.airtable_client import (
    get_agency_settings,
    get_request,
    list_requests,
    update_request,
)
from streamlit_app.utils.pdf_generator import generate_acord_pdf

st.set_page_config(page_title="COI Queue", layout="wide")
user = require_auth(allowed_roles=["agent", "admin"])

STATUSES = [
    "All",
    "New",
    "Pending",
    "In Review",
    "Clarification Needed",
    "Approved",
    "Rejected",
    "Completed",
]

EDITABLE_FIELDS = [
    "insured_client_name",
    "certificate_holder_name",
    "certificate_holder_address",
    "additional_insured",
    "waiver_of_subrogation",
    "coverage_types_requested",
    "specific_limits_requested",
    "needed_by",
    "notes_for_reviewer",
]


def _conf_label(field: str, record: dict) -> str:
    label = field.replace("_", " ").title()
    raw = record.get(f"{field}_confidence")
    try:
        conf = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        conf = None
    if conf is None:
        return label
    if conf <= 0.8:
        return f"{label}  (low confidence {conf:.2f} — verify)"
    return f"{label}  (confidence {conf:.2f})"


st.title("Request queue")
status_filter = st.selectbox("Filter by status", STATUSES, index=0)

try:
    rows = list_requests(None if status_filter == "All" else status_filter)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load requests from Airtable: {exc}")
    st.stop()

if not rows:
    st.info("No requests found.")
    st.stop()

# Compact queue table
st.dataframe(
    [
        {
            "insured": r.get("insured_client_name") or "",
            "holder": r.get("certificate_holder_name") or "",
            "status": r.get("status") or "",
            "needed_by": r.get("needed_by") or "",
            "overall_conf": r.get("extraction_confidence") or "",
            "id": r.get("id"),
        }
        for r in rows
    ],
    use_container_width=True,
    hide_index=True,
)

labels = [
    f"{r.get('status', '?')} | "
    f"{r.get('insured_client_name') or r.get('certificate_holder_name') or r.get('raw_email_subject') or '(untitled)'} | "
    f"{r.get('id')}"
    for r in rows
]
choice = st.selectbox(
    "Open request",
    options=list(range(len(rows))),
    format_func=lambda i: labels[i],
)
selected_id = rows[choice]["id"]

try:
    record = get_request(selected_id)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load request: {exc}")
    st.stop()

if not record:
    st.error("Request not found.")
    st.stop()

st.divider()
st.subheader(
    f"Detail — {record.get('insured_client_name') or record.get('raw_email_subject') or selected_id}"
)

if record.get("notes_for_reviewer"):
    st.warning(f"Reviewer notes: {record['notes_for_reviewer']}")

col_main, col_meta = st.columns([2, 1])

with col_meta:
    st.markdown("**Audit / meta**")
    st.write(
        {
            "id": record.get("id"),
            "status": record.get("status"),
            "requester_email": record.get("requester_email"),
            "extraction_confidence": record.get("extraction_confidence"),
            "prior_record_id": record.get("prior_record_id"),
            "raw_email_subject": record.get("raw_email_subject"),
            "raw_email_sender": record.get("raw_email_sender"),
            "gmail_thread_id": record.get("gmail_thread_id"),
            "approved_at": record.get("approved_at"),
            "pdf_version_hash": record.get("pdf_version_hash"),
        }
    )
    with st.expander("Raw email body"):
        st.text(record.get("raw_email_body") or "")
    with st.expander("Raw extraction JSON"):
        st.code(
            record.get("raw_extraction_json")
            or record.get("model_output_json")
            or "",
            language="json",
        )

with col_main:
    edited: dict = {"status": record.get("status") or "New"}
    with st.form("edit_request"):
        for field in EDITABLE_FIELDS:
            edited[field] = st.text_input(
                _conf_label(field, record),
                value=str(record.get(field) or ""),
            )
        opts = [s for s in STATUSES if s != "All"]
        current = record.get("status") or "New"
        idx = opts.index(current) if current in opts else 0
        edited["status"] = st.selectbox("Status", opts, index=idx)
        saved = st.form_submit_button("Save changes")
    if saved:
        payload = {k: v for k, v in edited.items()}
        if record.get("status") == "New" and payload.get("status") == "New":
            payload["status"] = "In Review"
        try:
            update_request(selected_id, payload)
            st.success("Saved.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Save failed: {exc}")

    st.markdown("**PDF**")
    agency = {}
    pdf_bytes = b""
    digest = ""
    try:
        agency = get_agency_settings()
        # Merge latest form values for PDF if present in session via record reload
        pdf_bytes, digest = generate_acord_pdf(record, agency)
        st.caption(f"pdf_version_hash: `{digest}`")
        st.download_button(
            "Download ACORD 25 PDF",
            data=pdf_bytes,
            file_name=f"acord25-{selected_id}.pdf",
            mime="application/pdf",
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"PDF preview unavailable: {exc}")

    st.markdown("**Actions**")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Deny", type="secondary"):
            try:
                update_request(selected_id, {"status": "Rejected"})
                st.success("Request rejected (no email sent).")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    with c2:
        if st.button("Approve", type="primary"):
            settings = get_settings()
            if not settings.n8n_approve_webhook_url:
                st.error("N8N_APPROVE_WEBHOOK_URL is not configured.")
            elif not pdf_bytes:
                st.error("PDF could not be generated; cannot approve.")
            else:
                try:
                    payload = {
                        "request_id": selected_id,
                        "requester_email": record.get("requester_email") or "",
                        "insured_name": record.get("insured_client_name") or "",
                        "subject": record.get("raw_email_subject") or "Certificate of Insurance",
                        "gmail_thread_id": record.get("gmail_thread_id") or "",
                        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                        "pdf_filename": f"acord25-{selected_id}.pdf",
                        "pdf_version_hash": digest,
                    }
                    resp = http_requests.post(
                        settings.n8n_approve_webhook_url,
                        json=payload,
                        timeout=60,
                    )
                    if not resp.ok:
                        st.error(
                            f"Approve webhook failed ({resp.status_code}): {resp.text[:500]}"
                        )
                    else:
                        update_request(
                            selected_id,
                            {
                                "status": "Approved",
                                "approved_at": datetime.now(timezone.utc).isoformat(),
                                "approved_by": [user["id"]],
                                "pdf_version_hash": digest,
                            },
                        )
                        st.success("Approved — Gmail draft with PDF should be created.")
                        st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Approve failed: {exc}")

st.sidebar.markdown(f"Signed in as **{user.get('email')}** ({user.get('role')})")
