"""Fill a real ACORD 25 AcroForm PDF for COI MVP review/approve flows."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject

CONFIDENCE_THRESHOLD = 0.8

DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent / ".cursor" / "acord25.pdf"
)

# AcroForm field names from .cursor/acord25.pdf (ACORD 0025 2016-03)
PRODUCER_FIELDS = {
    "name": "Producer_FullName_A",
    "address_line1": "Producer_MailingAddress_LineOne_A",
    "address_line2": "Producer_MailingAddress_LineTwo_A",
    "city": "Producer_MailingAddress_CityName_A",
    "state": "Producer_MailingAddress_StateOrProvinceCode_A",
    "postal": "Producer_MailingAddress_PostalCode_A",
    "contact": "Producer_ContactPerson_FullName_A",
    "phone": "Producer_ContactPerson_PhoneNumber_A",
    "fax": "Producer_FaxNumber_A",
    "email": "Producer_ContactPerson_EmailAddress_A",
}

HOLDER_FIELDS = {
    "name": "CertificateHolder_FullName_A",
    "address_line1": "CertificateHolder_MailingAddress_LineOne_A",
    "address_line2": "CertificateHolder_MailingAddress_LineTwo_A",
    "city": "CertificateHolder_MailingAddress_CityName_A",
    "state": "CertificateHolder_MailingAddress_StateOrProvinceCode_A",
    "postal": "CertificateHolder_MailingAddress_PostalCode_A",
}

# Y/N style codes on this AcroForm edition
AI_CODE_FIELDS = [
    "CertificateOfInsurance_GeneralLiability_AdditionalInsuredCode_A",
    "CertificateOfInsurance_AutomobileLiability_AdditionalInsuredCode_A",
    "CertificateOfInsurance_ExcessLiability_AdditionalInsuredCode_A",
]

WAIVER_CODE_FIELDS = [
    "Policy_GeneralLiability_SubrogationWaivedCode_A",
    "Policy_AutomobileLiability_SubrogationWaivedCode_A",
    "Policy_ExcessLiability_SubrogationWaivedCode_A",
    "Policy_WorkersCompensation_SubrogationWaivedCode_A",
]

REMARKS_FIELD = "CertificateOfLiabilityInsurance_ACORDForm_RemarkText_A"
COMPLETION_DATE_FIELD = "Form_CompletionDate_A"
NAMED_INSURED_FIELD = "NamedInsured_FullName_A"


def pdf_sha256(pdf_bytes: bytes) -> str:
    """Return hex SHA-256 of PDF bytes for audit (`pdf_version_hash`)."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def _truthy_request(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return False
    if text in {"n", "no", "false", "0", "none", "n/a", "na"}:
        return False
    return True


def _confidence(request_data: Mapping[str, Any], field: str) -> float:
    raw = request_data.get(f"{field}_confidence")
    if raw is None:
        # If no score provided, treat present non-empty values as eligible
        # only when caller already gated; default to 0 to be safe.
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _eligible(request_data: Mapping[str, Any], field: str) -> bool:
    value = request_data.get(field)
    if value is None or str(value).strip() == "":
        return False
    # Values arriving from n8n Shape Fields are already blanked at ≤0.8.
    # Still enforce threshold when confidence is present.
    if f"{field}_confidence" in request_data:
        return _confidence(request_data, field) > CONFIDENCE_THRESHOLD
    return True


def _parse_us_address(address: str) -> dict[str, str]:
    """Best-effort split of a single-line US-ish address into ACORD parts."""
    result = {
        "address_line1": "",
        "address_line2": "",
        "city": "",
        "state": "",
        "postal": "",
    }
    if not address or not str(address).strip():
        return result

    text = re.sub(r"\s+", " ", str(address).strip())
    # Pattern: street, city, ST ZIP
    m = re.match(
        r"^(?P<line1>.+?),\s*(?P<city>[^,]+),\s*"
        r"(?P<state>[A-Za-z]{2})\s+(?P<postal>\d{5}(?:-\d{4})?)$",
        text,
    )
    if m:
        result.update({k: v.strip() for k, v in m.groupdict().items()})
        return result

    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) >= 1:
        result["address_line1"] = parts[0]
    if len(parts) >= 2:
        # last part may be "City ST ZIP" or just city; middle may be line2
        tail = parts[-1]
        m2 = re.match(
            r"^(?P<city>.+?)\s+(?P<state>[A-Za-z]{2})\s+(?P<postal>\d{5}(?:-\d{4})?)$",
            tail,
        )
        if m2:
            result["city"] = m2.group("city").strip()
            result["state"] = m2.group("state").strip()
            result["postal"] = m2.group("postal").strip()
            if len(parts) == 3:
                result["address_line2"] = parts[1]
            elif len(parts) > 3:
                result["address_line2"] = ", ".join(parts[1:-1])
        else:
            if len(parts) >= 2:
                result["city"] = parts[1]
            if len(parts) >= 3:
                result["address_line2"] = ", ".join(parts[1:])
    return result


