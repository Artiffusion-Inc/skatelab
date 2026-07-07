"""Staff allowlist helper for internal docs access."""

from __future__ import annotations


def is_staff_email(email: str, staff_emails: list[str]) -> bool:
    """True if email is in the staff allowlist. Case-insensitive."""
    if not email or not staff_emails:
        return False
    return email.lower() in {e.lower() for e in staff_emails}
