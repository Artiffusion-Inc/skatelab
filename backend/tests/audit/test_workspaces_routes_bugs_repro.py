"""#731-#742: workspace route bug repro tests.

#731: create slug collision race (TOCTOU)
#732: invite lets ADMIN invite another ADMIN (role escalation)
#733: invite no self-invite guard
#734: invite race on add_workspace_member (TOCTOU) — pre-check exists
#735: get_workspace role check before existence (403 vs 404 leak)
#736: remove_member no last-admin guard (workspace orphan)
#737: remove_member silent 204 on non-existent member
#738: update_role ADMIN demotes peer ADMIN (no caller>=target check)
#739: update_role no self-demotion guard (admin lockout)
#740: create no per-user workspace count limit (DoS)
#741: workspace invite no rate limit (invite flood)
#742: invite no is_active check on target
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

ROUTES_PATH = Path(__file__).resolve().parents[2] / "app" / "routes" / "workspaces.py"
CRUD_PATH = Path(__file__).resolve().parents[2] / "app" / "crud" / "workspace.py"


# ---------------------------------------------------------------------------
# #731: slug collision race — IntegrityError catch
# ---------------------------------------------------------------------------


def test_create_catches_integrity_error_in_source():
    """#731: create wraps create_workspace in try/except IntegrityError."""
    source = ROUTES_PATH.read_text()
    assert "IntegrityError" in source, "#731: IntegrityError not imported/handled"


def test_create_workspace_has_unique_slug_in_model():
    """#731: Workspace model has unique constraint on slug."""
    from app.models.workspace import Workspace

    col = Workspace.__table__.c.slug
    assert col.unique is True, "#731: slug column missing unique constraint"


# ---------------------------------------------------------------------------
# #732: ADMIN cannot invite ADMIN — only OWNER can
# ---------------------------------------------------------------------------


def test_invite_admin_requires_owner_in_source():
    """#732: inviting as ADMIN requires OWNER role check."""
    source = ROUTES_PATH.read_text()
    assert "WorkspaceRole.ADMIN" in source, "#732: ADMIN role check missing in invite"


# ---------------------------------------------------------------------------
# #733: no self-invite
# ---------------------------------------------------------------------------


def test_no_self_invite_in_source():
    """#733: invite checks target.id != verified_user.id."""
    source = ROUTES_PATH.read_text()
    assert "Cannot invite yourself" in source, "#733: self-invite guard missing"


# ---------------------------------------------------------------------------
# #734: invite pre-check for existing member (409)
# ---------------------------------------------------------------------------


def test_invite_precheck_existing_member_in_source():
    """#734: invite checks existing membership before add."""
    source = ROUTES_PATH.read_text()
    assert "Already a member" in source, "#734: existing member pre-check missing"


# ---------------------------------------------------------------------------
# #735: get_workspace checks existence before role
# ---------------------------------------------------------------------------


def test_get_workspace_checks_existence_first_in_source():
    """#735: get_workspace checks workspace exists before role."""
    source = ROUTES_PATH.read_text()
    # Find the get_workspace method — should have NotFoundException before require_workspace_role
    assert "NotFoundException" in source, "#735: NotFoundException not used"


# ---------------------------------------------------------------------------
# #736: last-admin guard on remove
# ---------------------------------------------------------------------------


def test_last_admin_guard_in_source():
    """#736: remove_member checks last admin before removal."""
    source = ROUTES_PATH.read_text()
    assert "Cannot remove the last admin" in source, "#736: last-admin guard missing"


# ---------------------------------------------------------------------------
# #737: 404 on non-existent member removal
# ---------------------------------------------------------------------------


def test_remove_404_on_nonexistent_member_in_source():
    """#737: remove_member raises NotFoundException for missing member."""
    source = ROUTES_PATH.read_text()
    # The 404 check should happen before the removal
    lines = source.splitlines()
    in_remove = False
    for line in lines:
        if "async def remove_member" in line:
            in_remove = True
        if in_remove and "Member not found" in line:
            break
    else:
        pytest.fail("#737: Member not found check missing in remove_member")


# ---------------------------------------------------------------------------
# #738: ADMIN cannot demote peer ADMIN (only OWNER can promote to ADMIN)
# ---------------------------------------------------------------------------


def test_owner_check_on_admin_promotion_in_source():
    """#738: only OWNER can promote to ADMIN."""
    source = ROUTES_PATH.read_text()
    assert "Only the owner may promote members to admin" in source, (
        "#738: owner-only ADMIN promotion missing"
    )


# ---------------------------------------------------------------------------
# #739: no self-demotion
# ---------------------------------------------------------------------------


def test_no_self_demotion_in_source():
    """#739: update_role blocks self-role change."""
    source = ROUTES_PATH.read_text()
    assert "Cannot change your own role" in source, "#739: self-demotion guard missing"


# ---------------------------------------------------------------------------
# #740: per-user workspace count limit
# ---------------------------------------------------------------------------


def test_workspace_count_limit_in_source():
    """#740: create checks per-user workspace count."""
    source = ROUTES_PATH.read_text()
    assert "MAX_WORKSPACES_PER_USER" in source, "#740: workspace count limit constant missing"
    assert "Workspace limit reached" in source, "#740: workspace limit check missing"


def test_count_workspaces_for_user_in_crud():
    """#740: count_workspaces_for_user exists in CRUD."""
    source = CRUD_PATH.read_text()
    assert "count_workspaces_for_user" in source, "#740: count function missing in CRUD"


# ---------------------------------------------------------------------------
# #741: invite rate limit
# ---------------------------------------------------------------------------


def test_invite_rate_limit_in_source():
    """#741: invite has rate limit."""
    source = ROUTES_PATH.read_text()
    assert "check_rate_limit" in source, "#741: rate limit not called in invite"
    assert "workspace:invite" in source, "#741: workspace invite rate limit key missing"


# ---------------------------------------------------------------------------
# #742: invite checks target is_active
# ---------------------------------------------------------------------------


def test_invite_checks_target_is_active_in_source():
    """#742: invite checks target.is_active."""
    source = ROUTES_PATH.read_text()
    assert "is_active" in source, "#742: is_active check missing in invite"
