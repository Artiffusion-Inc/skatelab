"""Tests for is_staff flag on /v1/users/me driven by STAFF_EMAILS env."""

from __future__ import annotations

import pytest
from app.auth.staff import is_staff_email


# ---- Unit: pure helper ----
def test_is_staff_email_true_when_in_list():
    assert is_staff_email("boss@skatelab.ru", ["boss@skatelab.ru", "dev@skatelab.ru"]) is True


def test_is_staff_email_false_when_not_in_list():
    assert is_staff_email("regular@skatelab.ru", ["boss@skatelab.ru"]) is False


def test_is_staff_email_false_empty_list():
    assert is_staff_email("boss@skatelab.ru", []) is False


# ---- Config: StaffConfig parses comma-string ----
def test_staff_config_parses_comma_emails(monkeypatch):
    from app.config import StaffConfig

    monkeypatch.setenv("STAFF_EMAILS", "boss@skatelab.ru, dev@skatelab.ru")
    cfg = StaffConfig()
    assert cfg.emails == ["boss@skatelab.ru", "dev@skatelab.ru"]


def test_staff_config_empty_when_unset(monkeypatch):
    from app.config import StaffConfig

    monkeypatch.delenv("STAFF_EMAILS", raising=False)
    assert StaffConfig().emails == []


# ---- Integration: /v1/users/me returns is_staff field ----
@pytest.mark.anyio
async def test_me_returns_is_staff_field(client, auth_headers, monkeypatch):
    """get_me calls is_staff_email with get_settings().staff.emails."""
    from types import SimpleNamespace
    from unittest.mock import patch

    fake_settings = SimpleNamespace(staff=SimpleNamespace(emails=["boss@skatelab.ru"]))
    with patch("app.routes.users.get_settings", return_value=fake_settings):
        res = await client.get("/v1/users/me", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert "is_staff" in body
    assert isinstance(body["is_staff"], bool)
