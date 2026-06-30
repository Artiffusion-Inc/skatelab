"""RED repro — gamification IDOR: GET /users/{user_id}/level + /skills lack ownership check.

Any authenticated user can read any other user's XP/level/skills. The routes
at backend/app/routes/gamification.py:22-30 take `user_id` from the PATH and
pass it straight to the crud with NO ownership or coaching-connection check.
The only auth dep is implicit (JWT middleware authenticates the requester)
but the requester's identity is NEVER compared against the path `user_id`.

GamificationController is co-mounted on the /users router
(backend/app/routes/__init__.py:39) alongside UsersController, so
GET /v1/users/{any_id}/level and GET /v1/users/{any_id}/skills are wide open.

Same IDOR class as patched #338-341 (session-derived routes) — but gamification
was never wired through backend/app/auth/ownership.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from app.auth.security import create_access_token, hash_password
from app.crud.user_level import add_xp
from app.models.skill_progress import SkillProgress
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    user = User(email="a@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    user = User(email="b@example.com", hashed_password=hash_password("pass"), is_verified=True)
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers_a(user_a):
    token = create_access_token(user_id=user_a.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_b(user_b):
    token = create_access_token(user_id=user_b.id)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def victim_b_gamification(db_session: AsyncSession, user_b: User) -> None:
    """Seed user_b's gamification: 500 XP + a skill_progress row (jumps_bronze).

    get_or_create() uses Postgres ON CONFLICT syntax not supported by the
    SQLite test DB, so insert the SkillProgress row directly via the ORM.
    """
    await add_xp(db_session, user_b.id, 500)  # B now has total_xp=500
    db_session.add(
        SkillProgress(
            user_id=user_b.id,
            skill_id="jumps_bronze",
            category="jumps",
            tier="bronze",
            unlocked=True,
            best_score=0.72,
            xp_reward=50,
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_level_idor_cross_user_read(
    client, user_a: User, user_b: User, auth_headers_a, victim_b_gamification
):
    """A reads B's level → must be 403/404, NOT 200 with B's XP.

    RED now: 200 with B's total_xp=500 (cross-user leak).
    """
    response = await client.get(f"/v1/users/{user_b.id}/level", headers=auth_headers_a)
    assert response.status_code in (403, 404), (
        f"IDOR: attacker read victim's level. "
        f"expected 403/404, got {response.status_code} body={response.json()}"
    )


@pytest.mark.asyncio
async def test_skills_idor_cross_user_read(
    client, user_a: User, user_b: User, auth_headers_a, victim_b_gamification
):
    """A reads B's skills → must be 403/404, NOT 200 with B's SkillProgress[].

    RED now: 200 with B's skills list (cross-user leak).
    """
    response = await client.get(f"/v1/users/{user_b.id}/skills", headers=auth_headers_a)
    assert response.status_code in (403, 404), (
        f"IDOR: attacker read victim's skills. "
        f"expected 403/404, got {response.status_code} body={response.json()}"
    )


@pytest.mark.asyncio
async def test_control_own_level_works(client, user_a: User, auth_headers_a, victim_b_gamification):
    """Control: A reads own level → 200 (sanity, confirms setup is correct)."""
    response = await client.get(f"/v1/users/{user_a.id}/level", headers=auth_headers_a)
    assert response.status_code == 200, (
        f"control failed: own level should be 200, got {response.status_code}"
    )
