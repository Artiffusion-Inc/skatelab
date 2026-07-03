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

    #548 fix: create() now checks get_by_session_id first and updates
    existing rows instead of failing on the unique constraint.
    """
    import inspect

    from app.crud.session_score import create

    source = inspect.getsource(create)
    # Post-fix: create() calls get_by_session_id at the start of the
    # function to detect existing rows and update them instead of
    # failing on the unique constraint.
    assert "get_by_session_id" in source, (
        "session_score.create() must check for existing row first "
        "(upsert guard) to avoid IntegrityError on re-process."
    )


def test_session_phase_create_no_upsert_guard():
    """Verify session_phase create() has upsert guard.

    #548 fix: same as session_score — check existing first, update
    if present, otherwise create.
    """
    import inspect

    from app.crud.session_phase import create

    source = inspect.getsource(create)
    # Post-fix: create() calls get_by_session_id at the start.
    assert "get_by_session_id" in source, (
        "session_phase.create() must check for existing row first "
        "(upsert guard) to avoid IntegrityError on re-process."
    )
