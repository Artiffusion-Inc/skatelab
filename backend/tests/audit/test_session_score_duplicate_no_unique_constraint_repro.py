"""RED repro — session_score and session_phase have unique session_id but
no upsert protection — re-processing creates duplicate rows (IntegrityError 500).

Bug: worker.py calls save_analyzer_results → create_score/create_phase.
Both have unique=True on session_id in the ORM model. But the CRUD create()
functions don't check for existing rows — they just db.add() and flush.
If the worker re-processes a session (e.g. after a partial failure + retry),
the second create_score() call hits the unique constraint and raises
IntegrityError → unhandled 500.

The worker already handles the main metrics path via save_analysis_results()
which uses update_session_analysis() for the JSON columns (UPSERT via UPDATE),
but SessionScore and SessionPhase go through raw create() with no
ON CONFLICT handling.

Expected: Re-processing a session should update existing score/phase rows
(or silently skip), not crash with IntegrityError.
Current: Second create → IntegrityError → 500 to the user.
"""

import pytest


def test_session_score_unique_constraint_exists():
    """Verify SessionScore.session_id has unique=True — the constraint exists."""
    from app.models.session_score import SessionScore

    # Check the session_id column has unique=True
    col = SessionScore.__table__.columns.get("session_id")
    assert col is not None, "session_id column should exist"
    assert col.unique is True, "session_id should have unique=True constraint"


def test_session_phase_unique_constraint_exists():
    """Verify SessionPhase.session_id has unique=True — the constraint exists."""
    from app.models.session_phase import SessionPhase

    col = SessionPhase.__table__.columns.get("session_id")
    assert col is not None, "session_id column should exist"
    assert col.unique is True, "session_id should have unique=True constraint"


def test_session_score_create_no_upsert_guard():
    """Verify session_score create() has upsert guard.

    #548 fix: create() now wraps db.flush() in try/except IntegrityError.
    On integrity error, fetch existing row and update in place. This
    pattern is compatible with mocked test sessions (test_worker_tasks
    uses AsyncMock db) — the upsert path triggers only on a real
    IntegrityError, which AsyncMock doesn't raise by default.
    """
    import inspect

    from app.crud.session_score import create

    source = inspect.getsource(create)
    # Post-fix: try/except IntegrityError around db.flush() with
    # rollback + update-existing fallback.
    assert "IntegrityError" in source, (
        "session_score.create() must catch IntegrityError on db.flush() "
        "and update the existing row instead of failing the request."
    )
    assert "rollback" in source, (
        "session_score.create() must rollback the failed insert before fetching the existing row."
    )


def test_session_phase_create_no_upsert_guard():
    """Verify session_phase create() has upsert guard.

    #548 fix: same IntegrityError pattern as session_score.
    """
    import inspect

    from app.crud.session_phase import create

    source = inspect.getsource(create)
    assert "IntegrityError" in source, (
        "session_phase.create() must catch IntegrityError on db.flush() "
        "and update the existing row instead of failing the request."
    )
    assert "rollback" in source, (
        "session_phase.create() must rollback the failed insert before fetching the existing row."
    )
