"""Unit tests for signed auth session tokens."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from streamlit_app.auth import (
    AUTH_MAX_AGE_SECONDS,
    _normalize_cookie_value,
    issue_auth_token,
    parse_auth_token,
)


def _settings(secret: str = "test-session-secret") -> SimpleNamespace:
    return SimpleNamespace(session_secret=secret, airtable_api_key="")


class AuthTokenTests(unittest.TestCase):
    def test_roundtrip(self):
        with patch("streamlit_app.auth.get_settings", return_value=_settings()):
            token = issue_auth_token("recABC123")
            self.assertEqual(parse_auth_token(token), "recABC123")

    def test_rejects_tampered_token(self):
        with patch("streamlit_app.auth.get_settings", return_value=_settings()):
            token = issue_auth_token("recABC123")
            body, sig = token.split(".", 1)
            flipped = "A" if sig[0] != "A" else "B"
            tampered = f"{body}.{flipped}{sig[1:]}"
            self.assertIsNone(parse_auth_token(tampered))

    def test_rejects_expired_token(self):
        with patch("streamlit_app.auth.get_settings", return_value=_settings()):
            with patch("streamlit_app.auth.time.time", return_value=1_000_000):
                token = issue_auth_token("recABC123")
            with patch(
                "streamlit_app.auth.time.time",
                return_value=1_000_000 + AUTH_MAX_AGE_SECONDS + 1,
            ):
                self.assertIsNone(parse_auth_token(token))

    def test_rejects_garbage(self):
        self.assertIsNone(parse_auth_token(""))
        self.assertIsNone(parse_auth_token("not-a-token"))

    def test_normalize_quoted_cookie(self):
        self.assertEqual(_normalize_cookie_value('"abc.def"'), "abc.def")
        self.assertEqual(_normalize_cookie_value("abc.def"), "abc.def")


if __name__ == "__main__":
    unittest.main()
