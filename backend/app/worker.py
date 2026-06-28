"""arq worker for video processing pipeline.

Run with: uv run python -m app.worker

Dispatches to Vast.ai Serverless GPU.
Requires VASTAI_API_KEY environment variable.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import numpy as np
import sentry_sdk
from arq import Retry, cron
from arq.connections import RedisSettings

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

from app.config import get_settings
from app.storage import download_file
from app.task_manager import (
    TaskStatus,
    close_valkey_pool,
    get_valkey,
    init_valkey_pool,
    is_cancelled,
    mark_cancelled,
    publish_task_event,
    store_error,
    store_result,
    update_progress,
)
from app.vastai.client import NoReadyWorkerError
from src.types import H36Key  # pyright: ignore[reportMissingImports]

logger = logging.getLogger(__name__)

# Configure OpenMP threads for better CPU performance (runtime env var for C library)
_settings = get_settings()
os.environ.setdefault("OMP_NUM_THREADS", str(_settings.app.omp_num_threads))

# Semaphore to limit concurrent Vast.ai serverless dispatches
_VASTAI_SEMAPHORE = asyncio.Semaphore(5)


def _filter_cuda_oom(event: Event, hint: Hint) -> Event | None:
    msg = (event.get("message") or "").lower()
    if "cuda" in msg and "out of memory" in msg:
        return None
    return event


def _init_worker_sentry() -> None:
    dsn = _settings.sentry.dsn.get_secret_value()
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=_settings.sentry.environment,
        traces_sample_rate=_settings.sentry.traces_sample_rate,
        profiles_sample_rate=_settings.sentry.profiles_sample_rate,
        send_default_pii=False,
        before_send=_filter_cuda_oom,
    )
    sentry_sdk.set_tag("component", "ml-worker")


_init_worker_sentry()


def _sample_poses(
    poses: np.ndarray,
    sample_rate: int = 10,
) -> dict:
    """Sample poses to reduce data transfer for frontend.

    Args:
        poses: (N, 17, 3) array of poses
        sample_rate: Sample every Nth frame (default: 10)

    Returns:
        dict with frames list and poses array for sampled frames
    """
    n_frames = len(poses)
    sampled_indices = list(range(0, n_frames, sample_rate))

    # Extract sampled poses as list for JSON serialization
    sampled_poses = poses[sampled_indices].tolist()

    return {
        "frames": sampled_indices,
        "poses": sampled_poses,
    }


def _compute_frame_metrics(poses: np.ndarray) -> dict:
    """Compute frame-by-frame biomechanics metrics.

    Args:
        poses: (N, 17, 3) array of poses

    Returns:
        dict with metric arrays (knee angles, hip angles, trunk lean, CoM height)
    """
    # Extract keypoint arrays (vectorized)
    # H36Key indices: RHIP=1, RKNEE=2, RFOOT=3, LHIP=4, LKNEE=5, LFOOT=6
    # SPINE=7, THORAX=8, NECK=9, HIP_CENTER=0
    r_hip = poses[:, H36Key.RHIP]  # (N, 3)
    r_knee = poses[:, H36Key.RKNEE]
    r_foot = poses[:, H36Key.RFOOT]
    l_hip = poses[:, H36Key.LHIP]
    l_knee = poses[:, H36Key.LKNEE]
    l_foot = poses[:, H36Key.LFOOT]
    thorax = poses[:, H36Key.THORAX]
    spine = poses[:, H36Key.SPINE]
    neck = poses[:, H36Key.NECK]
    hip_center = poses[:, H36Key.HIP_CENTER]

    # Helper function to compute angles between vectors
    def compute_angles_batch(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
        """Compute angles at point b for vectors (a->b) and (b->c).

        Args:
            a, b, c: (N, 3) arrays of keypoints

        Returns:
            (N,) array of angles in degrees, with NaN for invalid frames
        """
        vec1 = b - a  # (N, 3)
        vec2 = c - b  # (N, 3)

        # Compute norms
        norm1 = np.linalg.norm(vec1, axis=1)
        norm2 = np.linalg.norm(vec2, axis=1)

        # Dot product
        dot = np.sum(vec1 * vec2, axis=1)

        # Cosine with clipping
        cos = np.clip(dot / (norm1 * norm2 + 1e-8), -1, 1)

        # Convert to degrees
        angles = np.degrees(np.arccos(cos))

        # Mark invalid frames (where any keypoint is NaN)
        valid_mask = ~(np.isnan(a).any(axis=1) | np.isnan(b).any(axis=1) | np.isnan(c).any(axis=1))
        angles[~valid_mask] = np.nan

        return angles

    # Knee angles (hip-knee-ankle)
    knee_angles_r = compute_angles_batch(r_hip, r_knee, r_foot)
    knee_angles_l = compute_angles_batch(l_hip, l_knee, l_foot)

    # Hip angles (thorax-hip-knee)
    hip_angles_r = compute_angles_batch(thorax, r_hip, r_knee)
    hip_angles_l = compute_angles_batch(thorax, l_hip, l_knee)

    # Trunk lean (spine angle from vertical) — requires 3D poses (x, y, z):
    # the projection zeroes y and takes arctan2(x, z). 2D-only poses (N, 17, 2)
    # have no z, so return None for every frame rather than crash on spine_vec[:, 2].
    if poses.shape[-1] < 3:
        n_frames = poses.shape[0]
        trunk_lean = np.full(n_frames, np.nan)
    else:
        spine_vec = neck - spine  # (N, 3)
        spine_vec[:, 1] = 0  # Project to horizontal plane (set y to 0)

        # Compute lean angle: arctan2(x, z)
        trunk_lean = np.degrees(np.arctan2(spine_vec[:, 0], spine_vec[:, 2]))

        # Handle division by zero (when z=0)
        z_zero = spine_vec[:, 2] == 0
        trunk_lean[z_zero] = 0.0

        # Mark invalid frames
        valid_spine = ~(np.isnan(spine).any(axis=1) | np.isnan(neck).any(axis=1))
        trunk_lean[~valid_spine] = np.nan

    # CoM height (hip center y-coordinate)
    com_height = hip_center[:, 1].copy()
    valid_hip = ~np.isnan(hip_center[:, 1])
    com_height[~valid_hip] = np.nan

    # Convert to lists for JSON (NaN -> None)
    def to_list(arr: np.ndarray) -> list:
        """Convert numpy array to list, replacing NaN with None."""
        return [float(x) if not np.isnan(x) else None for x in arr]

    return {
        "knee_angles_r": to_list(knee_angles_r),
        "knee_angles_l": to_list(knee_angles_l),
        "hip_angles_r": to_list(hip_angles_r),
        "hip_angles_l": to_list(hip_angles_l),
        "trunk_lean": to_list(trunk_lean),
        "com_height": to_list(com_height),
    }


def compose_isu_element_type(tas_type: str | None, rotations: int | None) -> str | None:
    """Compose ISU element code from ML TAS type + phase_detector rotation count."""
    if not tas_type or rotations is None:
        return None
    # import ml remap lazily to avoid importing ML pipeline at module load
    from src.analysis.isu_remap import remap_to_isu  # type: ignore

    return remap_to_isu(tas_type, rotations)


def _category_for_element(code: str | None) -> str | None:
    """Map ISU element code to gamification category."""
    if not code:
        return None
    from app.services.choreography.elements_db import get_element

    el = get_element(code)
    if el is None:
        return None
    if el.type.value == "jump":
        return "jumps"
    if el.type.value == "spin":
        return "spins"
    return "control"


async def startup(ctx: dict[str, Any]) -> None:
    """Initialize shared pools. Retry on Valkey failure."""
    import asyncio as _asyncio

    settings = get_settings()
    if not settings.vastai.api_key.get_secret_value():
        raise RuntimeError(
            "VASTAI_API_KEY is required. "
            "Local GPU processing has been removed. "
            "Set VASTAI_API_KEY in .env or environment."
        )

    for attempt in range(5):
        try:
            await init_valkey_pool(max_connections=5)
            logger.info("Valkey pool initialized (attempt %d)", attempt + 1)
            break
        except (OSError, RuntimeError, ConnectionError) as e:
            wait = min(2**attempt, 30)
            logger.warning(
                "Valkey pool init failed (attempt %d/5): %s, retry in %ds",
                attempt + 1,
                e,
                wait,
            )
            await _asyncio.sleep(wait)
    else:
        raise RuntimeError("Failed to initialize Valkey pool after 5 attempts")

    from app.analytics import get_posthog

    get_posthog()


async def shutdown(ctx: dict[str, Any]) -> None:
    """Close shared pools. arq's own Redis pool is closed by Worker.close() automatically."""
    from app.analytics import shutdown_posthog
    from app.storage import close_s3_clients

    shutdown_posthog()
    logger.info("Worker shutting down")
    await close_valkey_pool()
    await close_s3_clients()


