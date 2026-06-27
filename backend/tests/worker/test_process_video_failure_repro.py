"""RED repro — C1: process_video_task failure path never sets Session.status=failed.

Bug (worker.py:557-590, the outer except of `process_video_task`):
    When `process_video_task` raises a non-retryable exception
    (OSError/ValueError/RuntimeError/ConnectionError/TimeoutError), the except
    block ONLY writes Valkey state via `store_error(task_id, ...)` +
    `publish_task_event(...)`. It NEVER updates the DB `Session.status` to
    `failed`. The DB session row stays in its initial status
    (`queued` if video_key present, else `uploading` — see
    routes/sessions.py:122) FOREVER.

    The user polls `GET /sessions/{id}` (which reads the DB row, not Valkey) and
    sees a session that never finishes — stuck in `queued`/`uploading` long
    after the worker has given up. Valkey says `failed`, DB says `queued`:
    silent divergence + stuck UI.

Contrast (proof this is an oversight, not intentional):
    `analyze_music_task` (worker.py:815-831) DOES set the DB status to `failed`
    on exception — it re-opens a session, calls
    `update_music_analysis(db, music, status="failed")`, commits, then re-raises.
    `process_video_task` has no equivalent DB-status-failed update.

RED assertion:
    After `process_video_task` raises a non-retryable ValueError, the DB
    `Session.status` MUST be a terminal state (`failed`). Today it stays
    `queued` (the initial status), so this test FAILS (RED). When fixed, the
    worker will mark the DB row `failed` and the assertion passes.

Determinism: pure mocks, no real GPU / Valkey / DB. The mock Session object
records every status mutation; we assert it was never set to `failed`.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock aiobotocore before importing app.worker (which imports app.storage).
_mock_aiobotocore = MagicMock()
_mock_aiobotocore_session = MagicMock()
sys.modules.setdefault("aiobotocore", _mock_aiobotocore)
sys.modules.setdefault("aiobotocore.session", _mock_aiobotocore_session)


def _make_async_session_cm(mock_db):
    """Return an async context manager mock for async_session()."""
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_db
    cm.__aexit__.return_value = False
    return cm


def _make_session_row(initial_status: str = "queued") -> MagicMock:
    """Build a mock Session ORM row whose .status we can inspect after the call."""
    session = MagicMock()
    session.id = "session_stuck_1"
    session.user_id = "user_1"
    session.element_type = "waltz_jump"
    session.isu_code = None
    session.status = initial_status
    session.segmentation_status = "pending"
    return session


@pytest.fixture
def mock_valkey():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _inject_test_pool(mock_valkey):
    from app.task_manager import _set_test_pool

    _set_test_pool(mock_valkey)
    yield
    _set_test_pool(None)


@pytest.mark.asyncio
async def test_process_video_failure_does_not_set_db_session_status_failed(mock_valkey):
    """C1 RED: non-retryable failure leaves DB Session.status='queued', not 'failed'.

    Valkey gets `store_error` (status=failed) but the DB row is never updated.
    After a fix the worker should mark the DB Session row `failed` too, and
    this assertion will pass.
    """
    from app.worker import process_video_task

    initial_status = "queued"
    mock_session = _make_session_row(initial_status=initial_status)

    # Track any attempt to mutate the DB Session.status via update_session_analysis
    # or any direct attribute assignment we can observe.
    update_session_analysis = AsyncMock()

    with (
        patch(
            "app.vastai.client.process_video_remote_async",
            new_callable=AsyncMock,
            side_effect=ValueError("vast malformed payload"),
        ),
        patch("app.database.async_session_factory", create=True) as mock_async_session,
        patch("app.crud.session.get_by_id", new_callable=AsyncMock) as mock_get_by_id,
        patch(
            "app.crud.session.update_session_analysis",
            new_callable=AsyncMock,
        ) as mock_update_analysis,
        patch("app.worker.store_error", new_callable=AsyncMock) as mock_store_error,
        patch("app.worker.publish_task_event", new_callable=AsyncMock),
    ):
        # First get_by_id (fetch element_type at start) returns the session row.
        mock_get_by_id.return_value = mock_session
        mock_db = AsyncMock()
        mock_async_session.return_value = _make_async_session_cm(mock_db)

        # Non-retryable error (no "timeout"/"connection"/"network" in msg) so
        # the worker re-raises instead of deferring via Retry.
        with pytest.raises(ValueError, match="vast malformed payload"):
            await process_video_task(
                ctx={},
                task_id="task_stuck_1",
                video_key="input/video.mp4",
                person_click={"x": 100, "y": 200},
                session_id="session_stuck_1",
            )

    # --- Proof the failure path ran ---
    # Valkey WAS marked failed (this is the only thing the bug does today).
    mock_store_error.assert_awaited_once()
    assert mock_store_error.call_args[0][0] == "task_stuck_1"

    # --- THE BUG ASSERTION (RED) ---
    # The DB Session row must end in a terminal status. Today the worker NEVER
    # touches the DB Session.status on failure, so it stays "queued" forever.
    # update_session_analysis is the worker's only path that sets Session.status
    # (to "done") — on failure it must instead set "failed". It is never called
    # on the failure path today.
    assert mock_update_analysis.await_count == 0, (
        "sanity: update_session_analysis is not called on the failure path"
    )

    # The Session row's status must reflect terminal failure, not the initial
    # queued state. Today this is "queued" → assertion FAILS (RED).
    assert mock_session.status == "failed", (
        f"BUG (C1): process_video_task failure path never sets DB Session.status=failed. "
        f"Expected 'failed' (terminal), got {mock_session.status!r}. The outer except "
        f"block (worker.py:557-590) only writes Valkey via store_error + "
        f"publish_task_event — it NEVER updates the DB Session row. The session "
        f"stays {initial_status!r} forever; the user polls GET /sessions/{{id}} "
        f"(reads DB) and sees a never-finishing session. Contrast "
        f"analyze_music_task (worker.py:815-831) correctly sets DB status=failed "
        f"on exception. Fix: in the non-retryable except branch, open a session, "
        f"load the Session row, set status='failed' (+ error_message), commit."
    )


@pytest.mark.asyncio
async def test_process_video_failure_valkey_failed_but_db_queued_divergence(mock_valkey):
    """C1 RED (divergence form): Valkey says failed, DB says queued.

    A second angle on the same bug: the failure path writes Valkey status=failed
    via store_error, but the DB Session row is never updated, so the two stores
    diverge. After a fix, the DB row should also be terminal (failed), making the
    two stores consistent.
    """
    from app.worker import process_video_task

    mock_session = _make_session_row(initial_status="queued")

    with (
        patch(
            "app.vastai.client.process_video_remote_async",
            new_callable=AsyncMock,
            side_effect=RuntimeError("inference crashed"),
        ),
        patch("app.database.async_session_factory", create=True) as mock_async_session,
        patch("app.crud.session.get_by_id", new_callable=AsyncMock) as mock_get_by_id,
        patch("app.crud.session.update_session_analysis", new_callable=AsyncMock),
        patch("app.worker.store_error", new_callable=AsyncMock) as mock_store_error,
        patch("app.worker.publish_task_event", new_callable=AsyncMock),
    ):
        mock_get_by_id.return_value = mock_session
        mock_db = AsyncMock()
        mock_async_session.return_value = _make_async_session_cm(mock_db)

        with pytest.raises(RuntimeError, match="inference crashed"):
            await process_video_task(
                ctx={},
                task_id="task_div_1",
                video_key="input/video.mp4",
                person_click={"x": 100, "y": 200},
                session_id="session_div_1",
            )

    # Valkey status written by store_error is FAILED (task_manager.py:172).
    # That part works.
    mock_store_error.assert_awaited_once()

    # THE BUG (RED): DB Session.status diverges from Valkey. DB stays 'queued'
    # (the initial status) while Valkey reports 'failed'. After fix, DB should
    # also be 'failed' (terminal), so they agree.
    assert mock_session.status == "failed", (
        f"BUG (C1 divergence): Valkey is 'failed' but DB Session.status is "
        f"{mock_session.status!r} (initial 'queued' untouched). The failure "
        f"path (worker.py:557-590) updates Valkey only; the DB row never "
        f"transitions to a terminal state, so GET /sessions/{{id}} shows a "
        f"stuck session while Valkey reports failure. Fix: mirror "
        f"analyze_music_task — set DB status=failed on the non-retryable "
        f"except branch."
    )
