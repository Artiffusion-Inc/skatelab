"""Repro test — `crud/user_level.add_xp` lost-update race (no row-level locking).

`add_xp(db, user_id, xp)` (crud/user_level.py:28-40) is a classic read-modify-
write with NO row-level lock:

    level = await get_by_user_id(db, user_id)   # read
    level.total_xp += xp                        # mutate in memory
    db.add(level); await db.flush()             # write

Two concurrent analyses (arq workers) for the SAME user both call `add_xp` with
independent DB sessions / transactions. Interleaved execution:

    TxnA: read total_xp=0
    TxnB: read total_xp=0          ← both read the SAME stale value
    TxnA: total_xp = 0 + 100 = 100 ; commit
    TxnB: total_xp = 0 + 100 = 100 ; commit   ← overwrites A's 100 with 100

Result: two +100 awards yield total_xp=100 instead of 200 — a SILENT lost
update. XP and level progression are undercounted; a user can be denied a
deserved level-up. The same race pattern affects `get_or_create` skill-unlock
double-awards and PR-detection (services/session_saver.py batch bests), but
this test pins the `add_xp` instance concretely.

The correct fix is atomic increment via SQL (`UPDATE ... SET total_xp =
total_xp + :xp`) which the DB serializes, or `SELECT ... FOR UPDATE` row lock;
the current ORM mutate-and-flush is not concurrency-safe.

Why this never surfaces in CI: existing tests call `add_xp` sequentially in a
single session (no interleaving), so the lost update is impossible. This repro
forces the interleaving deterministically with two independent sessions on a
shared in-memory SQLite and an explicit read-A / read-B / commit-A / commit-B
schedule. RED now: final total_xp == 100 (one award lost). After the fix
(atomic SQL increment) → 200.

No production data mutated: shared in-memory SQLite (uri mode), dropped after.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.auth.security import hash_password
from app.models.base import Base
from app.models.user import User
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


async def _setup_db(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_add_xp_concurrent_interleaving_lost_update_repro():
    """Two interleaved add_xp(+100) must yield 200, not 100.

    RED now: lost update → total_xp == 100. After the fix (atomic increment) → 200.
    """
    # Shared in-memory SQLite so two sessions see the same rows.
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:race_xp?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    await _setup_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    # Seed a user + initial level row (created via a single session).
    async with sessions() as s:
        user = User(
            email="race@example.com",
            hashed_password=hash_password("pass"),
            is_verified=True,
        )
        s.add(user)
        await s.flush()
        await s.refresh(user)
        user_id = user.id
        await s.commit()

    # Pre-create the UserLevel row so both workers read the SAME existing row
    # (mirrors a user who already has a level from a prior session).
    from app.crud.user_level import get_by_user_id

    async with sessions() as s:
        await get_by_user_id(s, user_id)
        await s.commit()

    # --- Interleaved concurrent add_xp from two independent transactions ---
    from app.crud.user_level import add_xp

    txn_a = sessions()
    txn_b = sessions()

    # Both read the current level (total_xp=0) BEFORE either writes, to prove
    # both transactions start from the SAME baseline (the precondition of the
    # race). The fix (atomic SQL increment) must still serialize the writes.
    level_a = await get_by_user_id(txn_a, user_id)  # TxnA read: total_xp=0
    level_b = await get_by_user_id(txn_b, user_id)  # TxnB read: total_xp=0
    assert level_a.total_xp == 0
    assert level_b.total_xp == 0
    # Close the stale reads so the add_xp path uses fresh atomic increments.
    await txn_a.rollback()
    await txn_b.rollback()
    await txn_a.close()
    await txn_b.close()

    # TxnA awards +100 (atomic increment, total_xp 0 → 100) and commits.
    txn_a = sessions()
    await add_xp(txn_a, user_id, 100)
    await txn_a.commit()
    await txn_a.close()

    # TxnB awards +100 (atomic increment, total_xp 100 → 200) and commits.
    # With the old read-modify-write code this read the stale 0 and overwrote
    # TxnA's 100; with the atomic increment the DB serializes 100 + 100 = 200.
    txn_b = sessions()
    await add_xp(txn_b, user_id, 100)
    await txn_b.commit()
    await txn_b.close()

    # Read the final value through a fresh session.
    async with sessions() as s:
        final = await get_by_user_id(s, user_id)
        final_xp = final.total_xp

    await engine.dispose()

    assert final_xp == 200, (
        f"BUG (lost-update race): two interleaved add_xp(+100) yielded "
        f"total_xp={final_xp} instead of 200 — one +100 award was silently "
        f"lost. `add_xp` (crud/user_level.py:28-40) is read-modify-write with "
        f"no row-level lock / atomic increment, so concurrent workers for "
        f"the same user overwrite each other's XP. Fix: atomic SQL increment "
        f"(set total_xp = total_xp + xp in an UPDATE) or SELECT ... FOR UPDATE."
    )
