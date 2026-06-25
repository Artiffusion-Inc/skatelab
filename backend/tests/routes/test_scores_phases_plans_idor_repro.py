"""Repro tests for IDOR (Insecure Direct Object Reference) on session-derived data.

These tests pin a real authorization bug class in the backend: the routes that
return data DERIVED from a session (`/scores`, `/phases`, `/training-plans`) fetch
the data by `session_id` / `plan_id` alone and NEVER verify that the requesting
user owns the session. The canonical `GET /sessions/{id}` route DOES check
ownership (`session.user_id != user.id` → 403, sessions.py:194-203), but the
scores/phases/training-plans routes were written without that guard.

Bug surface (all confirmed by reading the route + CRUD):

  - `routes/scores.py:23-30` — `get_session_scores(session_id)` calls
    `crud/session_score.get_by_session_id(db, session_id)` which filters ONLY by
    `SessionScore.session_id == session_id` (crud/session_score.py:9-11). No
    `user_id` filter, no ownership check. ANY authenticated user can read ANY
    other user's composite scores + subscores by guessing/enumerating a
    session id.

  - `routes/phases.py:23-30` — same: `get_by_session_id(db, session_id)`
    (crud/session_phase.py:9-11) filters only by `session_id`. No ownership
    check. ANY authenticated user reads another user's phase detection data.

  - `routes/training_plans.py:44-49` — `get_plan(plan_id)` calls
    `crud/training_plan.get_by_id(db, plan_id)` which selects by `id` only
    (crud/training_plan.py:7-9). No `user_id` filter. ANY authenticated user
    reads ANY other user's generated training plan.

  - `routes/training_plans.py:26-42` — `generate_plan(data.session_id)` calls
    `crud/session_score.get_by_session_id(db, data.session_id)` (no ownership
    check) and then CREATES a training plan. A user can generate a plan from
    another user's session scores — leaking the victim's metric profile into an
    attacker-owned plan object (and burning compute).

Contrast (the existing, correct pattern in the SAME codebase):
`routes/sessions.py:186-204` `get_session` fetches the session, then checks
`session.user_id != user.id` (and a coaching-connection override) before
returning it — 403 otherwise. `test_get_session_forbidden` already pins that
contract GREEN. The scores/phases/plans routes diverge from this established
pattern and have NO equivalent test — so the IDOR never surfaces in CI.

User impact: scores (overall + per-subscore), phase detection, and AI training
plans are sensitive per-user coaching data. A coach's student-A could read
student-B's scores/plans if they obtain or guess a session/plan id. Session ids
are UUIDs (not trivially guessable) but UUIDs leak via logs, URLs, shared links,
and prior GET /sessions responses in multi-account scenarios; IDOR is still a
real severity issue for a SaaS handling personal athletic performance data.

These repros are RED now: an authenticated user requesting another user's
scores/phases/plan currently gets 200 with the victim's data. After the fix
(add the same ownership/coaching check as `get_session` before returning), the
asserts flip to expecting 403 → GREEN.

No production data is mutated by these tests: they create two users + a session
in the in-memory SQLite test DB and read through the AsyncTestClient. The
training-plan generation path does INSERT a plan, but only in the test DB.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import create_access_token, hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def victim_user(db_session: AsyncSession) -> User:
    user = User(
        email="victim@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def victim_headers(victim_user):
    token = create_access_token(user_id=victim_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def attacker_user(db_session: AsyncSession) -> User:
    user = User(
        email="attacker@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def attacker_headers(attacker_user):
    token = create_access_token(user_id=attacker_user.id)
    return {"Authorization": f"Bearer {token}"}


async def _create_victim_session(db_session: AsyncSession, victim_user: User):
    """Create a session owned by the victim (bypassing route rate-limits)."""
    from app.crud.session import create as crud_create

    session = await crud_create(db_session, user_id=victim_user.id, element_type="lutz")
    return session


@pytest.mark.asyncio
async def test_get_scores_idor_other_user_returns_403_repro(
    client, attacker_headers, victim_user, db_session: AsyncSession
):
    """GET /sessions/{id}/scores for ANOTHER user's session must 403, not 200.

    RED now: the route returns the victim's composite score (200) with no
    ownership check. After the fix (ownership guard like `get_session`) → 403.
    """
    from app.crud.session_score import create as create_score

    session = await _create_victim_session(db_session, victim_user)
    await create_score(
        db_session,
        session_id=session.id,
        subscores=[
            {
                "name": "takeoff",
                "label_ru": "Отрыв",
                "value": 8.5,
                "confidence": 0.9,
                "contributing_metrics": ["airtime"],
            }
        ],
        overall=8.5,
    )

    response = await client.get(f"/v1/sessions/{session.id}/scores", headers=attacker_headers)

    # CONTRACT: an attacker requesting the victim's session scores must be
    # denied (403). RED now: status is 200 and the body contains the victim's
    # overall score — a direct cross-user data leak.
    assert response.status_code == 403, (
        "BUG (IDOR): GET /sessions/{id}/scores returned "
        f"{response.status_code} for another user's session instead of 403. "
        f"Leaked body: {response.text}"
    )


@pytest.mark.asyncio
async def test_get_phases_idor_other_user_returns_403_repro(
    client, attacker_headers, victim_user, db_session: AsyncSession
):
    """GET /sessions/{id}/phases for ANOTHER user's session must 403, not 200.

    RED now: the route returns the victim's phase detection (200) with no
    ownership check. After the fix → 403.
    """
    from app.crud.session_phase import create as create_phase

    session = await _create_victim_session(db_session, victim_user)
    await create_phase(
        db_session,
        session_id=session.id,
        phases=[
            {
                "name": "takeoff",
                "start_frame": 0,
                "end_frame": 10,
                "start_time": 0.0,
                "end_time": 0.33,
                "confidence": 0.9,
                "detection_method": "com",
            }
        ],
        overall_confidence=0.9,
        element_type="lutz",
    )

    response = await client.get(f"/v1/sessions/{session.id}/phases", headers=attacker_headers)

    assert response.status_code == 403, (
        "BUG (IDOR): GET /sessions/{id}/phases returned "
        f"{response.status_code} for another user's session instead of 403. "
        f"Leaked body: {response.text}"
    )


@pytest.mark.asyncio
async def test_get_training_plan_idor_other_user_returns_403_repro(
    client, attacker_headers, victim_user, db_session: AsyncSession
):
    """GET /training-plans/{plan_id} for ANOTHER user's plan must 403, not 200.

    RED now: the route fetches the plan by id only (no user_id filter) and
    returns the victim's plan (200). After the fix → 403.
    """
    from app.crud.training_plan import create as create_plan

    plan = await create_plan(
        db_session,
        user_id=victim_user.id,
        session_id=None,
        items=[],
        focus_subscore=None,
    )

    response = await client.get(f"/v1/training-plans/{plan.id}", headers=attacker_headers)

    assert response.status_code == 403, (
        "BUG (IDOR): GET /training-plans/{id} returned "
        f"{response.status_code} for another user's plan instead of 403. "
        f"Leaked body: {response.text}"
    )


@pytest.mark.asyncio
async def test_generate_training_plan_idor_other_user_session_repro(
    client, attacker_headers, victim_user, db_session: AsyncSession
):
    """POST /training-plans/generate with ANOTHER user's session_id must 403.

    RED now: the route reads the victim's session score by session_id alone (no
    ownership check) and creates a plan from it. After the fix → 403 (the
    attacker must not be able to derive a plan from the victim's metrics).

    Note: the generated plan is created in the test in-memory DB only — no
    production data is mutated.
    """
    from app.crud.session_score import create as create_score

    session = await _create_victim_session(db_session, victim_user)
    await create_score(
        db_session,
        session_id=session.id,
        subscores=[
            {
                "name": "landing",
                "label_ru": "Приземление",
                "value": 6.0,
                "confidence": 0.8,
                "contributing_metrics": ["landing_knee_angle"],
            }
        ],
        overall=6.0,
    )

    response = await client.post(
        "/v1/training-plans/generate",
        json={"session_id": session.id},
        headers=attacker_headers,
    )

    assert response.status_code == 403, (
        "BUG (IDOR): POST /training-plans/generate accepted another user's "
        f"session_id and returned {response.status_code} instead of 403 — the "
        f"attacker derived a training plan from the victim's metrics. "
        f"Body: {response.text}"
    )
