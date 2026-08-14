"""Basic tests for ACORD 25 filler (no network)."""

from __future__ import annotations

import unittest
from io import BytesIO

from pypdf import PdfReader

from acord.fill import CONFIDENCE_THRESHOLD, fill_acord25, pdf_sha256


AGENCY = {
    "producer_name": "Cassian Insurance Agency",
    "producer_address_line1": "100 Main Street",
    "producer_city": "Richmond",
    "producer_state": "VA",
    "producer_postal": "23219",
    "producer_contact_name": "Alex Agent",
    "producer_phone": "804-555-0100",
    "producer_email": "alex@example.com",
}


class FillAcord25Tests(unittest.TestCase):
    def test_producer_and_high_confidence_fields(self):
        request = {
            "insured_client_name": "Acme Contracting LLC",
            "insured_client_name_confidence": 0.95,
            "certificate_holder_name": "Riverside Property Management LLC",
            "certificate_holder_name_confidence": 0.95,
            "certificate_holder_address": (
                "1200 Riverside Drive, Richmond, VA 23219"
            ),
            "certificate_holder_address_confidence": 0.95,
            "additional_insured": "Riverside Property Management LLC",
            "additional_insured_confidence": 0.9,
            "waiver_of_subrogation": "Riverside Property Management LLC",
            "waiver_of_subrogation_confidence": 0.9,
        }
        pdf_bytes, digest = fill_acord25(request, AGENCY)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertEqual(digest, pdf_sha256(pdf_bytes))
        self.assertEqual(len(digest), 64)

        fields = PdfReader(BytesIO(pdf_bytes)).get_fields() or {}
        self.assertEqual(
            str(fields["Producer_FullName_A"].get("/V")),
            "Cassian Insurance Agency",
        )
        self.assertEqual(
            str(fields["NamedInsured_FullName_A"].get("/V")),
            "Acme Contracting LLC",
        )
        self.assertEqual(
            str(fields["CertificateHolder_FullName_A"].get("/V")),
            "Riverside Property Management LLC",
        )
        self.assertEqual(
            str(fields["CertificateHolder_MailingAddress_CityName_A"].get("/V")),
            "Richmond",
        )

    def test_low_confidence_left_blank(self):
        request = {
            "insured_client_name": "Should Not Appear",
            "insured_client_name_confidence": CONFIDENCE_THRESHOLD,  # not >
            "certificate_holder_name": "Also Blank",
            "certificate_holder_name_confidence": 0.5,
        }
        pdf_bytes, _ = fill_acord25(request, AGENCY)
        fields = PdfReader(BytesIO(pdf_bytes)).get_fields() or {}
        insured = fields["NamedInsured_FullName_A"].get("/V")
        holder = fields["CertificateHolder_FullName_A"].get("/V")
        self.assertTrue(insured in (None, ""))
        self.assertTrue(holder in (None, ""))

    def test_coverage_grids_not_autofilled(self):
        request = {
            "specific_limits_requested": "1,000,000",
            "specific_limits_requested_confidence": 0.99,
            "coverage_types_requested": "General Liability",
            "coverage_types_requested_confidence": 0.99,
        }
        pdf_bytes, _ = fill_acord25(request, AGENCY)
        fields = PdfReader(BytesIO(pdf_bytes)).get_fields() or {}
        # Sample policy/limit fields should remain empty
        sample = [
            "GeneralLiability_EachOccurrenceLimitAmount_A",
            "Insurer_FullName_A",
            "GeneralLiability_PolicyNumberIdentifier_A",
        ]
        for name in sample:
            if name not in fields:
                continue
            val = fields[name].get("/V")
            self.assertTrue(val in (None, ""), msg=f"{name} should be blank")


if __name__ == "__main__":
    unittest.main()
