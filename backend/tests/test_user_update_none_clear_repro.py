"""Repro tests — PATCH /users/me null clears optional fields (#844).

Pre-fix ``update_profile`` forwarded ``data.bio`` (default ``None``) to
``crud.update`` even when the field was absent from the request. With the
#547 sentinel in crud (only ``UNSET`` is skipped, ``None`` is applied),
an absent optional field would clear the stored value.

Fix (#844): ``update_profile`` uses ``model_dump(exclude_unset=True)`` so
absent fields are not forwarded, while an explicit ``null`` is forwarded
and applied as a clear.

Tests:
  - observable: PATCH {bio: null} after bio set → bio cleared (None).
  - observable: PATCH {height_cm: null} → height_cm cleared (None).
  - observable: PATCH {weight_kg: null} → weight_kg cleared (None).
  - observable: PATCH {display_name: "..."} without bio → bio unchanged
    (absent field must not clear).
  - source-asserting: update_profile forwards exclude_unset dump.
"""

from __future__ import annotations

import pytest


async def _patch(client, auth_headers, body):
    return await client.patch("/v1/users/me", json=body, headers=auth_headers)


async def test_patch_profile_null_bio_clears_field_repro(client, auth_headers):
    """#844: explicit null clears bio."""
    await _patch(client, auth_headers, {"bio": "first bio"})
    r = await _patch(client, auth_headers, {"bio": None})
    assert r.status_code == 200, r.text
    assert r.json()["bio"] is None, "#844 RED: PATCH {bio:null} did not clear bio"


async def test_patch_profile_null_height_clears_field_repro(client, auth_headers):
    """#844: explicit null clears height_cm."""
    await _patch(client, auth_headers, {"height_cm": 180})
    r = await _patch(client, auth_headers, {"height_cm": None})
    assert r.status_code == 200, r.text
    assert r.json()["height_cm"] is None, "#844 RED: height_cm not cleared"


async def test_patch_profile_null_weight_clears_field_repro(client, auth_headers):
    """#844: explicit null clears weight_kg."""
    await _patch(client, auth_headers, {"weight_kg": 72.0})
    r = await _patch(client, auth_headers, {"weight_kg": None})
    assert r.status_code == 200, r.text
    assert r.json()["weight_kg"] is None, "#844 RED: weight_kg not cleared"


async def test_patch_profile_absent_field_does_not_clear_repro(client, auth_headers):
    """#844: absent field must NOT clear an existing value."""
    await _patch(client, auth_headers, {"bio": "keep me"})
    # Patch a DIFFERENT field; bio absent → must survive.
    r = await _patch(client, auth_headers, {"display_name": "New Name"})
    assert r.status_code == 200, r.text
    assert r.json()["bio"] == "keep me", (
        "#844 RED: absent field cleared existing value — exclude_unset missing"
    )


def test_update_profile_route_uses_exclude_unset_repro():
    """#844 GREEN: update_profile must forward ``model_dump(exclude_unset=True)``."""
    import inspect
    from pathlib import Path

    from app.routes.users import UsersController

    src = Path(inspect.getfile(UsersController)).read_text()
    idx = src.index("async def update_profile")
    block = src[idx : idx + 600]
    assert "exclude_unset=True" in block, (
        "#844: update_profile must use data.model_dump(exclude_unset=True) so "
        "absent fields are not forwarded as None clears."
    )