def _set_need_appearances(writer: PdfWriter) -> None:
    if writer._root_object.get("/AcroForm") is None:  # noqa: SLF001
        return
    writer._root_object["/AcroForm"].update(  # noqa: SLF001
        {NameObject("/NeedAppearances"): BooleanObject(True)}
    )


def fill_acord25(
    request_data: Mapping[str, Any],
    agency_settings: Mapping[str, Any],
    *,
    template_path: str | Path | None = None,
    completion_date: date | None = None,
) -> tuple[bytes, str]:
    """Fill ACORD 25 per MVP autofill policy.

    Always fills producer block from ``agency_settings`` and completion date.
    Fills insured / holder / AI / waiver / remarks from ``request_data`` when
    values are present and confidence (if provided) is > 0.8.

    Leaves policy numbers, limits, insurers, coverage grids, and policy dates blank.

    Returns ``(pdf_bytes, sha256_hex)``.
    """
    template = Path(template_path) if template_path else DEFAULT_TEMPLATE
    if not template.exists():
        raise FileNotFoundError(f"ACORD template not found: {template}")

    reader = PdfReader(str(template))
    writer = PdfWriter()
    writer.append(reader)

    values: dict[str, str] = {}

    # --- Always: completion date + producer block ---
    when = completion_date or date.today()
    values[COMPLETION_DATE_FIELD] = when.strftime("%m/%d/%Y")

    producer_map = {
        PRODUCER_FIELDS["name"]: agency_settings.get("producer_name", ""),
        PRODUCER_FIELDS["address_line1"]: agency_settings.get(
            "producer_address_line1",
            agency_settings.get("producer_address", ""),
        ),
        PRODUCER_FIELDS["address_line2"]: agency_settings.get(
            "producer_address_line2", ""
        ),
        PRODUCER_FIELDS["city"]: agency_settings.get("producer_city", ""),
        PRODUCER_FIELDS["state"]: agency_settings.get("producer_state", ""),
        PRODUCER_FIELDS["postal"]: agency_settings.get("producer_postal", ""),
        PRODUCER_FIELDS["contact"]: agency_settings.get(
            "producer_contact_name", ""
        ),
        PRODUCER_FIELDS["phone"]: agency_settings.get("producer_phone", ""),
        PRODUCER_FIELDS["fax"]: agency_settings.get("producer_fax", ""),
        PRODUCER_FIELDS["email"]: agency_settings.get("producer_email", ""),
    }
    for k, v in producer_map.items():
        if v is not None and str(v).strip() != "":
            values[k] = str(v).strip()

    # --- Conditional autofill ---
    if _eligible(request_data, "insured_client_name"):
        values[NAMED_INSURED_FIELD] = str(
            request_data["insured_client_name"]
        ).strip()

    if _eligible(request_data, "certificate_holder_name"):
        values[HOLDER_FIELDS["name"]] = str(
            request_data["certificate_holder_name"]
        ).strip()

    if _eligible(request_data, "certificate_holder_address"):
        parsed = _parse_us_address(
            str(request_data["certificate_holder_address"])
        )
        for key, field_name in HOLDER_FIELDS.items():
            if key == "name":
                continue
            if parsed.get(key):
                values[field_name] = parsed[key]

    if _eligible(request_data, "additional_insured") and _truthy_request(
        request_data.get("additional_insured")
    ):
        for field_name in AI_CODE_FIELDS:
            values[field_name] = "Y"

    if _eligible(request_data, "waiver_of_subrogation") and _truthy_request(
        request_data.get("waiver_of_subrogation")
    ):
        for field_name in WAIVER_CODE_FIELDS:
            values[field_name] = "Y"

    remark_parts: list[str] = []
    if _eligible(request_data, "additional_insured") and _truthy_request(
        request_data.get("additional_insured")
    ):
        remark_parts.append(
            f"Additional Insured: {request_data['additional_insured']}"
        )
    if _eligible(request_data, "waiver_of_subrogation") and _truthy_request(
        request_data.get("waiver_of_subrogation")
    ):
        remark_parts.append(
            f"Waiver of Subrogation: {request_data['waiver_of_subrogation']}"
        )
    notes = request_data.get("notes_for_reviewer") or request_data.get(
        "description_of_operations"
    )
    # Description/notes: include when explicitly provided as description;
    # do not dump internal reviewer notes onto the certificate by default.
    if request_data.get("description_of_operations"):
        if _eligible(request_data, "description_of_operations") or (
            "description_of_operations_confidence" not in request_data
            and str(request_data.get("description_of_operations")).strip()
        ):
            remark_parts.append(str(request_data["description_of_operations"]).strip())
    elif notes and request_data.get("include_notes_on_certificate"):
        remark_parts.append(str(notes).strip())

    if remark_parts:
        values[REMARKS_FIELD] = "\n".join(remark_parts)

    # Apply values to all pages
    if values:
        for page in writer.pages:
            writer.update_page_form_field_values(page, values)

    _set_need_appearances(writer)

    buf = BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()
    return pdf_bytes, pdf_sha256(pdf_bytes)
