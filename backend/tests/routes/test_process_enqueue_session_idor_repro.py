"""Repro test — `POST /process/queue` accepts another user's `session_id` (no
ownership check) → worker overwrites the victim's session with the attacker's
analysis results (mutation IDOR + data corruption).

`ProcessController.enqueue_process` (routes/process.py:42-78) takes
`data.session_id` from the request body (`ProcessRequest.session_id`,
schemas.py) and:
  1. creates a task state for the CALLER (`user_id=str(user.id)`, line 54), then
  2. enqueues `process_video_task` passing `session_id=data.session_id` and
     `user_id=str(user.id)` (lines 65-76) — NO check that the session belongs to
     the caller.

The worker (`process_video_task`, worker.py:300-302) then does
`session = await get_by_id(db, session_id)` (also no owner check) and writes
analysis results INTO that session via `update_session_analysis` /
`save_analysis_results` (worker.py:416/426/440) — overwriting the victim's
pose_data, frame_metrics, phases, metrics, overall_score, recommendations,
status with the attacker's video analysis.

So an authenticated attacker can:
  - Point processing at ANY session id (guessed / leaked from logs / shared URLs).
  - The worker clobbers the victim's session with the attacker's results
    (data corruption of another user's record).
  - Burn GPU compute billed to whoever pays for the worker, on the victim's
    session record.
  - This is the ENQUEUE-side (mutation) sibling of the read-side IDOR in #339
    (process status/cancel/result) and #338 (scores/phases/plans) — same root
    cause (fetch by id, no ownership check), but here it MUTATES the victim's
    data, not just reads it.

The existing `test_e2e_process.py` only enqueues with the SAME user's session
(or no session) — cross-user `session_id` is never tested, so the IDOR never
surfaces in CI. `test_detect_process_auth.py` only checks UNAUTHENTICATED → 401.

Repro: create a victim-owned session, then call `POST /process/queue` as the
ATTACKER with `session_id = victim's session id` + the attacker's `video_key`.
Mock `create_task_state` / `arq_pool.enqueue_job` (no real Valkey / worker run).
RED now: 200 and `enqueue_job` is called with `session_id = victim's session id`
— the attacker dispatched processing onto the victim's session. After the fix
(load the session, verify `session.user_id == user.id` or coaching connection,
403 otherwise) → 403 and `enqueue_job` not called with the victim's session_id.

No production data mutated: in-memory SQLite test DB; create_task_state and
arq_pool.enqueue_job are mocked (no real task dispatch).
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
        email="victim-enq@example.com",
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
        email="attacker-enq@example.com",
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


@pytest.mark.asyncio
async def test_process_enqueue_other_users_session_returns_403_repro(
    client, attacker_headers, victim_user, db_session: AsyncSession
):
    """POST /process/queue with ANOTHER user's session_id must 403.

    RED now: 200 and enqueue_job is called with the victim's session_id — the
    attacker dispatches processing onto the victim's session, and the worker
    would overwrite the victim's analysis results. After the fix → 403.
    """
    from app.crud.session import create as crud_create

    victim_session = await crud_create(db_session, user_id=victim_user.id, element_type="lutz")

    with (
        patch("app.routes.process.create_task_state", new_callable=AsyncMock),
    ):
        response = await client.post(
            "/v1/process/queue",
            json={
                "video_key": "uploads/attacker/evil.mp4",
                "person_click": {"x": 100, "y": 200},
                "session_id": victim_session.id,  # ← the VICTIM's session
            },
            headers=attacker_headers,
        )

    assert response.status_code == 403, (
        "BUG (mutation IDOR): POST /process/queue accepted ANOTHER user's "
        f"session_id and returned {response.status_code} (expected 403). The "
        f"worker would load the victim's session by id (worker.py:302, no owner "
        f"check) and overwrite its analysis results with the attacker's video. "
        f"Body: {response.text}"
    )

    # The worker must NOT have been dispatched onto the victim's session.
    enqueue_call = client.app.state.arq_pool.enqueue_job.call_args
    if enqueue_call is not None:
        dispatched_session_id = enqueue_call.kwargs.get("session_id")
        assert dispatched_session_id != victim_session.id, (
            f"BUG (mutation IDOR): arq enqueue_job was called with the victim's "
            f'session_id="{dispatched_session_id}" on behalf of the attacker — '
            f"the worker would clobber the victim's session data."
        )
