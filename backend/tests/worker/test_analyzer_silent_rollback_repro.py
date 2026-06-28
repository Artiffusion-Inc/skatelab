"""RED repro — C2: analyzer save_analyzer_results rollback silently drops
scores/phases + skips gamification while reporting `completed`.

Bug (worker.py:436-554, the `if session_id:` block of `process_video_task`):
    1. Main metrics + segments + status are committed at worker.py:480
       (`await db.commit()`). This persists SessionMetric rows and sets
       Session.status="done" via save_analysis_results.
    2. Then `save_analyzer_results` (analyzer_save.py) is called at
       worker.py:488 inside a nested try (485-522). It writes SessionScore +
       SessionPhase rows and, still inside the SAME try (before the second
       `db.commit()` at 508), enqueues the gamification task at 511-522
       (`redis.enqueue_job("compute_gamification_task", ...)`).
    3. When `save_analyzer_results` raises, the `except` at 523-529 logs a
       warning and calls `db.rollback()` (529) — discarding the
       SessionScore/SessionPhase rows AND ensuring the gamification enqueue
       (which is AFTER save_analyzer_results in the try) NEVER runs.
    4. BUT the outer flow continues: `store_result(task_id, response_data)`
       at 537 writes Valkey status="completed", and
       `publish_task_event(status="completed")` at 551 publishes "completed".

    Net effect: the client sees `completed` (Valkey + event stream) with NO
    SessionScore/SessionPhase rows and NO gamification (XP/skill-unlocks).
    Silent partial data loss + false-success reported to the user.

Contrast (proof this is a bug, not an accepted degradation):
    `analyze_music_task` (worker.py:815-831) RAISES on exception rather than
    swallowing — it sets DB status=failed and re-raises so the caller (arq)
    knows the task failed. The analyzer post-processing `except` in
    `process_video_task` instead swallows the error and reports completed.

RED assertion:
    After `save_analyzer_results` raises, the worker must NOT report
    `completed` to the client while SessionScore/SessionPhase are missing and
    gamification is skipped. Today: store_result=completed + publish
    "completed" + no gamification enqueue + SessionScore absent → test FAILS
    (RED). When fixed (mark the session partial/failed, or report a non-
    completed status, or commit scores before the risky step + surface the
    error), the assertion passes.

Determinism: pure mocks — no real GPU / Valkey / DB. We monkeypatch
`save_analyzer_results` to raise `RuntimeError("analyzer boom")` and assert on
the recorded Valkey/event/enqueue calls. No async timing involved.
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


def _make_vast_result(**overrides):
    """Build a mock VastResult with metrics/phases so the save path runs."""
    result = MagicMock()
    result.poses_key = None
    result.metrics_key = None
    result.stats = {"fps": 30}
    result.metrics = [{"name": "airtime", "value": 0.5}]
    result.phases = MagicMock()
    result.phases.name = "waltz_jump"
    result.phases.start = 0
    result.phases.takeoff = 5
    result.phases.peak = 10
    result.phases.landing = 15
    result.phases.end = 20
    result.recommendations = ["Good jump."]
    result.segments = None
    result.rotations = 1
    result.goe_grade = None
    for k, v in overrides.items():
        setattr(result, k, v)
    return result


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
async def test_analyzer_rollback_reports_completed_with_no_scores_no_gamification(mock_valkey):
    """C2 RED: save_analyzer_results raises → rollback drops scores + skips
    gamification, but store_result + publish_task_event still say 'completed'.
    """
    from app.worker import process_video_task

    mock_session = MagicMock()
    mock_session.id = "session_c2_1"
    mock_session.user_id = "user_c2"
    mock_session.element_type = "waltz_jump"
    mock_session.isu_code = None
    mock_session.status = "queued"
    mock_session.segmentation_status = "pending"

    # Fake arq redis pool with an enqueue_job spy — must NEVER be called when
    # save_analyzer_results raises (the gamification enqueue lives inside the
    # rolled-back try block at worker.py:511-522).
    fake_redis = MagicMock()
    fake_redis.enqueue_job = AsyncMock()

    # Track the create_score / create_phase calls inside save_analyzer_results
    # so we can prove they were attempted (added to session) then rolled back.
    create_score = AsyncMock()
    create_phase = AsyncMock()

    with (
        patch(
            "app.vastai.client.process_video_remote_async",
            new_callable=AsyncMock,
            return_value=_make_vast_result(),
        ),
        patch("app.database.async_session_factory", create=True) as mock_async_session,
        patch("app.crud.session.get_by_id", new_callable=AsyncMock) as mock_get_by_id,
        patch("app.crud.session.update_session_analysis", new_callable=AsyncMock),
        patch("app.services.session_saver.save_analysis_results", new_callable=AsyncMock),
        # save_analyzer_results is imported inside the function body from
        # app.services.analyzer_save — patch it there to raise AFTER the main
        # commit (worker.py:480).
        patch(
            "app.services.analyzer_save.save_analyzer_results",
            new_callable=AsyncMock,
            side_effect=RuntimeError("analyzer boom"),
        ),
        patch(
            "app.crud.session_score.create",
            new=create_score,
        ),
        patch(
            "app.crud.session_phase.create",
            new=create_phase,
        ),
        patch("app.worker.store_result", new_callable=AsyncMock) as mock_store_result,
        patch("app.worker.publish_task_event", new_callable=AsyncMock) as mock_publish,
        patch("app.worker.update_progress", new_callable=AsyncMock),
    ):
        mock_get_by_id.return_value = mock_session
        mock_db = AsyncMock()
        mock_async_session.return_value = _make_async_session_cm(mock_db)

        result = await process_video_task(
            ctx={"redis": fake_redis},
            task_id="task_c2_1",
            video_key="input/video.mp4",
            person_click={"x": 100, "y": 200},
            session_id="session_c2_1",
        )

    # --- Proof the main metrics commit happened (the precondition of C2) ---
    # The first commit (worker.py:480) persists SessionMetric rows. The
    # rollback at 529 only discards the analyzer rows added AFTER that commit.
    # We assert at least one commit was attempted (the main one) — proving the
    # rollback targeted the analyzer post-processing, not the main save.
    assert mock_db.commit.await_count >= 1, "main metrics commit must have run"

    # --- Proof save_analyzer_results raised and was caught ---
    # create_score/create_phase are called INSIDE save_analyzer_results
    # (analyzer_save.py:73, 144). Since we made save_analyzer_results itself
    # raise, those inner creates never run — but the rollback at 529 still
    # fires. The key point: no SECOND commit (508) happens, so even if rows
    # had been added they'd be rolled back.
    assert mock_db.rollback.await_count >= 1, (
        "analyzer failure must trigger db.rollback() (worker.py:529)"
    )

    # --- THE BUG ASSERTION (RED) ---
    # 1) Gamification enqueue MUST NOT run when save_analyzer_results raises
    #    (it is inside the same rolled-back try at worker.py:511-522).
    assert fake_redis.enqueue_job.await_count == 0, (
        "BUG (C2): gamification enqueue ran even though save_analyzer_results "
        "raised and the try block was rolled back. The enqueue at "
        "worker.py:511-522 is inside the same try as save_analyzer_results, "
        "so an exception must skip it. (If this fires, the test setup is "
        "wrong, not the bug.)"
    )

    # 2) BUT the worker reports 'completed' to the client via Valkey AND the
    #    event stream, despite the analyzer partial-failure. This is the
    #    silent false-success. RED today; after fix, status should be
    #    'partial'/'failed' or scores must be present.
    assert mock_store_result.await_count == 1, "store_result must be called once"
    # store_result writes TaskStatus.COMPLETED into Valkey (task_manager.py:154).
    # The published event must NOT claim 'completed' when scores are missing.
    published_statuses = [
        call.args[1].get("status")
        for call in mock_publish.call_args_list
        if len(call.args) > 1 and isinstance(call.args[1], dict)
    ]
    assert "completed" not in published_statuses, (
        f"BUG (C2): worker reports status='completed' to the client via "
        f"publish_task_event even though save_analyzer_results raised and "
        f"SessionScore/SessionPhase rows were rolled back + gamification was "
        f"skipped. Published statuses: {published_statuses}. The user sees "
        f"'completed' with NO multi-score report and NO XP/skill-unlocks — "
        f"silent partial data loss + false success. Contrast "
        f"analyze_music_task (worker.py:815-831) raises on exception rather "
        f"than swallowing. Fix: do not publish 'completed' when the analyzer "
        f"post-processing fails — set a 'partial'/'failed' status (Valkey + "
        f"event + DB), or commit SessionScore/SessionPhase in their own "
        f"transaction before the risky enqueue and surface the error."
    )

    # 3) store_result ALSO writes completed into Valkey — same bug, dual channel.
    # task_manager.store_result hardcodes TaskStatus.COMPLETED. After a fix,
    # the worker must not call store_result with the success payload when the
    # analyzer failed.
    assert result.get("status") != "Analysis complete!", (
        f"BUG (C2): process_video_task returns {result.get('status')!r} "
        f"('Analysis complete!') after save_analyzer_results raised — the "
        f"client-facing result masks the analyzer partial failure. Fix: "
        f"return a partial/failed status when analyzer post-processing fails."
    )


@pytest.mark.asyncio
async def test_analyzer_rollback_no_second_commit_so_scores_lost(mock_valkey):
    """C2 RED (commit-count form): the second commit (worker.py:508) is skipped
    on analyzer failure, so even if create_score had added rows, they are
    discarded by the rollback at 529. Combined with the 'completed' report,
    this is silent data loss.
    """
    from app.worker import process_video_task

    mock_session = MagicMock()
    mock_session.id = "session_c2_2"
    mock_session.user_id = "user_c2"
    mock_session.element_type = "axel"
    mock_session.isu_code = None
    mock_session.status = "queued"
    mock_session.segmentation_status = "pending"

    fake_redis = MagicMock()
    fake_redis.enqueue_job = AsyncMock()

    with (
        patch(
            "app.vastai.client.process_video_remote_async",
            new_callable=AsyncMock,
            return_value=_make_vast_result(),
        ),
        patch("app.database.async_session_factory", create=True) as mock_async_session,
        patch("app.crud.session.get_by_id", new_callable=AsyncMock) as mock_get_by_id,
        patch("app.crud.session.update_session_analysis", new_callable=AsyncMock),
        patch("app.services.session_saver.save_analysis_results", new_callable=AsyncMock),
        patch(
            "app.services.analyzer_save.save_analyzer_results",
            new_callable=AsyncMock,
            side_effect=RuntimeError("analyzer boom"),
        ),
        patch("app.worker.store_result", new_callable=AsyncMock) as mock_store_result,
        patch("app.worker.publish_task_event", new_callable=AsyncMock),
        patch("app.worker.update_progress", new_callable=AsyncMock),
    ):
        mock_get_by_id.return_value = mock_session
        mock_db = AsyncMock()
        mock_async_session.return_value = _make_async_session_cm(mock_db)

        await process_video_task(
            ctx={"redis": fake_redis},
            task_id="task_c2_2",
            video_key="input/video.mp4",
            person_click={"x": 100, "y": 200},
            session_id="session_c2_2",
        )

    # THE BUG (RED): today exactly ONE commit (main metrics at 480) runs on
    # analyzer failure — the second commit (508, for analyzer scores) is
    # skipped because save_analyzer_results raises before it, and rollback at
    # 529 discards any rows added in the analyzer try. So SessionScore /
    # SessionPhase are never persisted, yet store_result reports completed.
    # After a fix, EITHER the analyzer rows are committed in their own
    # transaction before the risky step (commit count > 1) OR the failure is
    # surfaced (store_result NOT called with completed). The first C2 test
    # pins the false-success; this test pins the missing persistence. RED now:
    # commit count == 1 (scores lost). GREEN after fix: commit count > 1
    # (analyzer rows persisted independently) OR store_result not called.
    assert mock_db.commit.await_count > 1 or mock_store_result.await_count == 0, (
        f"BUG (C2): on save_analyzer_results failure, the worker made "
        f"{mock_db.commit.await_count} commit(s) and called store_result "
        f"{mock_store_result.await_count} time(s). Today the second commit "
        f"(worker.py:508) for analyzer scores is skipped (raise before it) "
        f"and rollback at 529 discards SessionScore/SessionPhase, while "
        f"store_result still reports 'completed'. The user sees a completed "
        f"session with NO multi-score rows persisted. Fix: persist analyzer "
        f"results in their own transaction (commit before the risky enqueue) "
        f"so commit count > 1, OR surface the failure (don't call "
        f"store_result / publish 'completed')."
    )
