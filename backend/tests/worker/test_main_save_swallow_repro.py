"""RED repro: C5 — process_video_task OUTER main-save except swallows total save
failure and reports `completed` to the client with ZERO metrics committed.

Bug location: backend/app/worker.py:533-534
    except (OSError, ValueError, RuntimeError) as save_err:
        logger.warning("Failed to save session data: %s", save_err)

This outer except wraps the MAIN save block (`update_session_analysis`,
`save_analysis_results`, `batch_insert_elements`, commit). The inner except
at worker.py:530-532 rolls back and re-raises; that re-raise propagates to the
OUTER except at 533 which swallows (no re-raise). Control then falls through to:
  - `store_result(task_id, response_data)` at 537  -> hardcodes TaskStatus.COMPLETED
  - `publish_task_event(... status="completed" ...)` at 551-553

Result: client sees `status: completed` while the DB has ZERO SessionMetric
rows (rolled back) and Session.status never advanced to a terminal state.
Silent total data loss + false success.

Distinct from:
  - C1 (#371) — failure-path except at worker.py:557 (outermost, never sets
    Session.status=failed).
  - C2 (#372) — analyzer INNER except at worker.py:523 (save_analyzer_results
    rollback drops SessionScore/SessionPhase only).
C5 is the MIDDLE except wrapping the main save — a different try/except
boundary.

Contrast: analyze_music_task raises the error rather than swallowing
(worker.py:815-831).

This test is RED-by-design: it asserts the CORRECT behavior (no `completed`
reported when the main save fails) and FAILS today because the bug produces
`completed`. The test stays RED as proof of the bug — no fix is applied here.
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vast_result(**overrides):
    """Build a mock VastResult with metrics so the worker reaches the save block."""
    result = MagicMock()
    result.poses_key = None
    result.metrics_key = None
    result.stats = {"fps": 30}
    result.metrics = [{"name": "airtime", "value": 0.5}]
    result.phases = [{"phase": "takeoff", "frame": 10}]
    result.recommendations = ["Good jump."]
    result.segments = None
    result.rotations = 1
    for k, v in overrides.items():
        setattr(result, k, v)
    return result


def _make_async_session_cm(mock_db):
    """Return an async context manager mock for async_session()."""
    cm = AsyncMock()
    cm.__aenter__.return_value = mock_db
    cm.__aexit__.return_value = False
    return cm


@pytest.fixture
def mock_valkey():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _inject_test_pool(mock_valkey):
    from app.task_manager import _set_test_pool

    _set_test_pool(mock_valkey)
    yield
    _set_test_pool(None)


# ---------------------------------------------------------------------------
# C5 repro
# ---------------------------------------------------------------------------


class TestMainSaveSwallowRepro:
    """C5: outer main-save except swallows failure + reports completed."""

    @pytest.mark.asyncio
    async def test_main_save_failure_must_not_report_completed(self, mock_valkey):
        """RED-by-design: save_analysis_results raises -> worker must NOT report completed.

        Today the outer except at worker.py:533 swallows the RuntimeError, falls
        through to store_result (COMPLETED) + publish_task_event(completed), so the
        client sees a successful analysis while ZERO metrics were committed and
        Session.status never reached a terminal value.

        This assertion asserts the CORRECT behavior (no `completed` on save failure)
        and FAILS on the bug. The test stays RED as proof — no fix is applied.
        """
        from app.worker import process_video_task

        with (
            patch(
                "app.vastai.client.process_video_remote_async", new_callable=AsyncMock
            ) as mock_remote,
            patch("app.database.async_session_factory", create=True) as mock_async_session,
            patch("app.crud.session.get_by_id", new_callable=AsyncMock) as mock_get_session,
            patch(
                "app.services.session_saver.save_analysis_results",
                new_callable=AsyncMock,
                side_effect=RuntimeError("main save boom"),
            ),
            patch("app.crud.session.update_session_analysis", new_callable=AsyncMock),
            patch("app.crud.session.batch_insert_elements", new_callable=AsyncMock),
            # Capture the worker's reported status + published events.
            patch("app.worker.store_result", new_callable=AsyncMock) as mock_store_result,
            patch("app.worker.publish_task_event", new_callable=AsyncMock) as mock_publish_event,
        ):
            mock_remote.return_value = _make_vast_result()

            mock_db = AsyncMock()
            mock_async_session.return_value = _make_async_session_cm(mock_db)

            mock_session = MagicMock()
            mock_session.element_type = "waltz_jump"
            mock_session.user_id = "user_1"
            mock_get_session.return_value = mock_session

            result = await process_video_task(
                ctx={},
                task_id="proc_c5",
                video_key="input/video.mp4",
                person_click={"x": 100, "y": 200},
                session_id="session_42",
            )

        # --- Collect the statuses the worker reported to the client. ---
        # store_result hardcodes TaskStatus.COMPLETED (task_manager.py:154), so ANY
        # store_result call on this failure path is a `completed` report (the bug).
        # publish_task_event emits {"status": ...} dicts we collect below.
        from app.task_manager import TaskStatus

        reported_statuses: list[str] = []
        # One `completed` entry per store_result call (it always writes COMPLETED).
        reported_statuses.extend(
            TaskStatus.COMPLETED.value for _ in mock_store_result.call_args_list
        )
        reported_statuses.extend(
            call.args[1].get("status")
            for call in mock_publish_event.call_args_list
            if len(call.args) > 1 and isinstance(call.args[1], dict)
        )

        # 3) No metrics should have been committed (the inner except rolled back).
        # save_analysis_results raised before any commit, so the DB has ZERO
        # SessionMetric rows. We assert the worker should NOT claim success.
        mock_db.commit.assert_not_called()

        # --- The CORRECT behavior: no `completed` reported on main-save failure. ---
        # This FAILS today (RED) because the bug produces `completed` via both
        # store_result and publish_task_event despite ZERO committed metrics.
        assert TaskStatus.COMPLETED.value not in reported_statuses, (
            "C5 BUG: process_video_task reported `completed` to the client after "
            "the main save (save_analysis_results) raised RuntimeError. The outer "
            "except at worker.py:533 swallowed the error, store_result wrote "
            "TaskStatus.COMPLETED, and publish_task_event emitted status=completed, "
            "while ZERO SessionMetric rows were committed (rolled back by the inner "
            "except). Silent total data loss + false success. Fix: re-raise instead "
            "of swallow, OR set Valkey/DB status=failed on main-save failure before "
            "store_result. See issue: C5 (distinct from C1 #371 / C2 #372)."
        )
