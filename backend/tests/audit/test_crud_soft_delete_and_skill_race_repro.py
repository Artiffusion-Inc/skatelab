"""RED repro for two backend data-integrity bugs.

Bug #1 (HIGH) — soft-delete leak: ``crud/session.soft_delete`` only flips
``status`` to ``"deleted"`` (no ``deleted_at`` column), but the read paths
``get_by_id`` (crud/session.py:29-35), ``list_by_user`` (38-65) and
``count_by_user`` (68-78) select by ``user_id``/``id`` alone with NO
``status != "deleted"`` filter. Deleted sessions are therefore returned by
list, counted in totals, and fetched in full (metrics, pose_data,
recommendations) by ``GET /sessions/{id}``; coach ``?user_id=`` view shows a
student's deleted sessions; trend/prs/diagnostics are polluted.

The existing test ``test_session.py:192-200`` ENCODES the leak as expected
(``fetched.status == "deleted"``) so it is not a regression test. These
assertions pin the EXCLUSION behavior and are RED against current code.

Bug #2 (MEDIUM-HIGH) — ``skill_progress.get_or_create`` race + missing
``UniqueConstraint(user_id, skill_id)``. ``get_or_create``
(crud/skill_progress.py:26-45) is read-then-create with no ``with_for_update``
and no DB unique constraint on ``(user_id, skill_id)`` (migration
``add_analyzer_tables.py:46-77`` has separate non-unique indexes; model
``skill_progress.py`` has no ``__table_args__`` unique). Two concurrent
``check_skill_unlocks`` for the same user+category both read ``None`` and both
insert → 2 rows for one (user_id, skill_id). Consequences: duplicate skill
entries in UI, second-unlock re-flips ``unlocked``/``best_score``, per-row
``xp_reward`` would double-award if any caller awards it.

This test pins the race deterministically via the interleaved-two-sessionmaker
pattern (mirrors ``test_user_level_xp_race_repro.py``). RED now: 2 rows.
After fix (UniqueConstraint + ON CONFLICT / SELECT FOR UPDATE) → 1 row.
"""

from __future__ import annotations

import pytest
from app.crud.session import (
    count_by_user,
    create,
    get_by_id,
    list_by_user,
    soft_delete,
)
from app.crud.skill_progress import SKILL_DEFINITIONS, list_by_user_id
from app.models.base import Base
from app.models.skill_progress import SkillProgress
from app.models.user import User
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Bug #1 — soft-delete leak
# ---------------------------------------------------------------------------


async def test_soft_delete_excludes_from_list_count_get(db_session):
    """Deleted sessions must NOT appear in list_by_user / count_by_user /
    get_by_id. RED now: all three leak the deleted session."""
    # Seed a user + one session, then soft-delete it.
    user = User(id="user-1", email="user-1@test.com", hashed_password="hash")
    db_session.add(user)
    await db_session.flush()

    session = await create(db_session, user_id="user-1", element_type="axel")
    deleted_id = session.id
    await soft_delete(db_session, session)
    await db_session.commit()

    # list_by_user must exclude deleted sessions.
    listed = await list_by_user(db_session, "user-1")
    assert listed == [], (
        f"BUG (soft-delete leak): list_by_user returned {len(listed)} deleted "
        f"session(s) — {[s.id for s in listed]}. `soft_delete` sets "
        f"status='deleted' but list_by_user (crud/session.py:38-65) has no "
        f"status!='deleted' filter, so deleted sessions stay in the list."
    )

    # count_by_user must not count deleted sessions.
    counted = await count_by_user(db_session, "user-1")
    assert counted == 0, (
        f"BUG (soft-delete leak): count_by_user returned {counted} (expected 0) "
        f"— deleted session counted in total. count_by_user "
        f"(crud/session.py:68-78) has no status!='deleted' filter."
    )

    # get_by_id must not return the deleted session.
    fetched = await get_by_id(db_session, deleted_id)
    assert fetched is None, (
        f"BUG (soft-delete leak): get_by_id returned the deleted session "
        f"(id={deleted_id}, status={fetched.status if fetched else None}) — "
        f"full deleted session (metrics, pose_data, recommendations) is served "
        f"to any owner/coach GET. get_by_id (crud/session.py:29-35) has no "
        f"status!='deleted' filter."
    )


# ---------------------------------------------------------------------------
# Bug #2 — skill_progress.get_or_create race
# ---------------------------------------------------------------------------


