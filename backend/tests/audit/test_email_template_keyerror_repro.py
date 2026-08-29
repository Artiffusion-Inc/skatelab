"""Regression test for #640 — email _get_template_id KeyError on unknown type.

Bug: `_get_template_id` (email.py:42-44) indexes `self.TEMPLATES[email_type]`
without .get(). Unknown `email_type` raises KeyError. The callers wrap
`resend.Emails.send` in try/except but call `_get_template_id` BEFORE the
try block — KeyError propagates to the route handler, returning 500.

Fix: use `.get()` with None return, callers return None early.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.email import EmailService

_SRC_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "services" / "email.py"


def _make_svc() -> EmailService:
    with patch("app.services.email.get_settings") as mock_get:
        settings = MagicMock()
        settings.resend.api_key.get_secret_value.return_value = "test"
        settings.resend.from_email = "noreply@test.ru"
        settings.resend.from_name = "Test"
        mock_get.return_value = settings
        return EmailService()


def test_email_source_guards_unknown_template_type():
    """Source must guard against unknown email_type (#640)."""
    src = _SRC_FILE.read_text(encoding="utf-8")
    assert "#640" in src, (
        "BUG #640: email.py has no #640 reference — missing guard for "
        "unknown email_type in _get_template_id."
    )


def test_get_template_id_unknown_type_returns_none():
    """_get_template_id must return None for unknown email_type, not raise KeyError."""
    svc = _make_svc()
    result = svc._get_template_id("nonexistent_type", "ru")
    assert result is None


def test_get_template_id_known_type_still_works():
    """Known email_type still returns correct template ID (no regression)."""
    svc = _make_svc()
    assert svc._get_template_id("password_reset", "ru") == "password-reset-ru"
    assert svc._get_template_id("password_reset", "en") == "password-reset-en"
    assert svc._get_template_id("password_reset", "fr") == "password-reset-en"


async def test_send_password_reset_early_return_on_unknown_template():
    """send_password_reset returns None when _get_template_id returns None (#640)."""
    svc = _make_svc()
    with patch.object(svc, "_get_template_id", return_value=None):
        result = await svc.send_password_reset("x@test.ru", "tok", "ru")
    assert result is None


async def test_send_email_verification_early_return_on_unknown_template():
    """send_email_verification returns None when _get_template_id returns None (#640)."""
    svc = _make_svc()
    with patch.object(svc, "_get_template_id", return_value=None):
        result = await svc.send_email_verification("x@test.ru", "tok", "ru")
    assert result is None


async def test_send_coaching_invite_early_return_on_unknown_template():
    """send_coaching_invite returns None when _get_template_id returns None (#640)."""
    svc = _make_svc()
    with patch.object(svc, "_get_template_id", return_value=None):
        result = await svc.send_coaching_invite("x@test.ru", "Coach", "coaching", "ru")
    assert result is None
