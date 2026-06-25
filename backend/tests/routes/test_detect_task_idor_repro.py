"""Repro tests for IDOR on detect task status/result (missing ownership check).

`DetectController` (routes/detect.py) enqueues detection with `user_id` stored
on the task state (`create_task_state(..., user_id=str(user.id))`, detect.py:53)
but the read endpoints never verify the requesting user owns the task:

  - `GET /detect/{task_id}/status` (detect.py:70-90) returns `get_task_state`
    for ANY authenticated user — leaking progress, message, error, and the
    `result` (persons + preview_image + video_key) when present.
  - `GET /detect/{task_id}/result` (detect.py:92-117) returns the detection
    result (persons bboxes, preview, video_key) for ANY authenticated user.

Neither endpoint references `user` for authorization (the `user: CurrentUser`
dependency is injected but unused). So an attacker can read another user's
person-detection output — including `video_key` (the victim's uploaded video
S3 key) and the detected persons' bounding boxes / mid-hip coordinates.

This is the SAME bug class as the process-controller IDOR (see
`test_process_task_idor_repro.py`) and the session-derived-data IDOR (see
`test_scores_phases_plans_idor_repro.py`): routes that fetch by id alone
without an ownership guard, unlike `GET /sessions/{id}` which checks
`session.user_id != user.id`.

The existing `test_detect_process_auth.py` only asserts UNAUTHENTICATED → 401;
it never tests cross-USER access, so this IDOR never surfaces in CI.

Repro: mock `get_task_state` to return a task state carrying
`user_id == victim`, call status/result as the ATTACKER. RED now: 200 with the
victim's detection data. After the fix (ownership check before returning) → 403.

No production data mutated: `get_task_state` is mocked (no real Valkey reads).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from app.auth.security import create_access_token, hash_password
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def victim_user(db_session: AsyncSession) -> User:
    user = User(
        email="victim-detect@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def attacker_user(db_session: AsyncSession) -> User:
    user = User(
        email="attacker-detect@example.com",
        hashed_password=hash_password("pass"),
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def attacker_headers(attacker_user):
    token = create_access_token(user_id=attacker_user.id)
    return {"Authorization": f"Bearer {token}"}


_DETECT_TASK_ID = "det_victim_secret"


def _victim_completed_state(victim_user: User) -> dict:
    return {
        "task_id": _DETECT_TASK_ID,
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": {
            "persons": [
                {
                    "track_id": 1,
                    "hits": 42,
                    "bbox": [10.0, 20.0, 100.0, 200.0],
                    "mid_hip": [55.0, 110.0],
                },
            ],
            "preview_image": "data:image/png;base64,AAA",
            "video_key": "input/victim_secret_video.mp4",
            "auto_click": {"x": 150, "y": 300},
            "status": "completed",
        },
        "error": "",
        "user_id": str(victim_user.id),  # owned by victim
    }


@pytest.mark.asyncio
async def test_detect_status_idor_other_user_returns_403_repro(
    client, attacker_headers, victim_user
):
    """GET /detect/{task_id}/status for ANOTHER user's task must 403, not 200.

    RED now: returns 200 with the victim's persons + video_key + preview.
    After the fix → 403.
    """
    state = _victim_completed_state(victim_user)
    with patch("app.routes.detect.get_task_state", new_callable=AsyncMock, return_value=state):
        response = await client.get(
            f"/v1/detect/{_DETECT_TASK_ID}/status", headers=attacker_headers
        )

    assert response.status_code == 403, (
        "BUG (IDOR): GET /detect/{id}/status returned "
        f"{response.status_code} for another user's task instead of 403. "
        f"The victim's detection data leaked: {response.text}"
    )


@pytest.mark.asyncio
async def test_detect_result_idor_other_user_returns_403_repro(
    client, attacker_headers, victim_user
):
    """GET /detect/{task_id}/result for ANOTHER user's task must 403, not 200.

    RED now: returns 200 with the victim's persons bboxes + video_key + preview.
    After the fix → 403.
    """
    state = _victim_completed_state(victim_user)
    with patch("app.routes.detect.get_task_state", new_callable=AsyncMock, return_value=state):
        response = await client.get(
            f"/v1/detect/{_DETECT_TASK_ID}/result", headers=attacker_headers
        )

    assert response.status_code == 403, (
        "BUG (IDOR): GET /detect/{id}/result returned "
        f"{response.status_code} for another user's task instead of 403. "
        f"The victim's detection result leaked: {response.text}"
    )
