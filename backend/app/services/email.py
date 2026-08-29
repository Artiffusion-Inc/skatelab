"""Email service using Resend Hosted Templates."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import resend
from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """Send transactional emails via Resend Hosted Templates.

    Templates are stored on Resend and referenced by alias.
    Python sends template_id + variables — Resend renders and delivers.
    """

    TEMPLATES: ClassVar[dict[str, dict[str, str]]] = {
        "password_reset": {
            "ru": "password-reset-ru",
            "en": "password-reset-en",
        },
        "email_verification": {
            "ru": "email-verification-ru",
            "en": "email-verification-en",
        },
        "coaching_invite": {
            "ru": "coaching-invite-ru",
            "en": "coaching-invite-en",
        },
    }

    def __init__(self) -> None:
        settings = get_settings()
        resend.api_key = settings.resend.api_key.get_secret_value()
        self.from_email = settings.resend.from_email
        self.from_name = settings.resend.from_name

    def _get_template_id(self, email_type: str, locale: str) -> str | None:
        # #640: unknown email_type must return None, not raise KeyError.
        locale = locale if locale in ("ru", "en") else "en"
        template = self.TEMPLATES.get(email_type)
        if template is None:
            logger.warning("Unknown email_type %r; no template", email_type)
            return None
        return template[locale]

    def _from_header(self) -> str:
        return f"{self.from_name} <{self.from_email}>"

    async def send_password_reset(self, to: str, token: str, locale: str = "ru") -> str | None:
        """Send password reset email. Returns Resend email ID or None on failure."""
        template_id = self._get_template_id("password_reset", locale)
        if template_id is None:
            return None
        settings = get_settings()
        reset_url = settings.resend.reset_url_template.format(token=token)
        try:
            params: dict[str, Any] = {
                "from": self._from_header(),
                "to": [to],
                "template": {
                    "id": template_id,
                    "variables": {"RESET_URL": reset_url},
                },
            }
            email = resend.Emails.send(params)  # type: ignore[arg-type]
            return str(email["id"])
        except Exception:
            logger.exception("Failed to send password reset email to %s", to)
            return None

    async def send_email_verification(self, to: str, token: str, locale: str = "ru") -> str | None:
        """Send email verification. Returns Resend email ID or None on failure."""
        template_id = self._get_template_id("email_verification", locale)
        if template_id is None:
            return None
        settings = get_settings()
        verify_url = settings.resend.verify_url_template.format(token=token)
        try:
            params: dict[str, Any] = {
                "from": self._from_header(),
                "to": [to],
                "template": {
                    "id": template_id,
                    "variables": {"VERIFY_URL": verify_url},
                },
            }
            email = resend.Emails.send(params)  # type: ignore[arg-type]
            return str(email["id"])
        except Exception:
            logger.exception("Failed to send email verification to %s", to)
            return None

    async def send_coaching_invite(
        self, to: str, inviter_name: str, connection_type: str, locale: str = "ru"
    ) -> str | None:
        """Send coaching/choreography invite email. Returns Resend email ID or None on failure."""
        template_id = self._get_template_id("coaching_invite", locale)
        if template_id is None:
            return None
        settings = get_settings()
        try:
            params: dict[str, Any] = {
                "from": self._from_header(),
                "to": [to],
                "template": {
                    "id": template_id,
                    "variables": {
                        "INVITER_NAME": inviter_name,
                        "CONNECTION_TYPE": connection_type,
                        "DASHBOARD_URL": settings.resend.dashboard_url,
                    },
                },
            }
            email = resend.Emails.send(params)  # type: ignore[arg-type]
            return str(email["id"])
        except Exception:
            logger.exception("Failed to send coaching invite email to %s", to)
            return None
