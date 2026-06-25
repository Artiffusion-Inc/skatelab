"""Repro tests for IDOR on process task status/cancel (missing ownership check).

`ProcessController` is INCONSISTENT about task ownership:

  - `GET /process/{task_id}/stream` (routes/process.py:110-126) DOES check
    ownership: it reads `state["user_id"]` and raises `NotAuthorizedException`
    if `task_user_id != user.id` (lines 123-126).

  - `GET /process/{task_id}/status` (routes/process.py:80-102) does NOT check
    ownership: it returns `get_task_state(task_id)` for ANY authenticated user,
    including the `result` payload (processed video paths, poses path, CSV
    path, stats, error message). The `user` dependency is injected but unused.

  - `POST /process/{task_id}/cancel` (routes/process.py:104-108) does NOT check
    ownership: it calls `set_cancel_signal(task_id)` for ANY user — so an
    attacker can cancel another user's running processing job.

So the SAME controller guards the SSE stream but leaves the status + cancel
endpoints open. A user can poll another user's task status (leaking result
paths / progress / error detail) and cancel another user's job.

The existing `test_detect_process_auth.py` only checks that UNAUTHENTICATED
requests get 401 — it never tests cross-USER access (authenticated-but-wrong-
user), so this IDOR never surfaces in CI. `test_e2e_process.py` mocks
`get_task_state` with states that OMIT `user_id` entirely (so even the stream
ownership check is bypassed in tests — a separate latent gap), and uses a
single authed user, so cross-user access is never exercised.

Repro approach: mock `get_task_state` to return a task state carrying
`user_id == victim`, then call status/cancel as the ATTACKER (a different
authenticated user). RED now: status returns 200 with the victim's result,
cancel returns 200 `cancel_requested`. After the fix (add the same ownership
check as `stream`) → 403.

No production data mutated: `get_task_state` / `set_cancel_signal` are mocked
to AsyncMock (no real Valkey writes); only HTTP responses are observed.
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
        email="victim-proc@example.com",
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
        email="attacker-proc@example.com",
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


# A task that belongs to the VICTIM — carries user_id so the (correct) stream
# ownership check would reject an attacker. status/cancel ignore user_id.
_VICTIM_TASK_ID = "proc_victim_secret"


def _victim_running_state(victim_user: User) -> dict:
    return {
        "task_id": _VICTIM_TASK_ID,
        "status": "running",
        "progress": 0.5,
        "message": "Extracting poses",
        "result": None,
        "error": "",
        "user_id": str(victim_user.id),  # owned by victim
    }


def _victim_completed_state(victim_user: User) -> dict:
    return {
        "task_id": _VICTIM_TASK_ID,
        "status": "completed",
        "progress": 1.0,
        "message": "Done",
        "result": {
            "video_path": "output/proc_victim_secret/result.mp4",
            "poses_path": "output/proc_victim_secret/poses.npz",
            "csv_path": "output/proc_victim_secret/metrics.csv",
            "stats": {"total_frames": 300, "valid_frames": 280, "fps": 30.0},
            "status": "completed",
        },
        "error": "",
        "user_id": str(victim_user.id),
    }


@pytest.mark.asyncio
async def test_process_status_idor_other_user_returns_403_repro(
    client, attacker_headers, victim_user
):
    """GET /process/{task_id}/status for ANOTHER user's task must 403, not 200.

    RED now: returns 200 with the victim's result paths + stats. The `stream`
    endpoint in the SAME controller checks ownership; `status` does not.
    After the fix → 403.
    """
    state = _victim_completed_state(victim_user)
    with patch("app.routes.process.get_task_state", new_callable=AsyncMock, return_value=state):
        response = await client.get(
            f"/v1/process/{_VICTIM_TASK_ID}/status", headers=attacker_headers
        )

    assert response.status_code == 403, (
        "BUG (IDOR): GET /process/{id}/status returned "
        f"{response.status_code} for another user's task instead of 403. "
        f"The victim's result leaked: {response.text}"
    )


@pytest.mark.asyncio
async def test_process_cancel_idor_other_user_returns_403_repro(
    client, attacker_headers, victim_user
):
    """POST /process/{task_id}/cancel for ANOTHER user's task must 403, not 200.

    RED now: cancel returns 200 `cancel_requested` — an attacker can kill
    another user's running job. After the fix → 403.
    """
    state = _victim_running_state(victim_user)
    with (
        patch("app.routes.process.get_task_state", new_callable=AsyncMock, return_value=state),
        patch("app.routes.process.set_cancel_signal", new_callable=AsyncMock),
    ):
        response = await client.post(
            f"/v1/process/{_VICTIM_TASK_ID}/cancel", headers=attacker_headers
        )

    assert response.status_code == 403, (
        "BUG (IDOR): POST /process/{id}/cancel returned "
        f"{response.status_code} for another user's task instead of 403 — an "
        f"attacker can cancel the victim's job. Body: {response.text}"
    )


@pytest.mark.asyncio
async def test_process_status_idor_no_user_id_in_state_treated_as_denied_repro(
    client, attacker_headers
):
    """GET /process/{id}/status for a task with NO user_id must NOT leak to any user.

    A task state without `user_id` (e.g. legacy task, or a state written by a
    code path that forgot to set it) is currently readable by ANY authenticated
    user — the `status` route does not check ownership at all. This pins the
    stricter contract: a task whose owner cannot be established must be denied
    to non-owners (fail-closed), not returned.

    RED now: returns 200. After the fix (ownership check that fails closed when
    user_id is missing) → 403.
    """
    state = {
        "task_id": "proc_orphan",
        "status": "running",
        "progress": 0.2,
        "message": "Working",
        "result": None,
        "error": "",
        # NOTE: no "user_id" key — owner unknown.
    }
    with patch("app.routes.process.get_task_state", new_callable=AsyncMock, return_value=state):
        response = await client.get("/v1/process/proc_orphan/status", headers=attacker_headers)

    assert response.status_code == 403, (
        "BUG (IDOR/fail-open): GET /process/{id}/status returned "
        f"{response.status_code} for a task with NO user_id instead of 403. "
        f"An unattributed task must be fail-closed (denied), not readable by "
        f"any authenticated user. Body: {response.text}"
    )
