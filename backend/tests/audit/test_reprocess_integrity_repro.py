"""RED repro — re-process IntegrityError on three 1:1-per-session tables
(``session_metrics``, ``session_scores``, ``session_phases``).

Same bug-class across three CRUD layers: plain ``db.add`` + ``flush`` with NO
upsert / NO delete-existing-before-insert. Each table has a UNIQUE constraint
on the session-scoped key, so a second save for an already-saved session_id
(re-process / retry / re-analyze / re-upload) inserts a duplicate row and
raises ``IntegrityError`` at ``db.commit()``:

  LAYER 1 — session_metrics
    - ``crud/session_metric.py:120-124`` ``bulk_create``: loop ``db.add(
      SessionMetric(**m))`` + ``flush``, no get-by-session, no delete, no
      ``ON CONFLICT DO UPDATE``.
    - ``models/session.py:117-120`` ``Index("uq_session_metric_name",
      "session_id", "metric_name", unique=True)``.
    - caller ``services/session_saver.py:85`` (save_analysis_results) — no
      delete-existing before bulk_create.

  LAYER 2 — session_scores
    - ``crud/session_score.py:14-33`` ``create``: ``db.add(SessionScore(...))``
      + ``flush`` + ``refresh``, no upsert.
    - ``models/session_score.py:23-28`` ``session_id`` ``unique=True`` (1:1).
    - caller ``services/analyzer_save.py:73`` — no delete-existing, no upsert.

  LAYER 3 — session_phases
    - ``crud/session_phase.py:14-33`` ``create``: ``db.add(SessionPhase(...))``
      + ``flush`` + ``refresh``, no upsert.
    - ``models/session_phase.py:23-28`` ``session_id`` ``unique=True`` (1:1).
    - caller ``services/analyzer_save.py:165`` — no delete-existing, no upsert.

Trigger: ``routes/process.py:53-54`` checks ONLY ownership, NOT
already-processed → re-process is allowed. Single-threaded, NO concurrency
needed (sibling of the #459/#485 race-class on the SAME 1:1-per-session
tables, but reachable without a race — just call save twice for one session).

Prod impact (HIGH): EVERY retry / re-analyze / re-upload of an existing
session fails at metric-save → zero ``SessionMetric`` rows commit (session
stays non-done) OR broad-except rollback (``worker.py:529``) → session
``partial`` + multi-score + gamification XP / skill-unlocks silently dropped.

Technique: shared in-memory SQLite
(``?mode=memory&cache=shared&uri=true``) + ``async_sessionmaker``, mirrors
``test_user_level_unique_race_repro.py:55-75``. A real ``User`` + ``Session``
row is created to satisfy the FK (and to mirror prod shape); the UNIQUE
indexes ARE enforced by SQLite, which is what makes the duplicate insert
raise.
"""

from __future__ import annotations

