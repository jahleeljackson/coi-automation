"""PDF generation wrapper used by Streamlit detail/approve flows."""

from __future__ import annotations

from typing import Any, Mapping

from acord.fill import fill_acord25


def generate_acord_pdf(
    request_data: Mapping[str, Any], agency_settings: Mapping[str, Any]
) -> tuple[bytes, str]:
    # Review UI fills current field values (including agent edits), not only
    # high-confidence extraction values.
    return fill_acord25(request_data, agency_settings, respect_confidence=False)