async def process_video_task(
    ctx: dict[str, Any],
    *,
    task_id: str,
    video_key: str,
    person_click: dict[str, int],
    frame_skip: int = 1,
    tracking: str = "auto",
    ml_flags: dict[str, bool] | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """arq task: dispatch video processing to Vast.ai Serverless GPU."""
    if ml_flags is None:
        ml_flags = {
            "lift_3d": True,
            "optical_flow": False,
            "segment": False,
            "foot_track": False,
            "matting": False,
            "inpainting": False,
        }
    # Backward compat: migrate legacy "depth" key to "lift_3d"
    if "depth" in ml_flags and "lift_3d" not in ml_flags:
        ml_flags["lift_3d"] = ml_flags.pop("depth")
    settings = get_settings()
    valkey = get_valkey()

    try:
        now = datetime.now(UTC).isoformat()
        await valkey.hset(
            f"task:{task_id}",
            mapping={"status": TaskStatus.RUNNING, "started_at": now},
        )
        await update_progress(task_id, 0.0, "Starting...")
        await publish_task_event(
            task_id, {"status": "running", "progress": 0.0, "message": "Starting..."}
        )

        from app.crud.session import get_by_id
        from app.database import async_session_factory  # type: ignore[import-untyped]
        from app.vastai.client import process_video_remote_async

        # Fetch element_type and user_id from session if session_id provided
        element_type = None
        isu_code = None
        if session_id:
            async with async_session_factory() as db:
                session = await get_by_id(db, session_id)
                if session:
                    element_type = session.element_type
                    isu_code = session.isu_code
                    if user_id is None:
                        user_id = str(session.user_id)

        logger.info("Dispatching task %s to Vast.ai (video_key=%s)", task_id, video_key)
        await update_progress(task_id, 0.1, "Dispatching to GPU...")
        await publish_task_event(
            task_id,
            {"status": "running", "progress": 0.1, "message": "Dispatching to GPU..."},
        )

        # Cancellation check before expensive GPU dispatch
        if await is_cancelled(task_id):
            await mark_cancelled(task_id)
            return {"status": "cancelled"}

        from app.analytics_events import vastai_dispatched

        vastai_dispatched(
            distinct_id=user_id or session_id or task_id,
            session_id=session_id or "",
            instance_type="vastai-serverless",
            estimated_cost_usd=0.0,  # No estimate available at dispatch time
        )

        async with _VASTAI_SEMAPHORE:
            vast_result = await process_video_remote_async(
                video_key=video_key,
                person_click={"x": person_click["x"], "y": person_click["y"]}
                if person_click
                else None,
                frame_skip=frame_skip,
                tracking=tracking,
                ml_flags=ml_flags,
                element_type=element_type,
                isu_code=isu_code,
            )
        # NoReadyWorkerError is retryable in _async_route_request (3 attempts), so
        # reaching here means the endpoint stayed workerless across all retries —
        # re-raise as a Retry so arq defers it and the autoscaler gets more time.
        logger.info("Vast.ai processing complete for task %s", task_id)
        await update_progress(task_id, 0.7, "GPU processing complete")
        await publish_task_event(
            task_id,
            {"status": "running", "progress": 0.7, "message": "GPU processing complete"},
        )

        # Cancellation check after GPU returns (skip post-processing)
        if await is_cancelled(task_id):
            await mark_cancelled(task_id)
            return {"status": "cancelled"}

        # Prepare pose data for JSON storage (if poses available)
        pose_data = None
        frame_metrics = None

        if vast_result.poses_key:
            try:
                import tempfile

                # Download poses temporarily for sampling
                with tempfile.TemporaryDirectory() as tmpdir:
                    poses_path = Path(tmpdir) / "poses.npy"
                    await asyncio.to_thread(download_file, vast_result.poses_key, str(poses_path))

                    # Load poses and prepare data
                    poses = np.load(str(poses_path))
                    fps = vast_result.stats.get("fps", 30.0)

                    # Run sampling and metrics computation in parallel
                    sample_future = asyncio.to_thread(_sample_poses, poses, 10)
                    metrics_future = asyncio.to_thread(_compute_frame_metrics, poses)
                    sampled, frame_metrics = await asyncio.gather(sample_future, metrics_future)
                    sampled["fps"] = fps
                    pose_data = sampled

                    logger.info(
                        "Prepared pose_data: %d frames, %d metrics",
                        len(sampled["frames"]),
                        len(poses),
                    )
                    await update_progress(task_id, 0.85, "Preparing results...")
                    await publish_task_event(
                        task_id,
                        {"status": "running", "progress": 0.85, "message": "Preparing results..."},
                    )
            except (OSError, ValueError, RuntimeError) as pose_err:
                logger.warning("Failed to prepare pose data: %s", pose_err)

        response_data = {
            "poses_key": vast_result.poses_key or "",
            "metrics_key": vast_result.metrics_key or "",
            "stats": vast_result.stats,
            "status": "Analysis complete!",
        }
        # Track whether the (non-critical) analyzer post-processing failed. When
        # True, the main metrics are committed but SessionScore/SessionPhase rows
        # + gamification are missing — the client must NOT see `completed`.
        analyzer_failed = False
        if session_id:
            try:
                from app.crud.session import (
                    batch_insert_elements,
                    get_by_id,
                    update_session_analysis,
                )
                from app.database import async_session_factory  # type: ignore[import-untyped]
                from app.services.session_saver import save_analysis_results

                async with async_session_factory() as db:
                    try:
                        # Save pose data and frame metrics as JSON
                        if pose_data or frame_metrics:
                            await update_session_analysis(
                                db,
                                session_id=session_id,
                                pose_data=pose_data,
                                frame_metrics=frame_metrics,
                                phases=vast_result.phases,  # type: ignore[arg-type]
                            )

                        # Save metrics and recommendations
                        if vast_result.metrics:
                            await save_analysis_results(
                                db,
                                session_id=session_id,
                                metrics=vast_result.metrics,
                                phases=vast_result.phases,
                                recommendations=vast_result.recommendations or [],
                                goe_grade=vast_result.goe_grade,
                            )

                        # Save timeline segments (same transaction as metrics)
                        if vast_result.segments:
                            seg_confidence = float(
                                np.mean([s["confidence"] for s in vast_result.segments])
                            )
                            await batch_insert_elements(
                                db,
                                session_id,
                                vast_result.segments,
                                segmentation_confidence=seg_confidence,
                            )

                        # Update segmentation_status atomically
                        session_obj = await get_by_id(db, session_id)
                        if session_obj:
                            if vast_result.segments is not None:
                                session_obj.segmentation_status = "done"
                            else:
                                session_obj.segmentation_status = "failed"

                        # Single commit for metrics + segments + status
                        await db.commit()

                        # SkateLab analyzer: compute multi-score + save scores/phases,
                        # then enqueue gamification task. Non-critical: failures here
                        # must not break the main analysis result already committed.
                        try:
                            from app.services.analyzer_save import save_analyzer_results

                            analyzer = await save_analyzer_results(
                                db,
                                session_id=session_id,
                                metrics=vast_result.metrics or [],
                                phases=vast_result.phases,
                                fps=vast_result.stats.get("fps", 30.0),
                                total_frames=len(vast_result.segments)
                                if vast_result.segments
                                else 0,
                                rotations=vast_result.rotations,
                            )

                            # Compose ISU code from TAS type + rotation count
                            isu_code = compose_isu_element_type(
                                analyzer["element_type"], analyzer["rotations"]
                            )
                            if isu_code is not None and session_obj is not None:
                                session_obj.element_type = isu_code
                                db.add(session_obj)

                            await db.commit()

                            # Enqueue gamification task to fast queue (if redis pool available)
                            redis = ctx.get("redis")
                            if redis is not None and hasattr(redis, "enqueue_job"):
                                await redis.enqueue_job(
                                    "compute_gamification_task",
                                    session_id=session_id,
                                    user_id=str(session_obj.user_id)
                                    if session_obj
                                    else (user_id or ""),
                                    overall_score=analyzer["overall_score"],
                                    element_type=isu_code,
                                    _queue_name="skatelab:queue:fast",
                                )
                        except Exception as analyzer_err:  # noqa: BLE001
                            # Analyzer post-processing failed: SessionScore /
                            # SessionPhase rows are discarded by the rollback below
                            # and gamification is skipped. The MAIN metrics (committed
                            # at 480) are intact, so this is partial data loss, not
                            # total — but we must NOT report `completed` to the client
                            # while multi-score rows + XP/skill-unlocks are missing.
                            # Mark the DB Session row `partial`, surface a non-
                            # completed status to Valkey + the event stream, and keep
                            # store_result as a single call (the client polls Valkey
                            # for the terminal status). Committing the status change
                            # in its own transaction also persists the partial state
                            # independently of the rolled-back analyzer rows.
                            logger.warning(
                                "Skating analyzer post-processing failed for %s: %s",
                                session_id,
                                analyzer_err,
                            )
                            await db.rollback()
                            analyzer_failed = True
                            try:
                                session_partial = await get_by_id(db, session_id)
                                if session_partial is not None:
                                    session_partial.status = "partial"
                                    session_partial.error_message = str(analyzer_err)
                                    await db.commit()
                            except (OSError, RuntimeError):
                                logger.warning(
                                    "Failed to mark session partial for %s",
                                    session_id,
                                )
                    except Exception:
                        await db.rollback()
                        raise
            except (OSError, ValueError, RuntimeError) as save_err:
                # Main save failed: ZERO SessionMetric rows committed, Session.status
                # never advanced. Do NOT fall through to store_result(COMPLETED) +
                # publish_task_event("completed") — that would be false success with
                # total data loss. Surface the failure instead: write Valkey failed,
                # publish a failed event, and return a non-completed result. (The DB
                # Session row is left for the outermost except / #371 path to mark
                # failed if this re-surfaces there; we do not commit here so the
                # rollback inside the inner except is the last DB write on this path.)
                logger.warning("Failed to save session data: %s", save_err)
                await store_error(task_id, str(save_err))
                await publish_task_event(
                    task_id,
                    {"status": "failed", "progress": 1.0, "message": str(save_err)},
                )
                return {
                    "poses_key": vast_result.poses_key or "",
                    "metrics_key": vast_result.metrics_key or "",
                    "stats": vast_result.stats,
                    "status": "Analysis failed during save",
                }

        # Write Valkey status LAST, after DB commit (if any)
        if analyzer_failed:
            response_data["status"] = "Analysis complete with partial results"
        await store_result(task_id, response_data)

        from app.analytics_events import analysis_completed

        analysis_completed(
            distinct_id=user_id or session_id or task_id,
            session_id=session_id or "",
            duration_s=0,
            model="moganet-b",
            elements_count=len(vast_result.segments) if vast_result.segments else 0,
            gpu="vastai",
        )

        await update_progress(task_id, 1.0, "Done")
        await publish_task_event(
            task_id,
            {
                "status": "partial" if analyzer_failed else "completed",
                "progress": 1.0,
                "message": "Done with partial results" if analyzer_failed else "Done",
            },
        )

        return response_data

    except (OSError, ValueError, RuntimeError, ConnectionError, TimeoutError) as e:
        # NoReadyWorkerError is retryable: the Vast.ai endpoint had no ready worker
        # across route retries (workers still loading/warming, or endpoint stopped).
        # Defer via Retry so the autoscaler gets time to spin a worker up — don't
        # mark the task failed, just requeue it.
        is_no_ready_worker = isinstance(e, NoReadyWorkerError)
        logger.exception("Pipeline task %s failed", task_id)
        await store_error(task_id, str(e))

        from app.analytics_events import analysis_failed

        analysis_failed(
            distinct_id=user_id or session_id or task_id,
            session_id=session_id or "",
            error_type=type(e).__name__,
            retry_count=ctx.get("job_try", 1),
        )

        error_msg = str(e).lower()
        retryable = is_no_ready_worker or any(
            term in error_msg for term in ["timeout", "connection", "network"]
        )
        try:
            event_status = "queued" if retryable else "failed"
            event_message = "GPU worker warming up, retrying..." if is_no_ready_worker else str(e)
            await publish_task_event(
                task_id,
                {"status": event_status, "progress": 0.1, "message": event_message},
            )
        except (OSError, RuntimeError):
            logger.warning("Failed to publish error event for task %s", task_id)

        # Non-retryable failure: mark the DB Session row as failed so the user
        # polling GET /sessions/{id} (which reads the DB, not Valkey) sees a
        # terminal state instead of a stuck queued/uploading row. Mirrors
        # analyze_music_task's DB-status-failed update (worker.py:815-831).
        if not retryable and session_id:
            try:
                from app.crud.session import get_by_id as _get_by_id_failed
                from app.database import async_session_factory  # type: ignore[import-untyped]

                async with async_session_factory() as db:
                    session_row = await _get_by_id_failed(db, session_id)
                    if session_row is not None:
                        session_row.status = "failed"
                        session_row.error_message = str(e)
                        await db.commit()
            except (OSError, RuntimeError):
                logger.warning("Failed to update session status to failed for %s", session_id)

        if retryable:
            raise Retry(defer=ctx.get("job_try", 1) * 10) from e
        raise


async def detect_video_task(
    ctx: dict[str, Any],
    *,
    task_id: str,
    video_key: str,
    tracking: str = "auto",
) -> dict[str, Any]:
    """arq task: detect persons in uploaded video.

    Dispatches to Vast.ai Serverless GPU.
    Requires VASTAI_API_KEY environment variable.
    """
    valkey = get_valkey()

    try:
        now = datetime.now(UTC).isoformat()
        await valkey.hset(
            f"task:{task_id}",
            mapping={"status": TaskStatus.RUNNING, "started_at": now},
        )
        await update_progress(task_id, 0.0, "Starting detection...")
        await publish_task_event(
            task_id,
            {"status": "running", "progress": 0.0, "message": "Starting detection..."},
        )

        from app.vastai.client import detect_video_remote_async

        logger.info("Dispatching detection task %s to Vast.ai (video_key=%s)", task_id, video_key)
        await update_progress(task_id, 0.1, "Dispatching to GPU...")
        await publish_task_event(
            task_id,
            {"status": "running", "progress": 0.1, "message": "Dispatching to GPU..."},
        )

        if await is_cancelled(task_id):
            await mark_cancelled(task_id)
            return {"status": "cancelled"}

        async with _VASTAI_SEMAPHORE:
            detect_result = await detect_video_remote_async(
                video_key=video_key,
                tracking=tracking,
            )

        result_data = {
            "persons": [
                {
                    "track_id": p["track_id"],
                    "hits": p["hits"],
                    "bbox": p["bbox"],
                    "mid_hip": p["mid_hip"],
                }
                for p in detect_result.persons
            ],
            "preview_image": detect_result.preview_image,
            "video_key": detect_result.video_key,
            "auto_click": detect_result.auto_click,
            "status": detect_result.status,
        }
        await store_result(task_id, result_data)
        await update_progress(task_id, 1.0, "Done")
        await publish_task_event(
            task_id, {"status": "completed", "progress": 1.0, "message": "Done"}
        )
        return result_data

    except (
        NoReadyWorkerError,
        httpx.TimeoutException,
        httpx.ConnectError,
        ConnectionError,
        TimeoutError,
    ) as e:
        logger.warning("Vast.ai connection/no-worker error for detect task %s: %s", task_id, e)
        await store_error(task_id, str(e))
        with contextlib.suppress(OSError, RuntimeError):
            await publish_task_event(
                task_id,
                {
                    "status": "queued",
                    "progress": 0.1,
                    "message": (
                        "GPU worker warming up, retrying..."
                        if isinstance(e, NoReadyWorkerError)
                        else str(e)
                    ),
                },
            )
        raise Retry(defer=ctx.get("job_try", 1) * 10) from e
    except (OSError, ValueError, RuntimeError) as e:
        logger.exception("Detection task %s failed", task_id)
        await store_error(task_id, str(e))
        try:
            await publish_task_event(
                task_id, {"status": "failed", "progress": 0.0, "message": str(e)}
            )
        except (OSError, RuntimeError):
            logger.warning("Failed to publish error event for task %s", task_id)
        error_msg = str(e).lower()
        if any(term in error_msg for term in ["timeout", "connection", "network"]):
            raise Retry(defer=ctx.get("job_try", 1) * 10) from e
        raise


async def analyze_music_task(
    ctx: dict[str, Any],
    *,
    music_id: str,
    s3_key: str,
) -> dict[str, Any]:
    """arq task: analyze music file for BPM, structure, and energy peaks.

    Args:
        music_id: Database ID of the music record
        s3_key: S3 storage key for the audio file

    Returns:
        dict with status and analysis results
    """
    valkey = get_valkey()

    try:
        from app.crud.choreography import (
            find_music_by_fingerprint,
            get_music_analysis_by_id,
            update_music_analysis,
        )
        from app.database import async_session_factory
        from app.services.choreography.fingerprint import compute_fingerprint
        from app.services.choreography.music_analyzer import analyze_music_sync

        logger.info("Starting music analysis for music_id=%s, s3_key=%s", music_id, s3_key)

        # Download from S3 to temp file
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / f"music_{music_id}.mp3"
            logger.info("Downloading music from S3: %s -> %s", s3_key, audio_path)
            await asyncio.to_thread(download_file, s3_key, str(audio_path))

            # Compute fingerprint
            logger.info("Computing fingerprint for %s", audio_path)
            fingerprint = await asyncio.to_thread(compute_fingerprint, str(audio_path))
            if not fingerprint:
                raise RuntimeError("Failed to compute fingerprint")

            logger.info("Fingerprint computed: %s", fingerprint[:16] + "...")

            # Check for duplicate
            async with async_session_factory() as db:
                music = await get_music_analysis_by_id(db, music_id)
                if not music:
                    raise RuntimeError(f"Music record {music_id} not found")

                # Store fingerprint
                await update_music_analysis(db, music, fingerprint=fingerprint)
                await db.commit()

                # Check for existing analysis with same fingerprint
                duplicate = await find_music_by_fingerprint(db, fingerprint)
                if duplicate and duplicate.id != music_id:
                    fp_preview = (
                        duplicate.fingerprint[:16] + "..." if duplicate.fingerprint else "N/A"
                    )
                    logger.info(
                        "Found duplicate analysis: %s (music_id=%s)", duplicate.id, fp_preview
                    )
                    # Copy analysis results from duplicate
                    await update_music_analysis(
                        db,
                        music,
                        audio_url=music.audio_url,  # Keep our own URL
                        duration_sec=duplicate.duration_sec,
                        bpm=duplicate.bpm,
                        peaks=duplicate.peaks,
                        structure=duplicate.structure,
                        energy_curve=duplicate.energy_curve,
                        status="completed",
                    )
                    await db.commit()
                    return {
                        "status": "completed",
                        "music_id": music_id,
                        "duplicate_of": duplicate.id,
                        "bpm": duplicate.bpm,
                        "duration_sec": duplicate.duration_sec,
                    }

                # No duplicate - run full analysis
                logger.info("No duplicate found, running full music analysis")
                result = await asyncio.to_thread(analyze_music_sync, str(audio_path))

                await update_music_analysis(
                    db,
                    music,
                    audio_url=f"/files/{s3_key}",
                    duration_sec=result["duration_sec"],
                    bpm=result["bpm"],
                    peaks=result["peaks"],
                    structure=result.get("structure") or [],
                    energy_curve=result["energy_curve"],
                    status="completed",
                )
                await db.commit()

                logger.info(
                    "Music analysis complete: music_id=%s, bpm=%.1f, duration=%.1f",
                    music_id,
                    result["bpm"],
                    result["duration_sec"],
                )

                return {
                    "status": "completed",
                    "music_id": music_id,
                    "bpm": result["bpm"],
                    "duration_sec": result["duration_sec"],
                }

    except (OSError, ValueError, RuntimeError, ConnectionError, TimeoutError) as e:
        logger.exception("Music analysis task failed for music_id=%s", music_id)

        # Update DB status to failed
        try:
            from app.crud.choreography import get_music_analysis_by_id, update_music_analysis
            from app.database import async_session_factory

            async with async_session_factory() as db:
                music = await get_music_analysis_by_id(db, music_id)
                if music:
                    await update_music_analysis(db, music, status="failed")
                    await db.commit()
        except (OSError, RuntimeError):
            logger.warning("Failed to update music status to failed")

        raise


async def cleanup_expired_tokens(ctx: dict) -> int:
    """Delete expired refresh tokens and password reset tokens."""
    from app.crud.password_reset_token import cleanup_expired as cleanup_reset
    from app.crud.refresh_token import cleanup_expired as cleanup_refresh
    from app.database import async_session_factory

    async with async_session_factory() as db:
        n1 = await cleanup_refresh(db, batch_size=500)
        n2 = await cleanup_reset(db, batch_size=500)
        await db.commit()
        return n1 + n2


async def compute_gamification_task(
    ctx: dict[str, Any],
    *,
    session_id: str,
    user_id: str,
    overall_score: float,
    element_type: str | None = None,
) -> dict[str, Any]:
    """arq task: award XP and check skill unlocks after session analysis."""
    from app.database import async_session_factory  # type: ignore[import-untyped]
    from app.services.gamification import award_session_xp, check_skill_unlocks

    try:
        async with async_session_factory() as db:
            xp_result = await award_session_xp(db, user_id, overall_score)

            category = _category_for_element(element_type)

            unlocked_skills: list[str] = []
            if category:
                unlocked_skills = await check_skill_unlocks(db, user_id, category, overall_score)

            await db.commit()

        logger.info(
            "Gamification computed for session=%s user=%s xp=%d unlocked=%s",
            session_id,
            user_id,
            xp_result["xp_earned"],
            unlocked_skills,
        )
        return {
            "session_id": session_id,
            "xp_earned": xp_result["xp_earned"],
            "unlocked_skills": unlocked_skills,
        }
    except (OSError, ValueError, RuntimeError) as e:
        logger.exception("Gamification task failed for session %s", session_id)
        raise


class FastWorkerSettings:
    """arq worker for lightweight detection tasks."""

    queue_name: str = "skatelab:queue:fast"
    max_jobs: int = _settings.app.worker_max_jobs_remote
    retry_jobs: bool = True
    retry_delays: ClassVar[list[int]] = _settings.app.worker_retry_delays
    job_completion_wait: int = 120

    on_startup = startup
    on_shutdown = shutdown
    functions: ClassVar[list] = [detect_video_task, analyze_music_task, compute_gamification_task]
    cron_jobs: ClassVar[list] = [
        cron(cleanup_expired_tokens, minute=7),
    ]

    redis_settings = RedisSettings(**_settings.valkey.redis_kwargs())


class HeavyWorkerSettings:
    """arq worker for full ML pipeline processing."""

    queue_name: str = "skatelab:queue:heavy"
    max_jobs: int = 1  # GPU-bound, can't parallelize
    retry_jobs: bool = True
    retry_delays: ClassVar[list[int]] = _settings.app.worker_retry_delays
    job_completion_wait: int = 600

    on_startup = startup
    on_shutdown = shutdown
    functions: ClassVar[list] = [process_video_task]
    cron_jobs: ClassVar[list] = []

    redis_settings = RedisSettings(**_settings.valkey.redis_kwargs())