async def _setup_db(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_skill_progress_get_or_create_race_duplicate_rows_repro():
    """Two concurrent get_or_create for the same (user_id, skill_id) must
    yield exactly one row. The guard is the UniqueConstraint(user_id,
    skill_id) on the skill_progress table: both transactions read None, the
    winner inserts and commits, the loser's insert is rejected by the
    constraint (IntegrityError). ``get_or_create`` turns that rejection into a
    no-op re-read via ON CONFLICT DO NOTHING.

    This repro drives the loser's insert directly (bypassing get_or_create's
    ON CONFLICT clause) to assert the DB-level constraint exists and rejects
    the duplicate. Before the fix there was no unique constraint and both
    rows materialized → 2 rows. SQLite shared-cache hides the race window if
    the winner's insert is left uncommitted while the loser inserts (the
    loser sees nothing), so the winner commits first to pin the rejection.
    """
    from sqlalchemy import select

    # Shared in-memory SQLite so two sessions share the same schema/rows.
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:race_skill?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    await _setup_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    # Seed a user and commit so both transactions can see it.
    async with sessions() as s:
        user = User(
            email="skill-race@example.com",
            hashed_password="hash",
            is_verified=True,
        )
        s.add(user)
        await s.flush()
        await s.refresh(user)
        user_id = user.id
        await s.commit()

    # Two independent transactions. READ phase: both SELECT the same
    # (user_id, skill_id) and get None — the precondition of the race.
    txn_a = sessions()
    txn_b = sessions()

    read_a = await txn_a.execute(
        select(SkillProgress).where(
            SkillProgress.user_id == user_id, SkillProgress.skill_id == "jumps_bronze"
        )
    )
    read_b = await txn_b.execute(
        select(SkillProgress).where(
            SkillProgress.user_id == user_id, SkillProgress.skill_id == "jumps_bronze"
        )
    )
    existing_a = read_a.scalar_one_or_none()
    existing_b = read_b.scalar_one_or_none()
    assert existing_a is None, "precondition: txn_a read None"
    assert existing_b is None, "precondition: txn_b read None"

    # CREATE phase: both build a SkillProgress and insert. With the
    # UniqueConstraint(user_id, skill_id) fix (#459), the DB rejects the
    # second insert (IntegrityError) instead of materializing a duplicate
    # row. get_or_create turns this into a no-op via ON CONFLICT DO NOTHING;
    # this raw-insert repro bypasses that helper to assert the DB-level guard
    # directly: exactly one row survives, the losing transaction fails.
    from sqlalchemy.exc import IntegrityError

    defn = next(s for s in SKILL_DEFINITIONS if s["id"] == "jumps_bronze")
    row_a = SkillProgress(
        user_id=user_id,
        skill_id=defn["id"],
        category=defn["category"],
        tier=defn["tier"],
        xp_reward=defn["xp_reward"],
    )
    row_b = SkillProgress(
        user_id=user_id,
        skill_id=defn["id"],
        category=defn["category"],
        tier=defn["tier"],
        xp_reward=defn["xp_reward"],
    )
    txn_a.add(row_a)
    txn_b.add(row_b)
    # a inserts and commits first — its row becomes the surviving row.
    await txn_a.flush()
    await txn_a.commit()
    # b, which read None before a committed, now tries to insert a duplicate.
    # The UniqueConstraint(user_id, skill_id) rejects it (IntegrityError) —
    # exactly the DB-level guard get_or_create relies on via ON CONFLICT DO
    # NOTHING. Before the fix there was no constraint and b's row would
    # materialize → 2 rows.
    with pytest.raises(IntegrityError):
        await txn_b.flush()
    await txn_b.rollback()
    await txn_a.close()
    await txn_b.close()

    # Fresh session reads the persisted state.
    async with sessions() as s:
        rows = await list_by_user_id(s, user_id)
        row_count = len(rows)

    await engine.dispose()

    assert row_count == 1, (
        f"BUG (get_or_create race): list_by_user_id returned {row_count} rows "
        f"for one (user_id={user_id}, skill_id='jumps_bronze') — expected 1. "
        f"The UniqueConstraint(user_id, skill_id) must reject the duplicate "
        f"insert so only the winner's row survives; get_or_create's ON "
        f"CONFLICT DO NOTHING turns the rejection into a no-op re-read."
    )
