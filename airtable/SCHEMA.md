# Airtable Schema — COI MVP

Create these tables in the agency's Airtable base (system of record). After creating fields, re-import/update the n8n Airtable node URL mappings as needed.

**Setup checklist**
1. Create base (or use existing COI base).
2. Create tables `Requests`, `Users`, `AgencySettings` with fields below.
3. Link `Requests.prior_record_id` → `Requests`.
4. Link `Requests.approved_by` → `Users`.
5. Add one seed admin row in `Users` (set `password_hash` from the Streamlit app's hasher once built).
6. Add one row in `AgencySettings` with producer/agency ACORD block values.
7. In n8n: import `COI Request MVP - Error Alerts.json`, activate it, then set the main workflow's **Error Workflow** to that workflow.
8. Confirm OpenAI and Airtable nodes have retryOnFail / maxTries=3 (shipped in `COI Request MVP.json`).

---

## Table: Requests

| Field | Type | Notes |
|-------|------|--------|
| id | Autonumber | Airtable record id also used via API |
| requester_email | Email | |
| insured_client_name | Single line text | Blank if confidence ≤ 0.8 |
| certificate_holder_name | Single line text | |
| certificate_holder_address | Long text | |
| additional_insured | Long text | |
| waiver_of_subrogation | Single line text | |
| coverage_types_requested | Long text | |
| specific_limits_requested | Long text | |
| needed_by | Date | Optional; may be empty string from intake |
| notes_for_reviewer | Long text | |
| status | Single select | `New`, `Pending`, `In Review`, `Clarification Needed`, `Approved`, `Rejected`, `Completed` |
| prior_record_id | Link to Requests | Reopen lineage; empty on first intake |
| raw_email_subject | Single line text | Audit |
| raw_email_sender | Email | Audit |
| raw_email_body | Long text | Audit |
| raw_email_message_id | Single line text | Gmail message id |
| gmail_thread_id | Single line text | |
| raw_extraction_json | Long text | Full model JSON (per-field confidence) |
| requester_email_confidence | Number | 0–1 |
| insured_client_name_confidence | Number | 0–1 |
| certificate_holder_name_confidence | Number | 0–1 |
| certificate_holder_address_confidence | Number | 0–1 |
| additional_insured_confidence | Number | 0–1 |
| waiver_of_subrogation_confidence | Number | 0–1 |
| coverage_types_requested_confidence | Number | 0–1 |
| specific_limits_requested_confidence | Number | 0–1 |
| needed_by_confidence | Number | 0–1 |
| extraction_confidence | Number | overall_confidence (display) |
| created_at | Created time | |
| updated_at | Last modified time | |
| approved_at | Date time | Set on approve |
| approved_by | Link to Users | Set on approve |
| pdf_version_hash | Single line text | Hash/version of generated PDF |
| model_output_json | Long text | Alias/compat with intake node; prefer `raw_extraction_json` |

---

## Table: Users

| Field | Type | Notes |
|-------|------|--------|
| id | Autonumber | |
| email | Email | Unique |
| password_hash | Single line text | Never store plaintext |
| role | Single select | `agent`, `admin` |
| name | Single line text | |
| is_active | Checkbox | Default true |
| created_at | Created time | |
| last_login | Date time | |

---

## Table: AgencySettings

Single logical row per install (producer block for ACORD 25).

| Field | Type | Notes |
|-------|------|--------|
| producer_name | Single line text | Producer_FullName_A |
| producer_address_line1 | Single line text | |
| producer_address_line2 | Single line text | |
| producer_city | Single line text | |
| producer_state | Single line text | |
| producer_postal | Single line text | |
| producer_phone | Phone | |
| producer_fax | Phone | |
| producer_email | Email | |
| producer_contact_name | Single line text | |

If you prefer a single `producer_address` long text field for MVP, that is acceptable; the Streamlit filler can split or map as configured.

---

## Status transitions (operator-facing)

- Intake creates `New`
- Agent opens → `In Review`
- Waiting on missing info → `Clarification Needed`
- Approve → `Approved` (+ Gmail draft with PDF via webhook)
- Deny → `Rejected` (no email)
- After human send / close → `Completed` (counts toward hours-saved metric)

---

## Local app run (after schema + seed user)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill Airtable + N8N_APPROVE_WEBHOOK_URL
.venv/bin/python scripts/hash_password.py 'your-temp-password'
# paste hash into Airtable Users.password_hash for an admin row
streamlit run streamlit_app/app.py
```

Import into n8n (self-hosted):
- `COI Request MVP.json` (intake)
- `COI Request MVP - Error Alerts.json` (set as Error Workflow on intake)
- `COI Request MVP - Approve Webhook.json` (activate; copy Production URL into `.env`)