import pytest
from app.auth.security import hash_password
from app.crud.session_metric import bulk_create
from app.crud.session_phase import create as create_phase
from app.crud.session_score import create as create_score
from app.models.base import Base
from app.models.session import Session
from app.models.user import User
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _setup_db(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_user_session(sessions) -> str:
    """Create a real User + Session row and return the session_id."""
    async with sessions() as s:
        user = User(
            email="reprocess@example.com",
            hashed_password=hash_password("pass"),
            is_verified=True,
        )
        s.add(user)
        await s.flush()
        await s.refresh(user)
        session = Session(
            user_id=user.id,
            element_type="waltz_jump",
            status="processing",
        )
        s.add(session)
        await s.flush()
        await s.refresh(session)
        session_id = session.id
        await s.commit()
    return session_id


# --- LAYER 1: session_metrics ------------------------------------------------


@pytest.mark.asyncio
async def test_session_metrics_reprocess_no_integrity_error():
    """Re-process (second bulk_create for an existing session_id) must upsert
    / replace, NOT raise. RED now: ``uq_session_metric_name(session_id,
    metric_name)`` unique + ``bulk_create`` is plain ``db.add`` with no
    delete-existing / no ON CONFLICT → duplicate (session_id, metric_name) →
    IntegrityError at commit → zero SessionMetric rows commit, session stays
    non-done. EVERY retry/re-analyze silently loses ALL metrics.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:reprocess_metrics?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    await _setup_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    sid = await _seed_user_session(sessions)

    metric = {
        "session_id": sid,
        "metric_name": "airtime",
        "metric_value": 0.5,
        "is_in_range": True,
    }

    # First save (initial analysis).
    async with sessions() as s:
        await bulk_create(s, [metric])
        await s.commit()

    # Re-process: same session, updated metric value.
    metric2 = {**metric, "metric_value": 0.6}
    raised = False
    exc: Exception | None = None
    try:
        async with sessions() as s:
            await bulk_create(s, [metric2])
            await s.commit()
    except IntegrityError as e:
        raised = True
        exc = e

    await engine.dispose()

    assert not raised, (
        f"BUG (session_metrics re-process): bulk_create duplicate "
        f"(session_id, metric_name) → IntegrityError → zero SessionMetric "
        f"rows commit, session stays non-done. Re-process (retry/re-analyze) "
        f"silently loses ALL metrics. uq_session_metric_name unique + no "
        f"upsert/delete-existing. crud/session_metric.py:120-124. {exc}"
    )


# --- LAYER 2: session_scores -------------------------------------------------


@pytest.mark.asyncio
async def test_session_scores_reprocess_no_integrity_error():
    """Re-process (second create_score for an existing session_id) must upsert
    / replace, NOT raise. RED now: ``session_scores.session_id`` unique=True
    (1:1) + ``create`` is plain ``db.add`` with no delete-existing / no ON
    CONFLICT → duplicate session_id → IntegrityError at commit → broad-except
    rollback (worker.py:529) → session partial + multi-score + gamification
    XP / skill-unlocks silently dropped.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:reprocess_scores?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    await _setup_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    sid = await _seed_user_session(sessions)

    subscores = [{"name": "technique", "value": 8.0}]

    # First save (initial analysis).
    async with sessions() as s:
        await create_score(
            s,
            session_id=sid,
            subscores=subscores,
            overall=8.0,
        )
        await s.commit()

    # Re-process: same session, updated overall.
    raised = False
    exc: Exception | None = None
    try:
        async with sessions() as s:
            await create_score(
                s,
                session_id=sid,
                subscores=subscores,
                overall=8.5,
            )
            await s.commit()
    except IntegrityError as e:
        raised = True
        exc = e

    await engine.dispose()

    assert not raised, (
        f"BUG (session_scores re-process): create_score duplicate session_id "
        f"→ IntegrityError (session_scores.session_id unique=True, 1:1) → "
        f"broad-except rollback (worker.py:529) → session partial + "
        f"multi-score + gamification XP/skill-unlocks silently dropped. "
        f"crud/session_score.py:14-33 no upsert/delete-existing. {exc}"
    )


# --- LAYER 3: session_phases -------------------------------------------------


@pytest.mark.asyncio
async def test_session_phases_reprocess_no_integrity_error():
    """Re-process (second create_phase for an existing session_id) must upsert
    / replace, NOT raise. RED now: ``session_phases.session_id`` unique=True
    (1:1) + ``create`` is plain ``db.add`` with no delete-existing / no ON
    CONFLICT → duplicate session_id → IntegrityError at commit → rollback →
    extended phase detection silently lost on every re-process.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:reprocess_phases?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
    )
    await _setup_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    sid = await _seed_user_session(sessions)

    phases = [{"phase": "approach", "frame": 10}]

    # First save (initial analysis).
    async with sessions() as s:
        await create_phase(
            s,
            session_id=sid,
            phases=phases,
            overall_confidence=0.7,
            element_type="waltz_jump",
            fallback_used=False,
        )
        await s.commit()

    # Re-process: same session, updated confidence.
    raised = False
    exc: Exception | None = None
    try:
        async with sessions() as s:
            await create_phase(
                s,
                session_id=sid,
                phases=phases,
                overall_confidence=0.8,
                element_type="waltz_jump",
                fallback_used=False,
            )
            await s.commit()
    except IntegrityError as e:
        raised = True
        exc = e

    await engine.dispose()

    assert not raised, (
        f"BUG (session_phases re-process): create_phase duplicate session_id "
        f"→ IntegrityError (session_phases.session_id unique=True, 1:1) → "
        f"rollback → extended phase detection silently lost on every "
        f"re-process. crud/session_phase.py:14-33 no upsert/delete-existing. "
        f"{exc}"
    )
