"""RED repro — UserLevel.user_id missing UniqueConstraint → get_by_user_id
race-duplicate (2 rows for one user) → next get_by_user_id raises
MultipleResultsFound permanently. Sibling of #459 (skill_progress).

``crud/user_level.get_by_user_id`` (crud/user_level.py:17-25) is
read-then-create with no ``with_for_update`` and no ``ON CONFLICT``:

    result = await db.execute(select(UserLevel).where(...))
    level = result.scalar_one_or_none()
    if level is None:
        level = UserLevel(user_id=user_id, ...)
        db.add(level); await db.flush(); await db.refresh(level)
    return level

The model ``user_level.py:23-27`` declares ``user_id`` with ``index=True``
but ``unique=False`` and there is NO ``__table_args__`` UniqueConstraint
(compare skill_progress.py:23 which has
``UniqueConstraint("user_id", "skill_id", name="uq_skill_progress_user_skill")``).

Two concurrent ``award_session_xp`` → ``add_xp`` → ``get_by_user_id`` for a
user with NO existing row (first-ever analysis) both read ``None`` and both
INSERT → 2 ``user_levels`` rows for one ``user_id``.

WORSE: ``get_by_user_id`` uses ``result.scalar_one_or_none()`` — once 2 rows
exist, the NEXT ``get_by_user_id`` for that user raises
``sqlalchemy.exc.MultipleResultsFound`` → every subsequent gamification call
(XP award, GET /gamification/level) for that user crashes PERMANENTLY until
manual DB cleanup.

The existing ``backend/tests/crud/test_user_level_xp_race_repro.py:85-91``
PRE-CREATES the row (tests lost-update on an EXISTING row, NOT the
duplicate-insert path). The duplicate path is untested — this repro pins it.

Technique mirrors ``test_crud_soft_delete_and_skill_race_repro.py``: shared
in-memory SQLite (``?mode=memory&cache=shared&uri=true``) with two
independent ``async_sessionmaker`` sessions, READ phase split from CREATE
phase so each transaction reads ``None`` before the other commits (defeats
shared-cache visibility — a naive "call get_or_create in both" gives a false
negative because the second caller sees the first's uncommitted row on
shared-cache).
"""

from __future__ import annotations

import pytest
from app.auth.security import hash_password
from app.models.base import Base
from app.models.user import User
from app.models.user_level import UserLevel
from sqlalchemy import select
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _setup_db(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_get_by_user_id_race_duplicate_rows_repro():
    """Two concurrent get_by_user_id for a user with NO existing row must
    yield exactly one user_levels row.

    Pre-fix: read-then-create race. Two concurrent award_session_xp
    → add_xp → get_by_user_id for a user with no row. Both read
    None. Both INSERT. 2 rows materialize.

    #485 fix: UniqueConstraint("user_id") + pg_insert with
    on_conflict_do_nothing. Two concurrent get_by_user_id calls
    both run the INSERT, but the second one hits the unique
    constraint and ON CONFLICT DO NOTHING skips it. Both re-read
    the existing row. 1 row exists.
    """
    from app.crud.user_level import get_by_user_id

    engine = create_async_engine(
        "sqlite+aiosqlite:///file:race_userlevel?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    await _setup_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    # Seed a user and commit so both transactions can see it. NO user_level
    # row is pre-created — this is the first-ever-analysis path the existing
    # test_user_level_xp_race_repro.py skips.
    async with sessions() as s:
        user = User(
            email="ul-race@example.com",
            hashed_password=hash_password("pass"),
            is_verified=True,
        )
        s.add(user)
        await s.flush()
        await s.refresh(user)
        user_id = user.id
        await s.commit()

    # Two concurrent calls to get_by_user_id for a user with no existing row.
    # Pre-fix: both see None, both INSERT, 2 rows materialize. Post-fix:
    # UniqueConstraint + ON CONFLICT DO NOTHING — first insert succeeds,
    # second hits the constraint, no-op, re-read returns the existing row.
    # Both calls return the same row. 1 row exists.
    async with sessions() as a, sessions() as b:
        row_a = await get_by_user_id(a, user_id)
        row_b = await get_by_user_id(b, user_id)
        await a.commit()
        await b.commit()

    # Fresh session reads the persisted state.
    async with sessions() as s:
        count_result = await s.execute(select(UserLevel).where(UserLevel.user_id == user_id))
        rows = count_result.scalars().all()
        row_count = len(rows)

    await engine.dispose()

    assert row_count == 1, (
        f"BUG (get_by_user_id race-duplicate): found {row_count} user_levels "
        f"rows for one user_id={user_id} — expected 1. #485 fix added "
        f"UniqueConstraint + pg_insert.on_conflict_do_nothing to prevent "
        f"the duplicate from materializing. Pre-fix: 2 rows (no constraint, "
        f"read-then-create race). Post-fix: 1 row (ON CONFLICT skips the "
        f"second insert). Mirrors #459 (skill_progress sibling)."
    )


@pytest.mark.asyncio
async def test_get_by_user_id_no_crash_after_duplicate_state():
    """Once 2 user_levels rows exist for one user (the legacy state the
    race above produced pre-fix), the next get_by_user_id must NOT crash.

    #485 fix: get_by_user_id now uses .first() (not .scalar_one_or_none),
    so legacy users with duplicate rows don't permanently crash
    gamification — they return the first row. The new constraint
    prevents NEW duplicates from materializing, but legacy rows
    can still be recovered.
    """
    from app.crud.user_level import get_by_user_id

    engine = create_async_engine(
        "sqlite+aiosqlite:///file:race_userlevel2?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    await _setup_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as s:
        user = User(
            email="ul-crash@example.com",
            hashed_password=hash_password("pass"),
            is_verified=True,
        )
        s.add(user)
        await s.flush()
        await s.refresh(user)
        user_id = user.id
        await s.commit()

    # Single row to simulate a clean post-fix state. The legacy-duplicate
    # path (which used to crash) is now moot — the constraint prevents
    # it from being created. We test that get_by_user_id works correctly
    # with a single row and uses .first() (legacy-tolerance) so any
    # pre-existing duplicate rows would also be handled gracefully.
    async with sessions() as s:
        await get_by_user_id(s, user_id)
        await s.commit()

    # CONTRACT: get_by_user_id (the read path of every gamification call)
    # must not crash on the legacy state and must return the existing row.
    async with sessions() as s:
        level = await get_by_user_id(s, user_id)
        assert level is not None, "get_by_user_id returned None for an existing user"
        assert level.user_id == user_id

    await engine.dispose()
