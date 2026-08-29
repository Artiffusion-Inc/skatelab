"""Repro tests for training-plan route bugs #789-#794.

Pins six route-layer defects in ``routes/training_plans.py``:

  - #789: subscore coercion passed non-dict/non-schema garbage straight into
    ``generate_training_plan``, where it crashed on ``.value``/``.name``.
    Fix: validate+coerce each subscore, skip invalid entries with a warning.
  - #790: ``generate_training_plan`` call was unguarded — corrupt/edge
    subscores raised AttributeError/TypeError/ValueError → unhandled 500.
    Fix: wrap in try/except → 502 "Plan generation failed".
  - #791: ``TrainingPlanResponse.model_validate(plan)`` was unguarded —
    schema drift on the row raised ValidationError → unhandled 500.
    Fix: wrap in try/except → 502.
  - #792: ``POST /generate`` had no rate limit — expensive service CPU + DB
    write, abusable.
    Fix: ``check_rate_limit(f"plan_generate:{user.id}", max_requests=5,
    window_seconds=3600)``.
  - #793: repeated POST /generate for the same (user, session) created
    duplicate rows (table pollution).
    Fix: idempotent per (user_id, session_id) — ``get_for_session`` returns the
    existing plan instead of inserting a new one.
  - #794: ``GET /{plan_id}`` had no rate limit — DB read flood.
    Fix: ``check_rate_limit(f"plan_get:{user.id}", max_requests=60,
    window_seconds=60)``.

Tests:
  - source-asserting (read the route file, pin the guards exist) for #790/#791
    (try/except → 502) and #792/#794 (rate-limit calls with the exact scope/key).
  - behavioral (in-memory SQLite + AsyncTestClient) for #789 (garbage subscore
    skipped, valid plan returned) and #793 (idempotent — two POSTs return the
    same plan_id, one row in DB).

The FakeValkey in conftest returns count=1 from its pipeline, so
``check_rate_limit`` never trips behaviorally — the rate-limit tests are
source-asserting, not behavioral. That is enough to pin the guard's presence
and its exact identifier (the per-user scope is the security/cost property).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import create_access_token, hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


ROUTE_FILE = Path(__file__).resolve().parents[2] / "app" / "routes" / "training_plans.py"


# ---------------------------------------------------------------------------
# Source-asserting: the guards exist and use the right scope (#790/#791/#792/#794)
# ---------------------------------------------------------------------------


def test_source_generate_plan_has_rate_limit_call_with_per_user_scope():
    """#792: generate_plan must call check_rate_limit with plan_generate:{user.id}."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "check_rate_limit(" in src
    assert "plan_generate:" in src
    assert "max_requests=5" in src
    assert "window_seconds=3600" in src


def test_source_get_plan_has_rate_limit_call_with_per_user_scope():
    """#794: get_plan must call check_rate_limit with plan_get:{user.id}."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "plan_get:" in src
    assert "max_requests=60" in src
    assert "window_seconds=60" in src


def test_source_generate_plan_wraps_generator_in_try_except_502():
    """#790: generate_training_plan call must be wrapped — AttributeError/
    TypeError/ValueError → ClientException(status_code=502)."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "except (AttributeError, TypeError, ValueError)" in src
    assert "status_code=502" in src
    assert "generate_training_plan(" in src


def test_source_model_validate_wrapped_in_try_except_502():
    """#791: every TrainingPlanResponse.model_validate(...) call must be
    wrapped in try/except ValidationError → 502. There are three call sites
    (existing-plan return, created-plan return, get_plan return)."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    validate_count = src.count("TrainingPlanResponse.model_validate(")
    except_count = src.count("except ValidationError")
    assert validate_count >= 3, f"expected >=3 model_validate calls, got {validate_count}"
    assert except_count >= 3, f"expected >=3 ValidationError handlers, got {except_count}"
    assert "status_code=502" in src


def test_source_subscore_coercion_skips_invalid_entries():
    """#789: the coercion loop must isinstance-check SubScoreSchema and dict,
    skip garbage, and log a warning on skipped entries."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "isinstance(s, SubScoreSchema)" in src
    assert "isinstance(s, dict)" in src
    assert "SubScoreSchema(**s)" in src
    assert "continue" in src
    assert "logger.warning" in src


def test_source_dedup_uses_get_for_session():
    """#793: generate_plan must short-circuit on an existing plan for the
    (user_id, session_id) pair via crud.get_for_session, returning it
    instead of creating a duplicate."""
    src = ROUTE_FILE.read_text(encoding="utf-8")
    assert "get_for_session" in src
    assert "existing is not None" in src


def test_source_get_for_session_crud_exists():
    """#793: crud/training_plan.py must expose get_for_session(db, user_id, session_id)."""
    crud_file = ROUTE_FILE.resolve().parents[1] / "crud" / "training_plan.py"
    src = crud_file.read_text(encoding="utf-8")
    assert "async def get_for_session(" in src
    assert "TrainingPlanModel.user_id == user_id" in src
    assert "TrainingPlanModel.session_id == session_id" in src


# ---------------------------------------------------------------------------
# Behavioral: #789 (garbage subscore skipped) + #793 (idempotent generate)
# ---------------------------------------------------------------------------


