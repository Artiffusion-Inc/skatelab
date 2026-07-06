"""Repro tests for user/profile bugfixes #743-#754.

#743/#744 already fixed (UNSET sentinel pattern in crud/user.py).
Tests here cover #745-#754.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from app.auth.security import create_access_token, hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

SCHEMAS_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "schemas.py"
ROUTES_FILE = Path(__file__).resolve().parent.parent.parent / "app" / "routes" / "users.py"


# ---------------------------------------------------------------------------
# Source-assertion tests
# ---------------------------------------------------------------------------


def test_745_language_whitelisted_in_source():
    """#745: UpdateSettingsRequest.language has pattern constraint."""
    src = SCHEMAS_FILE.read_text()
    assert r'"^(ru|en)$"' in src, "#745 language whitelist missing from schema"


def test_746_timezone_validator_in_source():
    """#746: UpdateSettingsRequest.timezone validated against IANA."""
    src = SCHEMAS_FILE.read_text()
    assert "ZoneInfoNotFoundError" in src, "#746 IANA timezone validation missing"
    assert "validate_timezone" in src, "#746 timezone validator missing"


def test_747_magic_byte_check_in_source():
    """#747: upload_avatar verifies magic bytes, not just Content-Type."""
    src = ROUTES_FILE.read_text()
    assert "_MAGIC_BYTES" in src, "#747 magic bytes dict missing"
    assert "content.startswith(magic)" in src, "#747 magic byte check missing"


def test_748_s3_rollback_in_source():
    """#748: upload_avatar cleans up S3 on DB failure."""
    src = ROUTES_FILE.read_text()
    assert "delete_object" in src, "#748 S3 rollback (delete_object) missing"


def test_749_avatar_rate_limit_in_source():
    """#749: upload_avatar has rate limit."""
    src = ROUTES_FILE.read_text()
    assert 'check_rate_limit(f"avatar:{user.id}"' in src, "#749 avatar rate limit missing"


def test_750_profile_rate_limit_in_source():
    """#750: update_profile has rate limit."""
    src = ROUTES_FILE.read_text()
    assert 'check_rate_limit(f"profile:{user.id}"' in src, "#750 profile rate limit missing"


def test_751_onboarding_idempotent_in_source():
    """#751: update_onboarding_role rejects if already set."""
    src = ROUTES_FILE.read_text()
    assert "onboarding_role is not None" in src, "#751 onboarding idempotency guard missing"


def test_752_display_name_html_stripped_in_source():
    """#752: display_name rejects HTML tags."""
    src = SCHEMAS_FILE.read_text()
    assert "strip_html" in src, "#752 display_name HTML strip validator missing"


def test_753_s3_exception_handled_in_source():
    """#753: S3 exceptions caught and logged, not leaked."""
    src = ROUTES_FILE.read_text()
    assert 'logger.exception("S3 upload failed' in src, "#753 S3 exception logging missing"


def test_754_avatar_content_hash_in_source():
    """#754: avatar key includes content hash for cache-busting."""
    src = ROUTES_FILE.read_text()
    assert "content_hash" in src, "#754 content hash missing from avatar key"
    assert "avatars/{user.id}/{content_hash}" in src, "#754 avatar key pattern missing"


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_745_language_rejects_unknown():
    """#745: language must be 'ru' or 'en'."""
    from app.schemas import UpdateSettingsRequest

    # Valid
    UpdateSettingsRequest(language="ru", timezone="UTC", theme="dark", angular_unit="deg_per_sec")
    UpdateSettingsRequest(language="en", timezone="UTC", theme="system", angular_unit="rpm")
    # Invalid
    with pytest.raises(ValueError):
        UpdateSettingsRequest(
            language="xx", timezone="UTC", theme="dark", angular_unit="deg_per_sec"
        )
    with pytest.raises(ValueError):
        UpdateSettingsRequest(
            language="RU", timezone="UTC", theme="dark", angular_unit="deg_per_sec"
        )


def test_746_timezone_rejects_garbage():
    """#746: timezone validated against IANA."""
    from app.schemas import UpdateSettingsRequest

    # Valid IANA timezone
    UpdateSettingsRequest(
        language="ru", timezone="Europe/Moscow", theme="dark", angular_unit="deg_per_sec"
    )
    UpdateSettingsRequest(language="en", timezone="UTC", theme="system", angular_unit="rpm")
    # Invalid
    with pytest.raises(ValueError):
        UpdateSettingsRequest(
            language="ru", timezone="garbage", theme="dark", angular_unit="deg_per_sec"
        )
    with pytest.raises(ValueError):
        UpdateSettingsRequest(
            language="ru", timezone="Foo/Bar", theme="dark", angular_unit="deg_per_sec"
        )


def test_752_display_name_rejects_html():
    """#752: display_name with HTML tags is rejected."""
    from app.schemas import UpdateProfileRequest

    # Valid
    UpdateProfileRequest(display_name="Алиса", bio="Hello")
    # HTML tags rejected
    with pytest.raises(ValueError):
        UpdateProfileRequest(display_name="<script>alert(1)</script>")
    with pytest.raises(ValueError):
        UpdateProfileRequest(display_name="<b>bold</b>")
    with pytest.raises(ValueError):
        UpdateProfileRequest(display_name="a > b")


# ---------------------------------------------------------------------------
# Route-level behavior tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def verified_user(db_session: AsyncSession) -> User:
    user = User(email="test@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(verified_user):
    return {"Authorization": f"Bearer {create_access_token(user_id=verified_user.id)}"}


_mock_email = patch("app.routes.connections.EmailService", spec=True)
_mock_email.start()


@pytest.mark.asyncio
async def test_751_onboarding_rejects_repeat(client, verified_user, auth_headers):
    """#751: setting onboarding_role twice returns 409."""
    # First set succeeds
    resp1 = await client.patch(
        "/v1/users/me/onboarding",
        json={"onboarding_role": "skater"},
        headers=auth_headers,
    )
    assert resp1.status_code == 200

    # Second set fails
    resp2 = await client.patch(
        "/v1/users/me/onboarding",
        json={"onboarding_role": "coach"},
        headers=auth_headers,
    )
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_745_language_rejected_via_api(client, verified_user, auth_headers):
    """#745: invalid language rejected at API level."""
    resp = await client.patch(
        "/v1/users/me/settings",
        json={"language": "xx"},
        headers=auth_headers,
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_746_timezone_rejected_via_api(client, verified_user, auth_headers):
    """#746: invalid timezone rejected at API level."""
    resp = await client.patch(
        "/v1/users/me/settings",
        json={"timezone": "garbage"},
        headers=auth_headers,
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_752_display_name_rejected_via_api(client, verified_user, auth_headers):
    """#752: display_name with HTML rejected at API level."""
    resp = await client.patch(
        "/v1/users/me",
        json={"display_name": "<script>alert(1)</script>"},
        headers=auth_headers,
    )
    assert resp.status_code in (400, 422)
