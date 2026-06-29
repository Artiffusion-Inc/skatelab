"""T055 / #417 — `lang` plumbing to training-plan generation.

``POST /training-plans/generate`` (routes/training_plans.py) must forward
the caller's ``user.language`` into ``generate_training_plan(..., lang=...)``.
Issue #417: fix #415 added a ``lang`` param to ``generate_training_plan``
(picks ``label_en``/``description_en`` when ``lang="en"``), but the route
does NOT pass ``lang`` — every call defaults to ``"ru"`` so en-US users get
Russian training-plan items (``label_ru`` field holds Russian content).

This test enqueues a session with a multi-dimensional score and asserts the
returned plan item ``label_ru`` field holds English content for an
``language="en"`` user (e.g. "Jump rope", not "Прыжки через скакалку").

RED before site 6 (route passes no ``lang`` → defaults to ``"ru"`` →
Russian text), GREEN after.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from app.auth.security import create_access_token, hash_password
from app.crud.session import create as create_session
from app.crud.session_score import create as create_score
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _subscore(name: str, value: float = 3.0) -> dict:
    return {
        "name": name,
        "label_ru": "label",
        "value": value,
        "confidence": 0.9,
        "contributing_metrics": [],
    }


@pytest.fixture
async def en_user(db_session: AsyncSession) -> User:
    user = User(
        email="tp-en@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
        language="en",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def en_headers(en_user: User):
    token = create_access_token(user_id=en_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_training_plan_generate_uses_user_language_en(
    client, en_headers, en_user: User, db_session: AsyncSession
):
    """POST /training-plans/generate returns English plan items for en user."""
    session = await create_session(db_session, user_id=en_user.id, element_type="lutz")

    # Weakest subscore = takeoff_power (lowest value) → first plan item is the
    # takeoff_power exercise ("Jump rope" in EN / "Прыжки через скакалку" in RU).
    subscores = [
        _subscore("takeoff_power", value=2.0),
        _subscore("rotation_axis", value=6.0),
        _subscore("arm_coordination", value=7.0),
        _subscore("landing_absorption", value=6.5),
        _subscore("core_stability", value=7.0),
    ]
    await create_score(db_session, session_id=session.id, subscores=subscores, overall=5.5)

    # get_by_session_id loads via the route's db dep, which conftest overrides
    # to the test session, so the flushed score is visible there.
    response = await client.post(
        "/v1/training-plans/generate",
        json={"session_id": session.id},
        headers=en_headers,
    )

    assert response.status_code == 201, f"Body: {response.text}"

    body = response.json()
    assert body["items"], "training plan returned no items"
    first_label = body["items"][0]["label_ru"]
    assert "Jump rope" in first_label or "Squat jumps" in first_label, (
        f"BUG (#417): training-plan item for an language='en' user holds Russian "
        f"content (label_ru={first_label!r}). The route did not forward "
        f"user.language={en_user.language!r} to generate_training_plan, so it "
        f"defaulted to 'ru' and the English exercise labels are dead code."
    )