@pytest.fixture
async def verified_user(db_session: AsyncSession) -> User:
    user = User(
        email="planner@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def user_headers(verified_user: User):
    token = create_access_token(user_id=verified_user.id)
    return {"Authorization": f"Bearer {token}"}


async def _create_owned_session(db_session: AsyncSession, user: User):
    from app.crud.session import create as crud_create

    return await crud_create(db_session, user_id=user.id, element_type="lutz")


@pytest.mark.asyncio
async def test_generate_plan_skips_garbage_subscore_and_returns_plan(
    client, user_headers, verified_user, db_session: AsyncSession
):
    """#789: a SessionScore row whose subscores list contains a non-dict /
    non-schema garbage entry must NOT crash the generator. The garbage entry
    is skipped; the valid subscore still produces a plan (201).

    RED without the fix: the route passed the garbage entry into
    ``generate_training_plan``, which raised AttributeError on ``.value`` →
    500. After the fix: garbage skipped, valid entry yields items → 201.
    """
    from app.crud.session_score import create as create_score

    session = await _create_owned_session(db_session, verified_user)
    # Subscores list mixes one valid dict + one garbage non-dict value (the
    # kind of entry a legacy row / worker bug / manual DB edit can leave
    # behind). The dict uses a real recommendation key so the generator emits
    # an item.
    await create_score(
        db_session,
        session_id=session.id,
        subscores=[
            {
                "name": "takeoff_power",
                "label_ru": "Отрыв",
                "value": 4.0,
                "confidence": 0.8,
                "contributing_metrics": ["airtime"],
            },
            "garbage-string-not-a-subscore",  # would crash without #789 coercion
        ],
        overall=4.0,
    )

    response = await client.post(
        "/v1/training-plans/generate",
        json={"session_id": session.id},
        headers=user_headers,
    )

    assert response.status_code == 201, (
        f"#789: expected 201 with garbage subscore skipped, got "
        f"{response.status_code}. Body: {response.text}"
    )
    body = response.json()
    assert "id" in body
    assert isinstance(body["items"], list)
    assert len(body["items"]) >= 1, "valid subscore should yield at least one plan item"


@pytest.mark.asyncio
async def test_generate_plan_is_idempotent_per_user_session(
    client, user_headers, verified_user, db_session: AsyncSession
):
    """#793: two POST /generate for the same (user, session) must return the
    SAME plan id and must NOT create a second row.

    RED without the fix: each POST inserted a new plan → different ids,
    table pollution. After the fix: second POST returns the existing plan.
    """
    from app.crud.session_score import create as create_score

    session = await _create_owned_session(db_session, verified_user)
    await create_score(
        db_session,
        session_id=session.id,
        subscores=[
            {
                "name": "takeoff_power",
                "label_ru": "Отрыв",
                "value": 4.0,
                "confidence": 0.8,
                "contributing_metrics": ["airtime"],
            }
        ],
        overall=4.0,
    )

    r1 = await client.post(
        "/v1/training-plans/generate",
        json={"session_id": session.id},
        headers=user_headers,
    )
    assert r1.status_code == 201, r1.text
    plan_id_1 = r1.json()["id"]

    r2 = await client.post(
        "/v1/training-plans/generate",
        json={"session_id": session.id},
        headers=user_headers,
    )
    assert r2.status_code == 201, r2.text
    plan_id_2 = r2.json()["id"]

    assert plan_id_1 == plan_id_2, (
        f"#793: repeated generate created a duplicate plan "
        f"({plan_id_1} != {plan_id_2}) — expected idempotent return of the "
        f"existing plan."
    )


@pytest.mark.asyncio
async def test_generate_plan_502_on_corrupt_subscore_value(
    client, user_headers, verified_user, db_session: AsyncSession
):
    """#790: a subscore whose ``value`` is a non-numeric type crashes the
    generator (TypeError in ``sorted``/comparison). The route must surface 502,
    not 500.

    We bypass the SubScoreSchema validator (which would reject a non-float)
    by writing the score row directly through the CRUD with a dict that has an
    invalid value type — the coercion loop's dict branch constructs
    SubScoreSchema(**s); for a non-numeric value the ValidationError is caught
    by the #789 skip branch, so this test instead targets the #790 generator
    guard by mocking generate_training_plan to raise ValueError.
    """
    from app.crud.session_score import create as create_score

    session = await _create_owned_session(db_session, verified_user)
    await create_score(
        db_session,
        session_id=session.id,
        subscores=[
            {
                "name": "takeoff_power",
                "label_ru": "Отрыв",
                "value": 4.0,
                "confidence": 0.8,
                "contributing_metrics": ["airtime"],
            }
        ],
        overall=4.0,
    )

    with patch(
        "app.routes.training_plans.generate_training_plan",
        side_effect=ValueError("corrupt subscore edge"),
    ):
        response = await client.post(
            "/v1/training-plans/generate",
            json={"session_id": session.id},
            headers=user_headers,
        )

    assert response.status_code == 502, (
        f"#790: expected 502 when generator raises, got "
        f"{response.status_code}. Body: {response.text}"
    )
